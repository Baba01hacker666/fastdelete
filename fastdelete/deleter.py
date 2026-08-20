"""
Core deletion engine for fastdelete supporting single-thread, worker-pool, native C, shred, and trash modes.
"""

from __future__ import annotations

import asyncio
import ctypes
import errno
import json
import os
import stat
import sys
import threading
import time
from concurrent.futures import ThreadPoolExecutor, as_completed
from ctypes import POINTER, Structure, byref, c_char_p, c_int, c_uint64
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Callable, Dict, List, Optional

from fastdelete.errors import DeletionErrorRecord, PathChangedError
from fastdelete.filters import DeletionFilter
from fastdelete.progress import ProgressReporter, format_bytes
from fastdelete.safety import (
    TargetIdentity,
    inspect_target,
    normalize_long_path,
    safe_path_str,
)
from fastdelete.scanner import DirectoryScanner, ScanItem
from fastdelete.shredder import ShredMethod, shred_file
from fastdelete.trash import move_to_trash


class _CDeleteStats(Structure):
    # Must match CDeleteStats in c_engine.c (append-only for ABI safety).
    _fields_ = [
        ("files_discovered", c_uint64),
        ("files_deleted", c_uint64),
        ("dirs_deleted", c_uint64),
        ("bytes_deleted", c_uint64),
        ("skipped", c_uint64),
        ("failed", c_uint64),
        ("symlinks_deleted", c_uint64),
        ("symlinks_skipped", c_uint64),
    ]


# Cap the number of retained error records so a pathological failure storm
# (millions of failed entries) cannot exhaust memory; failures still counted.
MAX_KEPT_ERROR_RECORDS = 1000


_C_LIB = None

