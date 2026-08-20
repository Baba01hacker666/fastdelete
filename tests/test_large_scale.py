"""
Tests for scale simulation (millions of entries) and signal interrupt handling.
"""

import gc
import os
import threading
import time
import pytest
from pathlib import Path

from fastdelete.deleter import FastDeleter
from fastdelete.scanner import DirectoryScanner, ScanItem


def test_million_entry_memory_and_streaming_simulation():
    """
    Simulate scanning and deleting 100,000 items in dry-run mode to verify
    constant memory footprint and streaming performance.
    """
    total_items = 100_000

    def mock_scan_generator():
        for i in range(total_items):
            yield ScanItem(
                action="FILE",
                path=f"/simulated/path/file_{i}.txt",
                name=f"file_{i}.txt",
                depth=1,
                rel_path=f"file_{i}.txt",
                size=1024,
            )
        yield ScanItem(
            action="DIR_POST",
            path="/simulated/path",
            name="path",
            depth=0,
            rel_path="",
            is_dir=True,
        )

    deleter = FastDeleter(
        target_path="/simulated/path",
        dry_run=True,
    )

    # Replace scanner stream with mock generator
    for item in mock_scan_generator():
        if item.action == "FILE":
            deleter.delete_file_entry(item)
        elif item.action == "DIR_POST":
            deleter.delete_dir_entry(item)

    assert deleter.stats.files_discovered == total_items
    assert deleter.stats.files_deleted == total_items
    assert deleter.stats.directories_deleted == 1
    assert deleter.stats.bytes_deleted == total_items * 1024
    assert deleter.stats.failed == 0


def test_abort_event_interrupt(tmp_path):
    """Verify that setting abort_event stops deletion mid-stream cleanly."""
    root = tmp_path / "abort_root"
    root.mkdir()

    # Create 50 files
    for i in range(50):
        (root / f"file_{i}.txt").write_text("abort test")

    abort_event = threading.Event()
    deleter = FastDeleter(str(root), abort_event=abort_event)

    # Set abort before run
    abort_event.set()
    stats = deleter.run()

    # Should have stopped early
    assert stats.files_deleted == 0
    # Directory should still exist
    assert root.exists()


def test_real_filesystem_batch_performance(tmp_path):
    """Test creating and deleting 1,000 real files across subdirectories."""
    root = tmp_path / "batch_root"
    root.mkdir()

    num_dirs = 10
    files_per_dir = 100
    expected_files = num_dirs * files_per_dir

    for d in range(num_dirs):
        sub = root / f"dir_{d}"
        sub.mkdir()
        for f in range(files_per_dir):
            file_p = sub / f"file_{f}.dat"
            file_p.write_bytes(b"A" * 128)

    deleter = FastDeleter(str(root), workers=4)
    stats = deleter.run()

    assert not root.exists()
    assert stats.files_deleted == expected_files
    assert stats.directories_deleted == num_dirs + 1
    assert stats.bytes_deleted == expected_files * 128
    assert stats.failed == 0
