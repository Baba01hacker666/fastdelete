"""
fastdelete - High-performance, safe, multi-threaded filesystem deletion, workspace cleaner, and disk tool.
"""

__version__ = "2.0.0"
__author__ = "Baba01hacker666"

from fastdelete.errors import (
    FastDeleteError,
    SafetyError,
    InvalidTargetError,
    PathChangedError,
    DeletionAborted,
    FilterParseError,
    DeletionErrorRecord,
)
from fastdelete.safety import (
    TargetIdentity,
    inspect_target,
    validate_safety,
    safe_path_str,
    normalize_long_path,
)
from fastdelete.filters import (
    DeletionFilter,
    parse_size,
    parse_duration,
)
from fastdelete.scanner import (
    ScanAction,
    ScanItem,
    DirectoryScanner,
)
from fastdelete.deleter import (
    DeletionStats,
    FastDeleter,
)
from fastdelete.progress import (
    ProgressReporter,
    format_bytes,
    format_duration,
)
from fastdelete.shredder import (
    ShredMethod,
    shred_file,
)
from fastdelete.trash import (
    TrashItem,
    move_to_trash,
    list_trash,
    restore_trash_item,
    empty_trash,
)
from fastdelete.presets import (
    Preset,
    get_preset,
    list_presets,
    run_preset_clean,
)
from fastdelete.gitignore import (
    GitIgnoreRule,
    GitIgnoreMatcher,
)
from fastdelete.analyzer import (
    DiskUsageSummary,
    analyze_directory,
    render_analyzer_report,
)
from fastdelete.duplicates import (
    DuplicateGroup,
    DuplicateReport,
    find_duplicates,
    clean_duplicates,
    render_duplicates_report,
)
from fastdelete.api import (
    delete,
    delete_many,
    delete_async,
    shred,
    trash,
    restore,
    clean,
    analyze,
    duplicates,
)

__all__ = [
    "__version__",
    "__author__",
    # Public API
    "delete",
    "delete_many",
    "delete_async",
    "shred",
    "trash",
    "restore",
    "clean",
    "analyze",
    "duplicates",
    # Core Classes
    "FastDeleter",
    "DeletionStats",
    "DeletionFilter",
    "DirectoryScanner",
    "ScanItem",
    "ScanAction",
    "ProgressReporter",
    "TargetIdentity",
    "ShredMethod",
    "TrashItem",
    "Preset",
    "DiskUsageSummary",
    "DuplicateGroup",
    "DuplicateReport",
    "render_analyzer_report",
    "render_duplicates_report",
    "GitIgnoreMatcher",
    "GitIgnoreRule",
    "DeletionErrorRecord",
    # Utilities
    "inspect_target",
    "validate_safety",
    "safe_path_str",
    "normalize_long_path",
    "parse_size",
    "parse_duration",
    "format_bytes",
    "format_duration",
    "shred_file",
    "move_to_trash",
    "list_trash",
    "restore_trash_item",
    "empty_trash",
    "get_preset",
    "list_presets",
    "run_preset_clean",
    "analyze_directory",
    "find_duplicates",
    "clean_duplicates",
    # Exceptions
    "FastDeleteError",
    "SafetyError",
    "InvalidTargetError",
    "PathChangedError",
    "DeletionAborted",
    "FilterParseError",
]