def get_c_engine():
    global _C_LIB
    if _C_LIB is not None:
        return _C_LIB

    lib_path = Path(__file__).resolve().parent / "_fastdelete_c.so"
    if lib_path.exists():
        try:
            lib = ctypes.CDLL(str(lib_path))
            lib.c_fastdelete_tree.argtypes = [
                c_char_p,
                c_int,
                c_int,
                c_int,
                c_int,
                c_int,
                POINTER(c_int),
                POINTER(_CDeleteStats),
            ]
            lib.c_fastdelete_tree.restype = c_int
            _C_LIB = lib
            return _C_LIB
        except Exception:
            return None
    return None


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

    def rate_items_per_second(self) -> float:
        return self.total_deleted() / self.elapsed_seconds()

    def to_dict(self) -> Dict[str, Any]:
        return {
            "files_discovered": self.files_discovered,
            "files_deleted": self.files_deleted,
            "directories_deleted": self.directories_deleted,
            "symlinks_deleted": self.symlinks_deleted,
            "total_deleted": self.total_deleted(),
            "bytes_deleted": self.bytes_deleted,
            "bytes_deleted_human": format_bytes(self.bytes_deleted),
            "skipped": self.skipped,
            "failed": self.failed,
            "symlinks_skipped": self.symlinks_skipped,
            "elapsed_seconds": round(self.elapsed_seconds(), 4),
            "rate_items_per_second": round(self.rate_items_per_second(), 2),
            "errors": [
                {
                    "timestamp": e.timestamp,
                    "path": e.path,
                    "operation": e.operation,
                    "exception_class": e.exception_class,
                    "error_message": e.error_message,
                    "errno": e.errno,
                }
                for e in self.errors
            ],
        }

    def to_json(self, indent: Optional[int] = None) -> str:
        return json.dumps(self.to_dict(), indent=indent)


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
        use_c_engine: bool = True,
        shred: bool = False,
        shred_method: Union[ShredMethod, str] = ShredMethod.DOD,
        shred_passes: Optional[int] = None,
        trash: bool = False,
        event_callback: Optional[Callable[[Dict[str, Any]], None]] = None,
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
        self._c_abort_flag = ctypes.c_int(0)
        self.use_c_engine = use_c_engine and not shred and not trash
        self.shred = shred
        self.shred_method = shred_method
        self.shred_passes = shred_passes
        self.trash = trash
        self.event_callback = event_callback
        self.stats = DeletionStats()
        self._stats_lock = threading.Lock()
        self._log_lock = threading.Lock()
        self._target_identity: Optional[TargetIdentity] = None

    def request_abort(self) -> None:
        """Signal a clean abort. Safe to call from a signal handler."""
        self.abort_event.set()
        self._c_abort_flag.value = 1

    def _dispatch_event(self, event_type: str, data: Dict[str, Any]) -> None:
        """Emit structured event for streaming / machine-readable observers."""
        if self.event_callback:
            try:
                payload = {"event": event_type, "timestamp": time.time(), **data}
                self.event_callback(payload)
            except Exception:
                pass

    def _log_error_record(self, record: DeletionErrorRecord) -> None:
        """Record an error and optionally append to log file."""
        with self._stats_lock:
            self.stats.failed += 1
            if len(self.stats.errors) < MAX_KEPT_ERROR_RECORDS:
                self.stats.errors.append(record)

        self._dispatch_event("error", {
            "path": record.path,
            "operation": record.operation,
            "error": record.error_message,
        })

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
        """Attempt to fix permissions blocking deletion of path."""
        norm_path = normalize_long_path(path)
        changed = False
        try:
            st = os.lstat(norm_path)
            if not stat.S_ISLNK(st.st_mode):
                new_mode = st.st_mode | stat.S_IWUSR | stat.S_IRUSR
                if stat.S_ISDIR(st.st_mode):
                    new_mode |= stat.S_IXUSR
                os.chmod(norm_path, new_mode)
                changed = True
        except Exception:
            pass

        parent = os.path.dirname(norm_path.rstrip(os.sep)) or os.sep
        try:
            pst = os.lstat(parent)
            if not stat.S_ISLNK(pst.st_mode):
                os.chmod(
                    parent,
                    pst.st_mode | stat.S_IWUSR | stat.S_IRUSR | stat.S_IXUSR,
                )
                changed = True
        except Exception:
            pass
        return changed

    def delete_file_entry(self, item: ScanItem) -> bool:
        """
        Delete a single file, symlink, or special object.
        Supports standard unlinking, secure multi-pass shredding, and trash bin.
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
                action_name = "SHRED" if self.shred else "UNLINK"
                self.progress.print_verbose(action_name, item.path, f"size={item.size}")
            self._dispatch_event("file_deleted", {"path": item.path, "size": item.size, "dry_run": True})
            return True

        # Shred mode
        if self.shred and not item.is_symlink:
            try:
                shredded_bytes = shred_file(
                    path,
                    method=self.shred_method,
                    passes=self.shred_passes,
                )
                with self._stats_lock:
                    self.stats.files_deleted += 1
                    self.stats.bytes_deleted += max(item.size, shredded_bytes)
                if self.progress:
                    self.progress.print_verbose("SHRED", item.path)
                self._dispatch_event("file_deleted", {"path": item.path, "size": item.size, "shred": True})
                return True
            except Exception as e:
                record = DeletionErrorRecord.from_exception(item.path, "shred", e)
                self._log_error_record(record)
                return False

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
            self._dispatch_event("file_deleted", {"path": item.path, "size": item.size})
            return True
        except FileNotFoundError:
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
                    self._dispatch_event("file_deleted", {"path": item.path, "size": item.size, "forced": True})
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
        """
        if self.abort_event.is_set():
            return False

        if (
            item.depth == 0
            and not self.dry_run
            and self._target_identity is not None
        ):
            unchanged, reason = self._target_identity.verify_unchanged(item.path)
            if not unchanged:
                record = DeletionErrorRecord.from_exception(
                    item.path,
                    "rmdir",
                    PathChangedError(
                        f"Refusing to remove root directory: {reason}"
                    ),
                )
                self._log_error_record(record)
                return False

        path = normalize_long_path(item.path)

        if self.dry_run:
            with self._stats_lock:
                self.stats.directories_deleted += 1
            if self.progress:
                self.progress.print_verbose("RMDIR", item.path)
            self._dispatch_event("dir_deleted", {"path": item.path, "dry_run": True})
            return True

        try:
            os.rmdir(path)
            with self._stats_lock:
                self.stats.directories_deleted += 1
            if self.progress:
                self.progress.print_verbose("RMDIR", item.path)
            self._dispatch_event("dir_deleted", {"path": item.path})
            return True
        except FileNotFoundError:
            with self._stats_lock:
                self.stats.directories_deleted += 1
            return True
        except OSError as e:
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
                    self._dispatch_event("dir_deleted", {"path": item.path, "forced": True})
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
        Execute the deletion operation synchronously.
        Returns the final DeletionStats.
        """
        self.stats.start_time = time.time()
        self._dispatch_event("start", {"target": self.abs_target_path, "dry_run": self.dry_run})

        if self.log_file:
            self._log_message(
                f"[{time.strftime('%Y-%m-%dT%H:%M:%SZ', time.gmtime())}] Starting fastdelete on "
                f"{safe_path_str(self.abs_target_path)} (dry_run={self.dry_run}, workers={self.workers}, force={self.force})"
            )

        # Trash handling: if trash is requested, move entire target to trash
        if self.trash:
            try:
                if self.dry_run:
                    self.stats.files_discovered = 1
                    self.stats.files_deleted = 1
                else:
                    trash_item = move_to_trash(self.abs_target_path)
                    self.stats.files_discovered = 1
                    if trash_item.is_dir:
                        self.stats.directories_deleted = 1
                    else:
                        self.stats.files_deleted = 1
                    self.stats.bytes_deleted = trash_item.size
                self.stats.end_time = time.time()
                self._finish_progress_and_log()
                return self.stats
            except Exception as e:
                record = DeletionErrorRecord.from_exception(self.abs_target_path, "trash", e)
                self._log_error_record(record)
                self.stats.end_time = time.time()
                return self.stats

        # Pre-execution target inspection
        try:
            self._target_identity = inspect_target(self.abs_target_path)
        except Exception as e:
            record = DeletionErrorRecord.from_exception(self.abs_target_path, "inspect", e)
            self._log_error_record(record)
            self.stats.end_time = time.time()
            return self.stats

        # Single file / symlink target
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

        c_engine = get_c_engine() if self.use_c_engine else None
        can_use_c = (
            c_engine is not None
            and not self.filter.has_filters()
            and not (self.progress and self.progress.verbose)
        )

        if can_use_c:
            self._run_c_engine(c_engine)
        elif self.workers > 1:
            self._run_parallel(scanner)
        else:
            self._run_sequential(scanner)

        self.stats.end_time = time.time()
        self._finish_progress_and_log()
        return self.stats

    async def run_async(self) -> DeletionStats:
        """Asynchronously execute deletion in a background thread."""
        loop = asyncio.get_running_loop()
        return await loop.run_in_executor(None, self.run)

    def _run_c_engine(self, c_engine) -> None:
        """Execute native compiled C acceleration engine."""
        c_stats = _CDeleteStats()
        self._c_abort_flag.value = 1 if self.abort_event.is_set() else 0
        max_d = self.filter.max_depth if self.filter.max_depth is not None else 0

        target_bytes = self.abs_target_path.encode("utf-8", errors="surrogateescape")
        ret = c_engine.c_fastdelete_tree(
            target_bytes,
            1 if self.dry_run else 0,
            1 if self.force else 0,
            1 if self.filter.one_file_system else 0,
            max_d,
            1 if self.delete_root_dir else 0,
            ctypes.byref(self._c_abort_flag),
            ctypes.byref(c_stats),
        )

        with self._stats_lock:
            self.stats.files_discovered = c_stats.files_discovered
            self.stats.files_deleted = c_stats.files_deleted
            self.stats.directories_deleted = c_stats.dirs_deleted
            self.stats.bytes_deleted = c_stats.bytes_deleted
            self.stats.skipped = c_stats.skipped
            self.stats.failed = c_stats.failed
            self.stats.symlinks_deleted = c_stats.symlinks_deleted
            self.stats.symlinks_skipped = c_stats.symlinks_skipped

        if self.progress:
            self.progress.update(
                files_discovered=self.stats.files_discovered,
                files_deleted=self.stats.files_deleted,
                dirs_deleted=self.stats.directories_deleted,
                failed=self.stats.failed,
                skipped=self.stats.skipped,
                bytes_deleted=self.stats.bytes_deleted,
                force=True,
            )

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
        """Multi-threaded worker pool execution."""
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

        self._dispatch_event("summary", {"stats": self.stats.to_dict()})

        if self.log_file:
            summary_msg = (
                f"[{time.strftime('%Y-%m-%dT%H:%M:%SZ', time.gmtime())}] Completed fastdelete on {safe_path_str(self.abs_target_path)}: "
                f"Discovered={self.stats.files_discovered}, FilesDeleted={self.stats.files_deleted}, "
                f"DirsDeleted={self.stats.directories_deleted}, Bytes={self.stats.bytes_deleted}, "
                f"Failed={self.stats.failed}, Skipped={self.stats.skipped}, "
                f"Elapsed={self.stats.elapsed_seconds():.2f}s"
            )
            self._log_message(summary_msg)
