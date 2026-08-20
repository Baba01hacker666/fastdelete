"""
Multi-stage high-performance duplicate file finder and deduplication cleaner.
Uses file size grouping, partial header/footer hashing, and full SHA256 verification.
"""

from __future__ import annotations

import hashlib
import os
import stat
import sys
from collections import defaultdict
from dataclasses import dataclass, field
from pathlib import Path
from typing import Dict, List, Optional, Set, Tuple, Union

from fastdelete.deleter import DeletionStats, FastDeleter
from fastdelete.progress import format_bytes
from fastdelete.safety import safe_path_str


_HASH_CHUNK_SIZE = 64 * 1024
_SAMPLE_SIZE = 4096


def _sample_hash(path: str, size: int) -> str:
    """Read first and last 4KB to create a fast pre-filter signature."""
    h = hashlib.sha256()
    try:
        with open(path, "rb") as f:
            head = f.read(_SAMPLE_SIZE)
            h.update(head)
            if size > _SAMPLE_SIZE * 2:
                f.seek(max(0, size - _SAMPLE_SIZE))
                tail = f.read(_SAMPLE_SIZE)
                h.update(tail)
    except OSError:
        return ""
    return h.hexdigest()


def _full_hash(path: str) -> str:
    """Compute full SHA256 hash of a file."""
    h = hashlib.sha256()
    try:
        with open(path, "rb") as f:
            while chunk := f.read(_HASH_CHUNK_SIZE):
                h.update(chunk)
    except OSError:
        return ""
    return h.hexdigest()


@dataclass
class DuplicateGroup:
    """Group of identical files with identical content."""
    hash: str
    size: int
    paths: List[str]

    @property
    def wasted_bytes(self) -> int:
        """Space wasted by duplicate copies (excluding the primary copy)."""
        return max(0, len(self.paths) - 1) * self.size


@dataclass
class DuplicateReport:
    """Complete summary of detected duplicate files."""
    root_path: str
    groups: List[DuplicateGroup] = field(default_factory=list)
    total_duplicate_files: int = 0
    total_wasted_bytes: int = 0
    scanned_files: int = 0
    elapsed_seconds: float = 0.0

    def to_dict(self) -> dict:
        return {
            "root_path": self.root_path,
            "total_duplicate_files": self.total_duplicate_files,
            "total_wasted_bytes": self.total_wasted_bytes,
            "total_wasted_human": format_bytes(self.total_wasted_bytes),
            "scanned_files": self.scanned_files,
            "elapsed_seconds": self.elapsed_seconds,
            "groups": [
                {
                    "hash": g.hash,
                    "size": g.size,
                    "size_human": format_bytes(g.size),
                    "wasted_bytes": g.wasted_bytes,
                    "paths": g.paths,
                }
                for g in self.groups
            ],
        }


def find_duplicates(
    root_path: Union[str, Path],
    min_size: int = 1,
    max_size: Optional[int] = None,
) -> DuplicateReport:
    """
    Search for duplicate files in root_path using 3-stage progressive hashing.
    """
    import time
    start_time = time.perf_counter()

    root = os.path.abspath(str(root_path))
    report = DuplicateReport(root_path=root)

    # Stage 1: Group by file size
    size_map: Dict[int, List[str]] = defaultdict(list)
    scanned = 0

    for dirpath, _, filenames in os.walk(root):
        for fname in filenames:
            full_p = os.path.join(dirpath, fname)
            try:
                st = os.lstat(full_p)
                if not stat.S_ISREG(st.st_mode) or stat.S_ISLNK(st.st_mode):
                    continue
                sz = st.st_size
                if sz < min_size:
                    continue
                if max_size is not None and sz > max_size:
                    continue
                scanned += 1
                size_map[sz].append(full_p)
            except OSError:
                continue

    report.scanned_files = scanned

    # Candidate sizes (more than 1 file with this size)
    candidate_sizes = {sz: paths for sz, paths in size_map.items() if len(paths) > 1}

    # Stage 2: Partial Sample Hash
    sample_map: Dict[Tuple[int, str], List[str]] = defaultdict(list)
    for sz, paths in candidate_sizes.items():
        for p in paths:
            s_hash = _sample_hash(p, sz)
            if s_hash:
                sample_map[(sz, s_hash)].append(p)

    candidate_samples = {k: paths for k, paths in sample_map.items() if len(paths) > 1}

    # Stage 3: Full SHA256 Hash
    full_map: Dict[Tuple[int, str], List[str]] = defaultdict(list)
    for (sz, _), paths in candidate_samples.items():
        for p in paths:
            f_hash = _full_hash(p)
            if f_hash:
                full_map[(sz, f_hash)].append(p)

    groups: List[DuplicateGroup] = []
    total_wasted = 0
    total_dupes = 0

    for (sz, f_hash), paths in full_map.items():
        if len(paths) > 1:
            group = DuplicateGroup(hash=f_hash, size=sz, paths=paths)
            groups.append(group)
            total_dupes += len(paths) - 1
            total_wasted += group.wasted_bytes

    # Sort groups by wasted bytes descending
    groups.sort(key=lambda g: g.wasted_bytes, reverse=True)

    report.groups = groups
    report.total_duplicate_files = total_dupes
    report.total_wasted_bytes = total_wasted
    report.elapsed_seconds = max(0.001, time.perf_counter() - start_time)
    return report


