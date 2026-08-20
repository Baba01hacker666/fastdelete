"""
Filtering logic for fastdelete: globs, sizes, timestamps, depths, and filesystem boundaries.
"""

from __future__ import annotations

import fnmatch
import os
import re
import stat
import time
from dataclasses import dataclass, field
from typing import List, Optional, Tuple

from fastdelete.errors import FilterParseError


_SIZE_UNIT_MULTIPLIERS = {
    "": 1,
    "b": 1,
    "k": 1024,
    "kb": 1024,
    "kib": 1024,
    "m": 1024 * 1024,
    "mb": 1024 * 1024,
    "mib": 1024 * 1024,
    "g": 1024 * 1024 * 1024,
    "gb": 1024 * 1024 * 1024,
    "gib": 1024 * 1024 * 1024,
    "t": 1024 * 1024 * 1024 * 1024,
    "tb": 1024 * 1024 * 1024 * 1024,
    "tib": 1024 * 1024 * 1024 * 1024,
}

_DURATION_UNIT_MULTIPLIERS = {
    "": 1.0,
    "s": 1.0,
    "sec": 1.0,
    "secs": 1.0,
    "second": 1.0,
    "seconds": 1.0,
    "m": 60.0,
    "min": 60.0,
    "mins": 60.0,
    "minute": 60.0,
    "minutes": 60.0,
    "h": 3600.0,
    "hr": 3600.0,
    "hrs": 3600.0,
    "hour": 3600.0,
    "hours": 3600.0,
    "d": 86400.0,
    "day": 86400.0,
    "days": 86400.0,
    "w": 7 * 86400.0,
    "week": 7 * 86400.0,
    "weeks": 7 * 86400.0,
    "y": 365 * 86400.0,
    "year": 365 * 86400.0,
    "years": 365 * 86400.0,
}


def parse_size(size_str: str) -> int:
    """
    Parse a human-readable size string (e.g., '100M', '1.5GB', '500k', '1024') into bytes.
    Raises FilterParseError if the format is invalid.
    """
    if not size_str or not size_str.strip():
        raise FilterParseError("Size string cannot be empty.")

    cleaned = size_str.strip().lower()
    match = re.match(r"^([0-9]+(?:\.[0-9]+)?)\s*([a-z]*)$", cleaned)
    if not match:
        raise FilterParseError(f"Invalid size specification: {size_str!r}. Example valid formats: '100M', '1.5GB', '500k'.")

    num_str, unit = match.groups()
    if unit not in _SIZE_UNIT_MULTIPLIERS:
        raise FilterParseError(f"Unknown size unit '{unit}' in '{size_str}'. Supported units: B, K, M, G, T (and KiB, MiB, GiB, TiB).")

    try:
        val = float(num_str)
        multiplier = _SIZE_UNIT_MULTIPLIERS[unit]
        return int(val * multiplier)
    except (ValueError, OverflowError) as e:
        raise FilterParseError(f"Invalid number in size '{size_str}': {e}")


def parse_duration(duration_str: str) -> float:
    """
    Parse a human-readable duration string (e.g., '30d', '12h', '15m', '3600s') into seconds.
    Raises FilterParseError if the format is invalid.
    """
    if not duration_str or not duration_str.strip():
        raise FilterParseError("Duration string cannot be empty.")

    cleaned = duration_str.strip().lower()
    match = re.match(r"^([0-9]+(?:\.[0-9]+)?)\s*([a-z]*)$", cleaned)
    if not match:
        raise FilterParseError(f"Invalid duration specification: {duration_str!r}. Example valid formats: '30d', '12h', '15m', '3600s'.")

    num_str, unit = match.groups()
    if unit not in _DURATION_UNIT_MULTIPLIERS:
        raise FilterParseError(f"Unknown duration unit '{unit}' in '{duration_str}'. Supported units: s, m, h, d, w, y.")

    try:
        val = float(num_str)
        multiplier = _DURATION_UNIT_MULTIPLIERS[unit]
        return val * multiplier
    except (ValueError, OverflowError) as e:
        raise FilterParseError(f"Invalid number in duration '{duration_str}': {e}")


