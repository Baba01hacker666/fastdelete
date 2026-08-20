"""
fastdelete - High-performance, safe file and directory deletion CLI tool.
"""

__version__ = "1.0.0"
__author__ = "Baba01hacker666"

from fastdelete.errors import (
    FastDeleteError,
    SafetyError,
    InvalidTargetError,
    PathChangedError,
    DeletionAborted,
    FilterParseError,
)
from fastdelete.safety import (
    TargetIdentity,
    inspect_target,
    validate_safety,
    safe_path_str,
)
from fastdelete.filters import DeletionFilter, parse_size, parse_duration
from fastdelete.scanner import ScanAction, ScanItem, DirectoryScanner
from fastdelete.deleter import DeletionStats, FastDeleter
from fastdelete.progress import ProgressReporter

__all__ = [
    "__version__",
    "FastDeleteError",
    "SafetyError",
    "InvalidTargetError",
    "PathChangedError",
    "DeletionAborted",
    "FilterParseError",
    "TargetIdentity",
    "inspect_target",
    "validate_safety",
    "safe_path_str",
    "DeletionFilter",
    "parse_size",
    "parse_duration",
    "ScanAction",
    "ScanItem",
    "DirectoryScanner",
    "DeletionStats",
    "FastDeleter",
    "ProgressReporter",
]
