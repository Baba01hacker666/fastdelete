"""
Custom exceptions and error data structures for fastdelete.
"""

from __future__ import annotations

import dataclasses
from datetime import datetime, timezone
from typing import Optional


@dataclasses.dataclass(frozen=True)
class DeletionErrorRecord:
    """Represents a failure encountered during scanning or deletion."""
    timestamp: str
    path: str
    operation: str
    exception_class: str
    error_message: str
    errno: Optional[int] = None

    @classmethod
    def from_exception(cls, path: str, operation: str, exc: Exception) -> DeletionErrorRecord:
        now_str = datetime.now(timezone.utc).isoformat()
        err_no = getattr(exc, "errno", None)
        return cls(
            timestamp=now_str,
            path=str(path),
            operation=operation,
            exception_class=exc.__class__.__name__,
            error_message=str(exc),
            errno=err_no,
        )

    def to_log_line(self) -> str:
        """Format as a structured log line."""
        errno_str = f" [errno {self.errno}]" if self.errno is not None else ""
        return (
            f"[{self.timestamp}] [{self.operation.upper()}] "
            f"{self.path!r} -> {self.exception_class}{errno_str}: {self.error_message}"
        )


class FastDeleteError(Exception):
    """Base exception for all fastdelete errors."""


class SafetyError(FastDeleteError):
    """Raised when a path is refused for safety reasons (e.g. root/system directories)."""


class InvalidTargetError(FastDeleteError):
    """Raised when a specified target path does not exist or is invalid."""


class PathChangedError(FastDeleteError):
    """Raised when a target's identity (inode/device/mode) changed during operation."""


class DeletionAborted(FastDeleteError):
    """Raised when deletion is cancelled by the user or an interrupt signal."""


class FilterParseError(FastDeleteError):
    """Raised when an invalid filter syntax or unit is provided."""
