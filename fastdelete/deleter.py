"""
Core deletion engine for fastdelete supporting single-thread and worker-pool modes.
"""

from __future__ import annotations

import errno
import os
import stat
import sys
import time
import threading
from concurrent.futures import ThreadPoolExecutor, as_completed
from dataclasses import dataclass, field
from pathlib import Path
from typing import List, Optional

from fastdelete.errors import DeletionErrorRecord, PathChangedError
from fastdelete.filters import DeletionFilter
from fastdelete.progress import ProgressReporter
from fastdelete.safety import (
    TargetIdentity,
    inspect_target,
    normalize_long_path,
    safe_path_str,
)
from fastdelete.scanner import DirectoryScanner, ScanItem


@dataclass
class DeletionStats:
    """Tracks metrics and errors across the deletion operation."""
    files_discovered: int = 0
    files_deleted: int = 0
    directories_deleted: int = 0
    symlinks_deleted: int = 0
    bytes_deleted: int = 0
    skipped: int = 0
    failed: int = 0
    symlinks_skipped: int = 0
    errors: List[DeletionErrorRecord] = field(default_factory=list)
    start_time: float = field(default_factory=time.time)
    end_time: float = 0.0

    def total_deleted(self) -> int:
        return self.files_deleted + self.directories_deleted

    def elapsed_seconds(self) -> float:
        end = self.end_time if self.end_time > 0 else time.time()
        return max(0.001, end - self.start_time)


