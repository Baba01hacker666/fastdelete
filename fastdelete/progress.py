"""
Terminal progress reporting and summary formatting for fastdelete.
"""

from __future__ import annotations

import os
import sys
import time
from typing import Optional

from fastdelete.safety import safe_path_str


def format_bytes(num_bytes: int) -> str:
    """Format bytes into a human-readable string (e.g., '4.52 GB')."""
    if num_bytes < 1024:
        return f"{num_bytes} B"
    for unit in ["KB", "MB", "GB", "TB", "PB"]:
        num_bytes /= 1024.0
        if num_bytes < 1024.0:
            return f"{num_bytes:.2f} {unit}"
    return f"{num_bytes:.2f} EB"


def format_duration(seconds: float) -> str:
    """Format seconds into HH:MM:SS or MM:SS."""
    secs = int(max(0, seconds))
    hours = secs // 3600
    minutes = (secs % 3600) // 60
    rem_secs = secs % 60
    if hours > 0:
        return f"{hours:02d}:{minutes:02d}:{rem_secs:02d}"
    return f"{minutes:02d}:{rem_secs:02d}"


class ProgressReporter:
    """
    Renders live, streaming progress updates to terminal and formats final summary.
    """

    def __init__(
        self,
        target_path: str,
        quiet: bool = False,
        verbose: bool = False,
        dry_run: bool = False,
        stream=None,
        min_update_interval: float = 0.1,  # max 10 updates per sec
    ):
        self.target_path = target_path
        self.quiet = quiet
        self.verbose = verbose
        self.dry_run = dry_run
        self.stream = stream or sys.stderr
        self.is_tty = hasattr(self.stream, "isatty") and self.stream.isatty()
        self.min_update_interval = min_update_interval
        self._last_update_time = 0.0
        self._last_n_lines = 0
        self.start_time = time.time()

    def print_verbose(self, action: str, path: str, note: str = "") -> None:
        """Print detailed action line in verbose mode."""
        if self.verbose and not self.quiet:
            self._clear_live_progress()
            note_str = f" ({note})" if note else ""
            prefix = "[DRY-RUN] " if self.dry_run else ""
            safe_p = safe_path_str(path)
            self.stream.write(f"{prefix}{action:10s} {safe_p}{note_str}\n")
            self.stream.flush()

    def update(
        self,
        files_discovered: int,
        files_deleted: int,
        dirs_deleted: int,
        failed: int,
        skipped: int,
        bytes_deleted: int = 0,
        symlinks_deleted: int = 0,
        symlinks_skipped: int = 0,
        force: bool = False,
    ) -> None:
        """Update live status display."""
        if self.quiet:
            return

        now = time.time()
        elapsed = max(0.001, now - self.start_time)

        # Throttle updates unless forced
        if not force and (now - self._last_update_time) < self.min_update_interval:
            return
        self._last_update_time = now

        total_deleted = files_deleted + dirs_deleted
        rate = total_deleted / elapsed
        elapsed_str = format_duration(elapsed)

        header = "Simulating deletion (dry-run)..." if self.dry_run else "Deleting..."

        if self.is_tty:
            # Multi-line ANSI terminal in-place update
            lines = [
                f"\033[1;36m{header}\033[0m",
                f"  Files:    {files_discovered:,}",
                f"  Dirs:     {dirs_deleted:,}",
                f"  Deleted:  \033[1;32m{total_deleted:,}\033[0m",
                f"  Failed:   \033[1;31m{failed:,}\033[0m",
                f"  Skipped:  \033[1;33m{skipped:,}\033[0m",
                f"  Rate:     {rate:,.0f} items/s",
                f"  Elapsed:  {elapsed_str}",
            ]

            self._clear_live_progress()
            self.stream.write("\n".join(lines) + "\n")
            self.stream.flush()
            self._last_n_lines = len(lines)
        else:
            # Periodic non-TTY single line
            line = (
                f"{header} Discovered: {files_discovered:,} | Deleted: {total_deleted:,} | "
                f"Failed: {failed:,} | Skipped: {skipped:,} | Rate: {rate:,.0f}/s | Elapsed: {elapsed_str}\n"
            )
            self.stream.write(line)
            self.stream.flush()

    def _clear_live_progress(self) -> None:
        """Clear previously rendered live progress lines in a TTY."""
        if self.is_tty and self._last_n_lines > 0:
            # Move cursor up and clear lines
            for _ in range(self._last_n_lines):
                self.stream.write("\033[F\033[K")
            self.stream.flush()
            self._last_n_lines = 0

    def print_summary(
        self,
        files_discovered: int,
        files_deleted: int,
        dirs_deleted: int,
        bytes_deleted: int,
        failed: int,
        skipped: int,
        symlinks_deleted: int,
        symlinks_skipped: int,
        elapsed_time: float,
    ) -> None:
        """Print comprehensive operation summary."""
        self._clear_live_progress()

        if self.quiet:
            return

        total_deleted = files_deleted + dirs_deleted
        rate = total_deleted / max(0.001, elapsed_time)
        elapsed_str = format_duration(elapsed_time)
        bytes_str = f"{format_bytes(bytes_deleted)} ({bytes_deleted:,} bytes)"
        mode_str = " (DRY-RUN)" if self.dry_run else ""

        banner = "=" * 54
        divider = "-" * 54
        title = f"FASTDELETE SUMMARY{mode_str}"

        lines = [
            f"\n{banner}",
            f" {title.center(52)}",
            f"{divider}",
            f" Target:              {safe_path_str(self.target_path)}",
            f" Files Discovered:    {files_discovered:>15,}",
            f" Files Deleted:       {files_deleted:>15,}",
            f" Directories Deleted: {dirs_deleted:>15,}",
            f" Symlinks Deleted:    {symlinks_deleted:>15,}",
            f" Bytes Deleted:       {bytes_str:>25s}",
            f" Skipped:             {skipped:>15,}",
            f" Failed:              {failed:>15,}",
            f" Symlinks Skipped:    {symlinks_skipped:>15,}",
            f" Total Elapsed:       {elapsed_str:>15s}",
            f" Average Rate:        {rate:>13,.0f} items/s",
            f"{banner}\n",
        ]

        self.stream.write("\n".join(lines))
        self.stream.flush()
