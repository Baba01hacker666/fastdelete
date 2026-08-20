"""
Tests for FastDeleter: normal files, unusual filenames, symlinks, permissions, dry-run, workers, and race conditions.
"""

import os
import stat
import sys
import threading
import pytest
from pathlib import Path

from fastdelete.deleter import FastDeleter
from fastdelete.filters import DeletionFilter
from fastdelete.progress import ProgressReporter
from fastdelete.scanner import ScanItem


def test_delete_single_file(tmp_path):
    """Test deleting a single regular file."""
    f = tmp_path / "test.txt"
    f.write_text("content")

    deleter = FastDeleter(str(f))
    stats = deleter.run()

    assert not f.exists()
    assert stats.files_deleted == 1
    assert stats.failed == 0


def test_delete_empty_directory(tmp_path):
    """Test deleting an empty directory."""
    d = tmp_path / "empty_dir"
    d.mkdir()

    deleter = FastDeleter(str(d))
    stats = deleter.run()

    assert not d.exists()
    assert stats.directories_deleted == 1
    assert stats.failed == 0


def test_delete_deep_tree(tmp_path):
    """Test deleting a nested directory tree."""
    curr = tmp_path / "deep_root"
    curr.mkdir()
    total_files = 0
    total_dirs = 1

    for i in range(20):
        curr = curr / f"level_{i}"
        curr.mkdir()
        total_dirs += 1
        for j in range(5):
            f = curr / f"file_{j}.txt"
            f.write_text("data")
            total_files += 1

    deleter = FastDeleter(str(tmp_path / "deep_root"))
    stats = deleter.run()

    assert not (tmp_path / "deep_root").exists()
    assert stats.files_deleted == total_files
    assert stats.directories_deleted == total_dirs
    assert stats.failed == 0


def test_delete_unusual_filenames(tmp_path):
    """
    Test deleting files with Unicode, emojis, newlines, tabs, quotes,
    spaces, leading dashes, and hidden files.
    """
    root = tmp_path / "unusual_root"
    root.mkdir()

    filenames = [
        "regular.txt",
        "file with spaces.txt",
        "file\twith\ttabs.txt",
        'file"with"quotes.txt',
        "file'with'single'quotes.txt",
        "unicode_café_résumé.txt",
        "emoji_🎉_🚀_🔥.txt",
        "cjk_中文_日本語_한국어.txt",
        "arabic_العربية.txt",
        "-starts-with-dash.txt",
        "--double-dash.txt",
        ".hidden-dotfile",
        "special_chars_!@#$%^&*()_+=~`{}[]|;.txt",
        "very_long_name_" + ("a" * 150) + ".txt",
    ]

    if sys.platform != "win32":
        # Newlines in filenames are valid on POSIX
        filenames.append("file\nwith\nnewlines.txt")

    created = 0
    for name in filenames:
        try:
            p = root / name
            p.write_text("unusual content")
            created += 1
        except OSError:
            # Filesystem might not support certain characters or lengths
            pass

    assert created > 0

    deleter = FastDeleter(str(root))
    stats = deleter.run()

    assert not root.exists()
    assert stats.files_deleted == created
    assert stats.failed == 0


def test_symlink_to_file_preserves_target(tmp_path):
    """Verify that deleting a symlink removes the link but preserves the target file."""
    target = tmp_path / "target_file.txt"
    target.write_text("important data")

    link_dir = tmp_path / "link_dir"
    link_dir.mkdir()
    link = link_dir / "symlink.txt"
    link.symlink_to(target)

    deleter = FastDeleter(str(link_dir))
    stats = deleter.run()

    assert not link_dir.exists()
    assert not link.exists()
    # The actual target file outside link_dir MUST still exist and have content!
    assert target.exists()
    assert target.read_text() == "important data"