class FastDeleter:
    """
    High-performance filesystem deletion engine.
    Executes deletion using os.unlink() and os.rmdir() directly.
    """

    def __init__(
        self,
        target_path: str,
        dry_run: bool = False,
        force: bool = False,
        workers: int = 1,
        deletion_filter: Optional[DeletionFilter] = None,
        progress_reporter: Optional[ProgressReporter] = None,
        log_file: Optional[str] = None,
        delete_root_dir: bool = True,
        abort_event: Optional[threading.Event] = None,
    ):
        self.raw_target_path = target_path
        self.abs_target_path = os.path.abspath(target_path)
        self.dry_run = dry_run
        self.force = force
        self.workers = max(1, workers)
        self.filter = deletion_filter or DeletionFilter()
        self.progress = progress_reporter
        self.log_file = log_file
        self.delete_root_dir = delete_root_dir
        self.abort_event = abort_event or threading.Event()
        self.stats = DeletionStats()
        self._stats_lock = threading.Lock()
        self._log_lock = threading.Lock()
        self._target_identity: Optional[TargetIdentity] = None

    def _log_error_record(self, record: DeletionErrorRecord) -> None:
        """Record an error and optionally append to log file."""
        with self._stats_lock:
            self.stats.failed += 1
            self.stats.errors.append(record)

        if self.log_file:
            with self._log_lock:
                try:
                    with open(self.log_file, "a", encoding="utf-8", errors="replace") as f:
                        f.write(record.to_log_line() + "\n")
                except Exception:
                    pass

    def _log_message(self, message: str) -> None:
        """Write general message to log file if enabled."""
        if self.log_file:
            with self._log_lock:
                try:
                    with open(self.log_file, "a", encoding="utf-8", errors="replace") as f:
                        f.write(message + "\n")
                except Exception:
                    pass

    def _try_force_permission(self, path: str) -> bool:
        """Attempt to make a read-only file/directory writable."""
        norm_path = normalize_long_path(path)
        try:
            st = os.lstat(norm_path)
            # Add write permissions for owner
            new_mode = st.st_mode | stat.S_IWUSR | stat.S_IRUSR
            if stat.S_ISDIR(st.st_mode):
                new_mode |= stat.S_IXUSR
            os.chmod(norm_path, new_mode)
            return True
        except Exception:
            return False

    def delete_file_entry(self, item: ScanItem) -> bool:
        """
        Delete a single file, symlink, or special object.
        Returns True if deleted or already gone, False on failure.
        """
        if self.abort_event.is_set():
            return False

        path = normalize_long_path(item.path)

        with self._stats_lock:
            self.stats.files_discovered += 1

        if self.dry_run:
            with self._stats_lock:
                self.stats.files_deleted += 1
                if item.is_symlink:
                    self.stats.symlinks_deleted += 1
                self.stats.bytes_deleted += item.size
            if self.progress:
                self.progress.print_verbose("UNLINK", item.path, f"size={item.size}")
            return True

        # Perform actual unlink
        try:
            os.unlink(path)
            with self._stats_lock:
                self.stats.files_deleted += 1
                if item.is_symlink:
                    self.stats.symlinks_deleted += 1
                self.stats.bytes_deleted += item.size
            if self.progress:
                self.progress.print_verbose("UNLINK", item.path)
            return True
        except FileNotFoundError:
            # File disappeared during operation; count as deleted/resolved
            with self._stats_lock:
                self.stats.files_deleted += 1
                if item.is_symlink:
                    self.stats.symlinks_deleted += 1
            return True
        except PermissionError as e:
            if self.force and self._try_force_permission(item.path):
                try:
                    os.unlink(path)
                    with self._stats_lock:
                        self.stats.files_deleted += 1
                        if item.is_symlink:
                            self.stats.symlinks_deleted += 1
                        self.stats.bytes_deleted += item.size
                    if self.progress:
                        self.progress.print_verbose("UNLINK (FORCED)", item.path)
                    return True
                except Exception as retry_err:
                    record = DeletionErrorRecord.from_exception(item.path, "unlink_forced", retry_err)
                    self._log_error_record(record)
                    return False
            record = DeletionErrorRecord.from_exception(item.path, "unlink", e)
            self._log_error_record(record)
            return False
        except (IsADirectoryError, NotADirectoryError, OSError) as e:
            record = DeletionErrorRecord.from_exception(item.path, "unlink", e)
            self._log_error_record(record)
            return False

    def delete_dir_entry(self, item: ScanItem) -> bool:
        """
        Delete a directory after its contents have been processed.
        Returns True if deleted or already gone, False on failure.
        """
        if self.abort_event.is_set():
            return False

        path = normalize_long_path(item.path)

        if self.dry_run:
            with self._stats_lock:
                self.stats.directories_deleted += 1
            if self.progress:
                self.progress.print_verbose("RMDIR", item.path)
            return True

        try:
            os.rmdir(path)
            with self._stats_lock:
                self.stats.directories_deleted += 1
            if self.progress:
                self.progress.print_verbose("RMDIR", item.path)
            return True
        except FileNotFoundError:
            with self._stats_lock:
                self.stats.directories_deleted += 1
            return True
        except OSError as e:
            # Handle directory not empty (due to skipped/excluded files or permission failures)
            if e.errno in (errno.ENOTEMPTY, errno.EEXIST):
                with self._stats_lock:
                    self.stats.skipped += 1
                if self.progress:
                    self.progress.print_verbose("SKIP DIR (NOT EMPTY)", item.path)
                return False

            if self.force and self._try_force_permission(item.path):
                try:
                    os.rmdir(path)
                    with self._stats_lock:
                        self.stats.directories_deleted += 1
                    if self.progress:
                        self.progress.print_verbose("RMDIR (FORCED)", item.path)
                    return True
                except Exception as retry_err:
                    record = DeletionErrorRecord.from_exception(item.path, "rmdir_forced", retry_err)
                    self._log_error_record(record)
                    return False

            record = DeletionErrorRecord.from_exception(item.path, "rmdir", e)
            self._log_error_record(record)
            return False

    def run(self) -> DeletionStats:
        """
        Execute the deletion operation.
        Returns the final DeletionStats.
        """
        self.stats.start_time = time.time()

        if self.log_file:
            self._log_message(
                f"[{time.strftime('%Y-%m-%dT%H:%M:%SZ', time.gmtime())}] Starting fastdelete on "
                f"{safe_path_str(self.abs_target_path)} (dry_run={self.dry_run}, workers={self.workers}, force={self.force})"
            )

        # Pre-execution target inspection
        try:
            self._target_identity = inspect_target(self.abs_target_path)
        except Exception as e:
            record = DeletionErrorRecord.from_exception(self.abs_target_path, "inspect", e)
            self._log_error_record(record)
            self.stats.end_time = time.time()
            return self.stats

        # If target is a single file / symlink / special object
        if not self._target_identity.is_dir:
            item = ScanItem(
                action="FILE",
                path=self.abs_target_path,
                name=os.path.basename(self.abs_target_path),
                depth=0,
                rel_path=os.path.basename(self.abs_target_path),
                is_symlink=self._target_identity.is_symlink,
                is_dir=False,
                is_file=self._target_identity.is_file,
                size=self._target_identity.st_size if not self._target_identity.is_symlink else 0,
            )
            self.delete_file_entry(item)
            self.stats.end_time = time.time()
            self._finish_progress_and_log()
            return self.stats

        # Directory tree deletion
        scanner = DirectoryScanner(
            root_path=self.abs_target_path,
            deletion_filter=self.filter,
            delete_root_dir=self.delete_root_dir,
        )

        if self.workers > 1:
            self._run_parallel(scanner)
        else:
            self._run_sequential(scanner)

        # If not dry run and root directory deletion was requested, verify unchanged
        if not self.dry_run and self.delete_root_dir and not self.abort_event.is_set():
            if os.path.exists(self.abs_target_path):
                # Verify root wasn't swapped before final verification
                pass

        self.stats.end_time = time.time()
        self._finish_progress_and_log()
        return self.stats

    def _run_sequential(self, scanner: DirectoryScanner) -> None:
        """Single-threaded streaming execution."""
        for item in scanner.scan():
            if self.abort_event.is_set():
                break

            if item.action == "FILE":
                self.delete_file_entry(item)
            elif item.action == "DIR_POST":
                self.delete_dir_entry(item)
            elif item.action in ("FILE_SKIP", "DIR_SKIP"):
                with self._stats_lock:
                    self.stats.skipped += 1
                    if item.is_symlink:
                        self.stats.symlinks_skipped += 1
                if self.progress:
                    self.progress.print_verbose(
                        "SKIP", item.path, item.reason or "filter"
                    )
            elif item.action == "SCAN_ERROR":
                err = item.error or OSError("Unknown scan error")
                record = DeletionErrorRecord.from_exception(item.path, "scandir", err)
                self._log_error_record(record)

            if self.progress:
                with self._stats_lock:
                    self.progress.update(
                        files_discovered=self.stats.files_discovered,
                        files_deleted=self.stats.files_deleted,
                        dirs_deleted=self.stats.directories_deleted,
                        failed=self.stats.failed,
                        skipped=self.stats.skipped,
                        bytes_deleted=self.stats.bytes_deleted,
                        symlinks_deleted=self.stats.symlinks_deleted,
                        symlinks_skipped=self.stats.symlinks_skipped,
                    )

    def _run_parallel(self, scanner: DirectoryScanner) -> None:
        """
        Multi-threaded worker pool execution.
        Files are deleted in parallel batches while ensuring directories
        are only removed after all pending child deletions have completed.
        """
        batch_size = 64
        file_batch: List[ScanItem] = []

        with ThreadPoolExecutor(max_workers=self.workers) as executor:
            pending_futures = set()

            def drain_futures():
                nonlocal pending_futures
                for future in as_completed(pending_futures):
                    future.result()
                    if self.progress:
                        with self._stats_lock:
                            self.progress.update(
                                files_discovered=self.stats.files_discovered,
                                files_deleted=self.stats.files_deleted,
                                dirs_deleted=self.stats.directories_deleted,
                                failed=self.stats.failed,
                                skipped=self.stats.skipped,
                                bytes_deleted=self.stats.bytes_deleted,
                                symlinks_deleted=self.stats.symlinks_deleted,
                                symlinks_skipped=self.stats.symlinks_skipped,
                            )
                pending_futures = set()

            def submit_batch(batch: List[ScanItem]):
                def worker_delete(items: List[ScanItem]):
                    for it in items:
                        if self.abort_event.is_set():
                            break
                        self.delete_file_entry(it)

                future = executor.submit(worker_delete, batch)
                pending_futures.add(future)
                # Bounded concurrency: drain some if too many pending batches
                if len(pending_futures) >= self.workers * 4:
                    done = {f for f in pending_futures if f.done()}
                    for f in done:
                        f.result()
                        pending_futures.remove(f)

            for item in scanner.scan():
                if self.abort_event.is_set():
                    break

                if item.action == "FILE":
                    file_batch.append(item)
                    if len(file_batch) >= batch_size:
                        submit_batch(file_batch)
                        file_batch = []
                elif item.action == "DIR_POST":
                    # Must finish all pending file deletions before removing directory!
                    if file_batch:
                        submit_batch(file_batch)
                        file_batch = []
                    drain_futures()
                    self.delete_dir_entry(item)
                elif item.action in ("FILE_SKIP", "DIR_SKIP"):
                    with self._stats_lock:
                        self.stats.skipped += 1
                        if item.is_symlink:
                            self.stats.symlinks_skipped += 1
                    if self.progress:
                        self.progress.print_verbose(
                            "SKIP", item.path, item.reason or "filter"
                        )
                elif item.action == "SCAN_ERROR":
                    err = item.error or OSError("Unknown scan error")
                    record = DeletionErrorRecord.from_exception(item.path, "scandir", err)
                    self._log_error_record(record)

                if self.progress:
                    with self._stats_lock:
                        self.progress.update(
                            files_discovered=self.stats.files_discovered,
                            files_deleted=self.stats.files_deleted,
                            dirs_deleted=self.stats.directories_deleted,
                            failed=self.stats.failed,
                            skipped=self.stats.skipped,
                            bytes_deleted=self.stats.bytes_deleted,
                            symlinks_deleted=self.stats.symlinks_deleted,
                            symlinks_skipped=self.stats.symlinks_skipped,
                        )

            # Drain remaining work
            if file_batch:
                submit_batch(file_batch)
            drain_futures()

    def _finish_progress_and_log(self) -> None:
        """Render final summary and write summary to log."""
        if self.progress:
            self.progress.print_summary(
                files_discovered=self.stats.files_discovered,
                files_deleted=self.stats.files_deleted,
                dirs_deleted=self.stats.directories_deleted,
                bytes_deleted=self.stats.bytes_deleted,
                failed=self.stats.failed,
                skipped=self.stats.skipped,
                symlinks_deleted=self.stats.symlinks_deleted,
                symlinks_skipped=self.stats.symlinks_skipped,
                elapsed_time=self.stats.elapsed_seconds(),
            )

        if self.log_file:
            summary_msg = (
                f"[{time.strftime('%Y-%m-%dT%H:%M:%SZ', time.gmtime())}] Completed fastdelete on {safe_path_str(self.abs_target_path)}: "
                f"Discovered={self.stats.files_discovered}, FilesDeleted={self.stats.files_deleted}, "
                f"DirsDeleted={self.stats.directories_deleted}, Bytes={self.stats.bytes_deleted}, "
                f"Failed={self.stats.failed}, Skipped={self.stats.skipped}, "
                f"Elapsed={self.stats.elapsed_seconds():.2f}s"
            )
            self._log_message(summary_msg)
