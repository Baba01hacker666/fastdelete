"""
Tests for iterative directory scanner and deep tree traversal.
"""

import os
import pytest
from pathlib import Path

from fastdelete.filters import DeletionFilter
from fastdelete.scanner import DirectoryScanner


def test_scanner_post_order(tmp_path):
    """Verify that scanner yields files before their containing directories."""
    sub = tmp_path / "subdir"
    sub.mkdir()
    f1 = sub / "file1.txt"
    f1.write_text("hello")
    f2 = tmp_path / "root_file.txt"
    f2.write_text("root")

    scanner = DirectoryScanner(str(tmp_path), delete_root_dir=True)
    items = list(scanner.scan())

    action_paths = [(item.action, item.path) for item in items]
    
    # f1 must appear before subdir DIR_POST
    f1_idx = next(i for i, (act, p) in enumerate(action_paths) if p == str(f1))
    sub_idx = next(i for i, (act, p) in enumerate(action_paths) if p == str(sub) and act == "DIR_POST")
    root_idx = next(i for i, (act, p) in enumerate(action_paths) if p == str(tmp_path) and act == "DIR_POST")

    assert f1_idx < sub_idx
    assert sub_idx < root_idx


def test_scanner_does_not_traverse_directory_symlinks(tmp_path):
    """Verify that directory symlinks are never traversed recursively."""
    real_dir = tmp_path / "real_dir"
    real_dir.mkdir()
    secret_file = real_dir / "secret.txt"
    secret_file.write_text("secret")

    scan_root = tmp_path / "scan_root"
    scan_root.mkdir()
    link_to_real = scan_root / "link_dir"
    link_to_real.symlink_to(real_dir)

    scanner = DirectoryScanner(str(scan_root), delete_root_dir=False)
    items = list(scanner.scan())

    paths = [item.path for item in items]
    assert str(link_to_real) in paths
    # secret_file inside real_dir MUST NOT be in scanned paths
    assert str(secret_file) not in paths

    # The link should be emitted as a FILE action with is_symlink=True
    link_item = next(item for item in items if item.path == str(link_to_real))
    assert link_item.action == "FILE"
    assert link_item.is_symlink is True


def test_scanner_deep_tree(tmp_path):
    """
    Test scanning a deeply nested directory tree (depth=100)
    to ensure no RecursionError occurs.
    """
    depth = 100
    curr = tmp_path
    for i in range(depth):
        curr = curr / f"d_{i}"
        curr.mkdir()
        f = curr / "f.txt"
        f.write_text("x")

    scanner = DirectoryScanner(str(tmp_path), delete_root_dir=True)
    items = list(scanner.scan())

    file_items = [it for it in items if it.action == "FILE"]
    dir_items = [it for it in items if it.action == "DIR_POST"]

    assert len(file_items) == depth
    assert len(dir_items) == depth + 1  # depth subdirs + root


def test_scanner_exclude_filter(tmp_path):
    """Test that excluded subdirectories are not traversed."""
    keep_dir = tmp_path / "keep"
    keep_dir.mkdir()
    (keep_dir / "keep.txt").write_text("keep")

    skip_dir = tmp_path / "skip_me"
    skip_dir.mkdir()
    (skip_dir / "hidden.txt").write_text("hidden")

    filt = DeletionFilter(exclude_patterns=["skip_me*"])
    scanner = DirectoryScanner(str(tmp_path), deletion_filter=filt)
    items = list(scanner.scan())

    paths = [it.path for it in items]
    assert str(keep_dir / "keep.txt") in paths
    assert str(skip_dir / "hidden.txt") not in paths

    skip_item = next(it for it in items if it.path == str(skip_dir))
    assert skip_item.action == "DIR_SKIP"
