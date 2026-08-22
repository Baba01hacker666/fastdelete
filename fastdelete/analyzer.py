"""
High-performance disk space analyzer and directory usage tree inspection.
Calculates recursive sizes, finds the largest disk hogs, and analyzes space by extension.
"""

from __future__ import annotations

import heapq
import os
import sys
from collections import defaultdict
from dataclasses import dataclass, field
from pathlib import Path
from typing import Dict, List, Optional, Tuple, Union

from fastdelete.progress import format_bytes
from fastdelete.safety import safe_path_str


@dataclass
class DiskUsageSummary:
    """Detailed breakdown of disk space consumption."""
    target_path: str
    total_bytes: int = 0
    total_files: int = 0
    total_dirs: int = 0
    total_symlinks: int = 0
    largest_files: List[Tuple[str, int]] = field(default_factory=list)
    largest_subdirs: List[Tuple[str, int, int]] = field(default_factory=list)  # (path, bytes, files)
    by_extension: Dict[str, Tuple[int, int]] = field(default_factory=dict)     # ext -> (count, bytes)
    elapsed_seconds: float = 0.0

    def to_dict(self) -> dict:
        return {
            "target_path": self.target_path,
            "total_bytes": self.total_bytes,
            "total_bytes_human": format_bytes(self.total_bytes),
            "total_files": self.total_files,
            "total_dirs": self.total_dirs,
            "total_symlinks": self.total_symlinks,
            "largest_files": [
                {"path": p, "size": s, "size_human": format_bytes(s)}
                for p, s in self.largest_files
            ],
            "largest_subdirs": [
                {"path": p, "size": s, "size_human": format_bytes(s), "files": fc}
                for p, s, fc in self.largest_subdirs
            ],
            "by_extension": {
                ext: {"count": c, "bytes": b, "bytes_human": format_bytes(b)}
                for ext, (c, b) in sorted(self.by_extension.items(), key=lambda x: x[1][1], reverse=True)
            },
            "elapsed_seconds": self.elapsed_seconds,
        }


def analyze_directory(
    target_path: Union[str, Path],
    top_n: int = 10,
    max_depth: Optional[int] = None,
) -> DiskUsageSummary:
    """
    Perform a high-speed traversal of target_path to calculate disk consumption metrics.
    """
    import time
    start_time = time.perf_counter()

    root = os.path.abspath(str(target_path))
    summary = DiskUsageSummary(target_path=root)

    if not os.path.exists(root):
        return summary

    if not os.path.isdir(root) or os.path.islink(root):
        try:
            st = os.lstat(root)
            summary.total_files = 1
            summary.total_bytes = st.st_size
            summary.largest_files.append((root, st.st_size))
        except OSError:
            pass
        summary.elapsed_seconds = max(0.001, time.perf_counter() - start_time)
        return summary

    # Max-heap for largest files: store as (size, path)
    largest_files_heap: List[Tuple[int, str]] = []
    
    # Extension tracking: ext -> [count, total_bytes]
    ext_stats: Dict[str, List[int]] = defaultdict(lambda: [0, 0])

    # Direct subdirectories tracking
    subdir_stats: Dict[str, List[int]] = {}  # subdir_path -> [bytes, files]
    try:
        with os.scandir(root) as it:
            for entry in it:
                if entry.is_dir(follow_symlinks=False):
                    subdir_stats[entry.path] = [0, 0]
    except OSError:
        pass

    # Iterative stack traversal (path, depth, current_toplevel_subdir)
    stack = [(root, 0, None)]

    while stack:
        curr_dir, depth, top_subdir = stack.pop()
        summary.total_dirs += 1

        try:
            with os.scandir(curr_dir) as it:
                for entry in it:
                    try:
                        is_sym = entry.is_symlink()
                    except OSError:
                        is_sym = False

                    if is_sym:
                        summary.total_symlinks += 1
                        continue

                    try:
                        is_dir = entry.is_dir(follow_symlinks=False)
                    except OSError:
                        is_dir = False

                    if is_dir:
                        if max_depth is not None and depth + 1 > max_depth:
                            continue
                        assigned_top = top_subdir if top_subdir is not None else (entry.path if depth == 0 else None)
                        stack.append((entry.path, depth + 1, assigned_top))
                        continue

                    # Regular file / special file
                    try:
                        st = entry.stat(follow_symlinks=False)
                        fsize = st.st_size
                    except OSError:
                        fsize = 0

                    summary.total_files += 1
                    summary.total_bytes += fsize

                    if top_subdir and top_subdir in subdir_stats:
                        subdir_stats[top_subdir][0] += fsize
                        subdir_stats[top_subdir][1] += 1
                    elif depth == 0 and curr_dir == root:
                        # Root-level file
                        pass

                    # Track extensions
                    _, ext = os.path.splitext(entry.name)
                    ext_norm = ext.lower() if ext else "<no extension>"
                    ext_stats[ext_norm][0] += 1
                    ext_stats[ext_norm][1] += fsize

                    # Largest files tracking (keep top_n items)
                    if len(largest_files_heap) < top_n:
                        heapq.heappush(largest_files_heap, (fsize, entry.path))
                    elif fsize > largest_files_heap[0][0]:
                        heapq.heapreplace(largest_files_heap, (fsize, entry.path))

        except (PermissionError, OSError):
            continue

    # Format largest files in descending order
    summary.largest_files = [
        (p, s) for s, p in sorted(largest_files_heap, key=lambda x: x[0], reverse=True)
    ]

    # Format largest direct subdirectories
    subdirs_sorted = sorted(subdir_stats.items(), key=lambda x: x[1][0], reverse=True)[:top_n]
    summary.largest_subdirs = [
        (path, data[0], data[1]) for path, data in subdirs_sorted
    ]

    summary.by_extension = {
        ext: (data[0], data[1]) for ext, data in ext_stats.items()
    }

    summary.elapsed_seconds = max(0.001, time.perf_counter() - start_time)
    return summary