@dataclass
class DeletionFilter:
    """
    Encapsulates all selection and exclusion criteria for deletion and traversal.
    """
    include_patterns: List[str] = field(default_factory=list)
    exclude_patterns: List[str] = field(default_factory=list)
    min_size: Optional[int] = None
    max_size: Optional[int] = None
    older_than: Optional[float] = None
    newer_than: Optional[float] = None
    max_depth: Optional[int] = None
    min_depth: Optional[int] = None
    files_only: bool = False
    dirs_only: bool = False
    empty_dirs_only: bool = False
    one_file_system: bool = False
    base_dev: Optional[int] = None
    reference_time: float = field(default_factory=time.time)

    def has_filters(self) -> bool:
        """Return True if any filtering options are active."""
        return bool(
            self.include_patterns
            or self.exclude_patterns
            or self.min_size is not None
            or self.max_size is not None
            or self.older_than is not None
            or self.newer_than is not None
            or self.max_depth is not None
            or self.min_depth is not None
            or self.files_only
            or self.dirs_only
            or self.empty_dirs_only
            or self.one_file_system
        )

    def _matches_name_or_path(self, name: str, rel_path: str, patterns: List[str]) -> bool:
        """Check if filename or relative path matches any pattern."""
        for pat in patterns:
            if fnmatch.fnmatch(name, pat):
                return True
            if fnmatch.fnmatch(rel_path, pat):
                return True
            # Also check normalized Unix paths for Windows compatibility
            if "/" in pat and fnmatch.fnmatch(rel_path.replace("\\", "/"), pat):
                return True
        return False

    def should_traverse_directory(
        self,
        entry: os.DirEntry,
        depth: int,
        rel_path: str,
    ) -> Tuple[bool, Optional[str]]:
        """
        Check if scanner should traverse into this subdirectory.
        Returns (should_traverse, reason_if_skipped).
        """
        # Exclude patterns apply to traversal
        if self.exclude_patterns and self._matches_name_or_path(entry.name, rel_path, self.exclude_patterns):
            return False, f"Directory matches exclude pattern"

        # Max depth check: if depth exceeds max_depth, do not recurse further
        if self.max_depth is not None and depth > self.max_depth:
            return False, f"Depth {depth} exceeds max-depth {self.max_depth}"

        # One-file-system check
        if self.one_file_system and self.base_dev is not None:
            try:
                st = entry.stat(follow_symlinks=False)
                if st.st_dev != self.base_dev:
                    return False, f"Filesystem boundary crossed (device {st.st_dev} != base {self.base_dev})"
            except (OSError, PermissionError) as e:
                # If stat fails, we let the scanner handle the permission/error upon entering
                pass

        return True, None

    def matches_file(
        self,
        entry: os.DirEntry,
        depth: int,
        rel_path: str,
    ) -> Tuple[bool, Optional[str]]:
        """
        Evaluate whether a regular file, symlink, or special file matches the deletion filter.
        Returns (is_match, reason_if_skipped).
        """
        if self.dirs_only:
            return False, "Skipped (--dirs-only active)"

        if self.min_depth is not None and depth < self.min_depth:
            return False, f"Depth {depth} is less than min-depth {self.min_depth}"

        if self.max_depth is not None and depth > self.max_depth:
            return False, f"Depth {depth} exceeds max-depth {self.max_depth}"

        # Exclude check
        if self.exclude_patterns and self._matches_name_or_path(entry.name, rel_path, self.exclude_patterns):
            return False, "Matches exclude pattern"

        # Include check
        if self.include_patterns and not self._matches_name_or_path(entry.name, rel_path, self.include_patterns):
            return False, "Does not match include pattern"

        # Size and age checks require stat
        needs_stat = (
            self.min_size is not None
            or self.max_size is not None
            or self.older_than is not None
            or self.newer_than is not None
        )

        if needs_stat:
            try:
                st = entry.stat(follow_symlinks=False)
            except (FileNotFoundError, PermissionError, OSError) as e:
                # If stat fails on file (e.g. broken symlink or vanished), we can't verify size/mtime
                if self.min_size is not None or self.max_size is not None:
                    return False, f"Cannot stat file for size filtering: {e}"
                if self.older_than is not None or self.newer_than is not None:
                    return False, f"Cannot stat file for time filtering: {e}"
                return True, None

            # Size filtering (only applies to regular files, not symlinks)
            if stat.S_ISREG(st.st_mode):
                if self.min_size is not None and st.st_size < self.min_size:
                    return False, f"File size ({st.st_size} bytes) < min-size ({self.min_size} bytes)"
                if self.max_size is not None and st.st_size > self.max_size:
                    return False, f"File size ({st.st_size} bytes) > max-size ({self.max_size} bytes)"

            # Time filtering (mtime)
            mtime = st.st_mtime
            age = self.reference_time - mtime

            if self.older_than is not None and age < self.older_than:
                return False, f"File age ({age:.1f}s) is newer than older-than ({self.older_than:.1f}s)"

            if self.newer_than is not None and age > self.newer_than:
                return False, f"File age ({age:.1f}s) is older than newer-than ({self.newer_than:.1f}s)"

        return True, None

    def matches_dir_removal(
        self,
        depth: int,
        rel_path: str,
        dir_name: str,
    ) -> Tuple[bool, Optional[str]]:
        """
        Check if a directory itself can be removed after its contents are processed.
        """
        if self.files_only:
            return False, "Skipped (--files-only active)"

        if self.min_depth is not None and depth < self.min_depth:
            return False, f"Depth {depth} is less than min-depth {self.min_depth}"

        if self.max_depth is not None and depth > self.max_depth:
            return False, f"Depth {depth} exceeds max-depth {self.max_depth}"

        if self.exclude_patterns and self._matches_name_or_path(dir_name, rel_path, self.exclude_patterns):
            return False, "Directory matches exclude pattern"

        return True, None
