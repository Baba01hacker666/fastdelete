"""
High-level public Python API for fastdelete.
Provides simple, intuitive functions for synchronous and asynchronous deletion,
secure shredding, trash bin operations, preset cleanups, disk space analysis, and duplicate detection.
"""

from __future__ import annotations

import asyncio
from pathlib import Path
from typing import Any, Callable, Dict, Optional, Sequence, Union

from fastdelete.analyzer import DiskUsageSummary, analyze_directory
from fastdelete.deleter import DeletionStats, FastDeleter
from fastdelete.duplicates import DuplicateReport, find_duplicates
from fastdelete.filters import DeletionFilter
from fastdelete.presets import run_preset_clean
from fastdelete.progress import ProgressReporter
from fastdelete.safety import inspect_target, validate_safety
from fastdelete.shredder import ShredMethod
from fastdelete.trash import TrashItem, move_to_trash, restore_trash_item


def delete(
    target: Union[str, Path],
    *,
    dry_run: bool = False,
    force: bool = False,
    workers: int = 1,
    filter: Optional[DeletionFilter] = None,
    shred: bool = False,
    shred_method: Union[ShredMethod, str] = ShredMethod.DOD,
    shred_passes: Optional[int] = None,
    trash: bool = False,
    allow_root: bool = False,
    allow_home: bool = False,
    quiet: bool = True,
    verbose: bool = False,
    delete_root_dir: bool = True,
    log_file: Optional[str] = None,
    callback: Optional[Callable[[Dict[str, Any]], None]] = None,
) -> DeletionStats:
    """
    Delete a file or directory tree safely and with high performance.

    Args:
        target: File or directory path to delete.
        dry_run: If True, simulate deletion without touching disk.
        force: If True, reset permissions on read-only files before unlinking.
        workers: Number of parallel worker threads (default: 1).
        filter: Optional DeletionFilter with glob, regex, size, or time criteria.
        shred: If True, securely overwrite file contents before unlinking.
        shred_method: Wiping algorithm ('zero', 'random', 'dod', 'gutmann').
        shred_passes: Number of overwrite passes.
        trash: If True, move to FreeDesktop/OS Trash instead of unlinking.
        allow_root: Allow deleting filesystem root or protected system directories.
        allow_home: Allow deleting user home directory.
        quiet: Suppress terminal progress output.
        verbose: Print detailed action lines for each item.
        delete_root_dir: If True, delete the root directory itself when deleting a tree.
        log_file: Optional path to append error logs.
        callback: Event listener receiving live dictionary events.

    Returns:
        DeletionStats object with total items deleted, bytes freed, and elapsed time.
    """
    target_str = str(target)
    identity = inspect_target(target_str)
    validate_safety(identity, allow_root=allow_root, allow_home=allow_home)

    progress = None
    if not quiet or verbose:
        progress = ProgressReporter(
            target_path=identity.abs_path,
            quiet=quiet,
            verbose=verbose,
            dry_run=dry_run,
        )

    deleter = FastDeleter(
        target_path=identity.abs_path,
        dry_run=dry_run,
        force=force,
        workers=workers,
        deletion_filter=filter,
        progress_reporter=progress,
        log_file=log_file,
        delete_root_dir=delete_root_dir,
        shred=shred,
        shred_method=shred_method,
        shred_passes=shred_passes,
        trash=trash,
        event_callback=callback,
    )

    return deleter.run()


def delete_many(
    targets: Sequence[Union[str, Path]],
    *,
    dry_run: bool = False,
    force: bool = False,
    workers: int = 1,
    filter: Optional[DeletionFilter] = None,
    shred: bool = False,
    shred_method: Union[ShredMethod, str] = ShredMethod.DOD,
    trash: bool = False,
    allow_root: bool = False,
    allow_home: bool = False,
    quiet: bool = True,
) -> DeletionStats:
    """
    Delete multiple files or directory paths in sequence.
    Returns cumulative DeletionStats.
    """
    combined = DeletionStats()

    for target in targets:
        st = delete(
            target=target,
            dry_run=dry_run,
            force=force,
            workers=workers,
            filter=filter,
            shred=shred,
            shred_method=shred_method,
            trash=trash,
            allow_root=allow_root,
            allow_home=allow_home,
            quiet=quiet,
        )
        combined.files_discovered += st.files_discovered
        combined.files_deleted += st.files_deleted
        combined.directories_deleted += st.directories_deleted
        combined.symlinks_deleted += st.symlinks_deleted
        combined.bytes_deleted += st.bytes_deleted
        combined.skipped += st.skipped
        combined.failed += st.failed
        combined.symlinks_skipped += st.symlinks_skipped
        combined.errors.extend(st.errors)

    return combined


async def delete_async(
    target: Union[str, Path],
    **kwargs: Any,
) -> DeletionStats:
    """
    Asynchronously delete a target in a worker thread.
    Non-blocking for use in asyncio event loops (FastAPI, aiohttp, Celery, etc.).
    """
    loop = asyncio.get_running_loop()
    return await loop.run_in_executor(None, lambda: delete(target, **kwargs))


def shred(
    target: Union[str, Path],
    passes: int = 3,
    method: Union[ShredMethod, str] = ShredMethod.DOD,
    **kwargs: Any,
) -> DeletionStats:
    """
    Convenience wrapper to securely shred a target with multi-pass wiping.
    """
    return delete(
        target=target,
        shred=True,
        shred_method=method,
        shred_passes=passes,
        **kwargs,
    )


def trash(target: Union[str, Path]) -> TrashItem:
    """
    Convenience wrapper to safely move a file or folder to the Trash bin.
    """
    return move_to_trash(target)


def restore(item_id_or_name: str, destination: Optional[Union[str, Path]] = None) -> str:
    """
    Restore an item from the Trash bin.
    """
    return restore_trash_item(item_id_or_name, destination=destination)


def clean(
    preset_name: str,
    root_path: Union[str, Path] = ".",
    **kwargs: Any,
) -> DeletionStats:
    """
    Execute a workspace cleaner preset (e.g. 'python', 'node', 'rust', 'c', 'temp', 'logs').
    """
    return run_preset_clean(preset_name=preset_name, root_path=root_path, **kwargs)


def analyze(
    target: Union[str, Path],
    top_n: int = 10,
    max_depth: Optional[int] = None,
) -> DiskUsageSummary:
    """
    Analyze recursive disk space consumption of target.
    """
    return analyze_directory(target, top_n=top_n, max_depth=max_depth)


def duplicates(
    target: Union[str, Path],
    min_size: int = 1,
    max_size: Optional[int] = None,
) -> DuplicateReport:
    """
    Find duplicate files in target directory.
    """
    return find_duplicates(target, min_size=min_size, max_size=max_size)