def render_analyzer_report(summary: DiskUsageSummary, stream=None) -> str:
    """Render human-readable formatted terminal report."""
    stream = stream or sys.stdout
    lines = []

    banner = "=" * 70
    divider = "-" * 70

    lines.append(banner)
    lines.append(f" DISK USAGE ANALYSIS: {safe_path_str(summary.target_path)}")
    lines.append(divider)
    lines.append(f" Total Space:      {format_bytes(summary.total_bytes)} ({summary.total_bytes:,} bytes)")
    lines.append(f" Total Files:      {summary.total_files:,}")
    lines.append(f" Total Dirs:       {summary.total_dirs:,}")
    lines.append(f" Total Symlinks:   {summary.total_symlinks:,}")
    lines.append(f" Analysis Time:    {summary.elapsed_seconds:.3f}s")
    lines.append(divider)

    if summary.largest_subdirs:
        lines.append(" TOP SUBDIRECTORIES:")
        for path, b_count, f_count in summary.largest_subdirs[:10]:
            rel_name = os.path.basename(path)
            lines.append(f"  • {format_bytes(b_count):>10s} | {f_count:>8,d} files | {safe_path_str(rel_name)}")
        lines.append(divider)

    if summary.largest_files:
        lines.append(" TOP LARGEST FILES:")
        for path, size in summary.largest_files[:10]:
            rel = os.path.relpath(path, summary.target_path)
            lines.append(f"  • {format_bytes(size):>10s} | {safe_path_str(rel)}")
        lines.append(divider)

    if summary.by_extension:
        lines.append(" SPACE BY FILE TYPE:")
        top_exts = sorted(summary.by_extension.items(), key=lambda x: x[1][1], reverse=True)[:8]
        for ext, (cnt, b_count) in top_exts:
            pct = (b_count / max(1, summary.total_bytes)) * 100
            lines.append(f"  • {ext:<16s} | {cnt:>7,d} files | {format_bytes(b_count):>10s} ({pct:5.1f}%)")
        lines.append(banner)

    output = "\n".join(lines)
    return output