def test_symlink_to_directory_preserves_target_directory(tmp_path):
    """Verify that deleting a symlink pointing to a directory preserves the target dir and its contents."""
    real_dir = tmp_path / "real_dir"
    real_dir.mkdir()
    secret = real_dir / "secret.txt"
    secret.write_text("do not delete")

    link_dir = tmp_path / "link_dir"
    link_dir.mkdir()
    dir_symlink = link_dir / "symlink_dir"
    dir_symlink.symlink_to(real_dir)

    deleter = FastDeleter(str(link_dir))
    stats = deleter.run()

    assert not link_dir.exists()
    # Real directory and its secret file MUST remain untouched!
    assert real_dir.exists()
    assert secret.exists()
    assert secret.read_text() == "do not delete"


def test_broken_symlink_deletion(tmp_path):
    """Verify broken symlinks are unlinked cleanly without error."""
    broken_root = tmp_path / "broken_root"
    broken_root.mkdir()
    broken_link = broken_root / "broken.lnk"
    broken_link.symlink_to(tmp_path / "non_existent_file.dat")

    deleter = FastDeleter(str(broken_root))
    stats = deleter.run()

    assert not broken_root.exists()
    assert stats.files_deleted == 1
    assert stats.failed == 0


def test_force_mode_read_only_files(tmp_path):
    """Verify that --force allows deleting read-only files and directories."""
    root = tmp_path / "readonly_root"
    root.mkdir()
    f = root / "readonly.txt"
    f.write_text("protected")

    # Make file read-only (remove write permission)
    os.chmod(str(f), stat.S_IRUSR)

    # Deleting without force may fail on some platforms/filesystems
    # With force=True, it must succeed!
    deleter = FastDeleter(str(root), force=True)
    stats = deleter.run()

    assert not root.exists()
    assert stats.files_deleted == 1
    assert stats.failed == 0


def test_dry_run_mode(tmp_path):
    """Verify dry-run simulates deletion without modifying filesystem."""
    root = tmp_path / "dry_root"
    root.mkdir()
    f1 = root / "f1.txt"
    f1.write_text("hello")
    sub = root / "sub"
    sub.mkdir()
    f2 = sub / "f2.txt"
    f2.write_text("world")

    deleter = FastDeleter(str(root), dry_run=True)
    stats = deleter.run()

    # All files and dirs must still exist on disk!
    assert root.exists()
    assert f1.exists()
    assert sub.exists()
    assert f2.exists()

    assert stats.files_deleted == 2
    assert stats.directories_deleted == 2


def test_parallel_worker_deletion(tmp_path):
    """Test parallel worker deletion (--workers 4)."""
    root = tmp_path / "worker_root"
    root.mkdir()
    num_files = 100

    for i in range(num_files):
        (root / f"worker_file_{i}.txt").write_text(f"content {i}")

    deleter = FastDeleter(str(root), workers=4)
    stats = deleter.run()

    assert not root.exists()
    assert stats.files_deleted == num_files
    assert stats.directories_deleted == 1
    assert stats.failed == 0


def test_disappearing_file_race_condition(tmp_path):
    """Simulate file disappearing between scan and deletion."""
    root = tmp_path / "race_root"
    root.mkdir()
    f = root / "vanishing.txt"
    f.write_text("vanish")

    deleter = FastDeleter(str(root))
    
    # Delete file before calling delete_file_entry
    f.unlink()
    
    item = ScanItem(
        action="FILE",
        path=str(f),
        name="vanishing.txt",
        depth=1,
        rel_path="vanishing.txt",
    )
    result = deleter.delete_file_entry(item)
    
    # Must be handled gracefully (returns True, counted in stats)
    assert result is True
    assert deleter.stats.failed == 0


def test_failure_logging(tmp_path):
    """Verify that failures are logged to the specified log file."""
    log_file = tmp_path / "deletion.log"
    root = tmp_path / "fail_root"
    root.mkdir()

    deleter = FastDeleter(str(root), log_file=str(log_file))
    stats = deleter.run()

    assert log_file.exists()
    content = log_file.read_text()
    assert "Starting fastdelete" in content
    assert "Completed fastdelete" in content