def render_duplicates_report(report: DuplicateReport, stream=None) -> str:
    """Render human-readable duplicate report for terminal."""
    stream = stream or sys.stdout
    lines = []

    banner = "=" * 70
    divider = "-" * 70

    lines.append(banner)
    lines.append(f" DUPLICATE FILES REPORT: {safe_path_str(report.root_path)}")
    lines.append(divider)
    lines.append(f" Total Scanned Files:   {report.scanned_files:,}")
    lines.append(f" Duplicate Groups:      {len(report.groups):,}")
    lines.append(f" Redundant Files:       {report.total_duplicate_files:,}")
    lines.append(f" Potential Space Saved: {format_bytes(report.total_wasted_bytes)}")
    lines.append(f" Search Time:           {report.elapsed_seconds:.3f}s")
    lines.append(divider)

    if not report.groups:
        lines.append("  No duplicate files found.")
        lines.append(banner)
        return "\n".join(lines)

    lines.append(" DUPLICATE SETS (Top 10):")
    for i, grp in enumerate(report.groups[:10], 1):
        lines.append(f"\n Group #{i} - {len(grp.paths)} copies | {format_bytes(grp.size)} each | Wasted: {format_bytes(grp.wasted_bytes)}")
        for idx, p in enumerate(grp.paths):
            rel = os.path.relpath(p, report.root_path)
            tag = "  [KEEP] " if idx == 0 else "  [DUPE] "
            lines.append(f"  {tag} {safe_path_str(rel)}")

    lines.append(banner)
    return "\n".join(lines)


def clean_duplicates(
    report: DuplicateReport,
    keep_strategy: str = "first",  # 'first', 'newest', 'oldest'
    action: str = "delete",         # 'delete', 'dry-run', 'hardlink'
) -> DeletionStats:
    """
    Remove or hardlink duplicate files in report according to keep_strategy.
    """
    stats = DeletionStats()

    for group in report.groups:
        paths = list(group.paths)

        if keep_strategy == "newest":
            paths.sort(key=lambda p: os.path.getmtime(p), reverse=True)
        elif keep_strategy == "oldest":
            paths.sort(key=lambda p: os.path.getmtime(p))

        primary = paths[0]
        duplicates_to_process = paths[1:]

        for dupe_path in duplicates_to_process:
            stats.files_discovered += 1

            if action == "dry-run":
                stats.files_deleted += 1
                stats.bytes_deleted += group.size
            elif action == "hardlink":
                try:
                    # Remove dupe and link to primary
                    os.unlink(dupe_path)
                    os.link(primary, dupe_path)
                    stats.files_deleted += 1
                    stats.bytes_deleted += group.size
                except OSError:
                    stats.failed += 1
            else:
                # Actual delete
                deleter = FastDeleter(dupe_path)
                st = deleter.run()
                stats.files_deleted += st.files_deleted
                stats.bytes_deleted += st.bytes_deleted
                stats.failed += st.failed

    return stats
