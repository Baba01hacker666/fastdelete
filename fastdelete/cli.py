"""
Command-line interface and argument parsing for fastdelete.
"""

from __future__ import annotations

import argparse
import os
import signal
import sys
import threading
from pathlib import Path
from typing import List, Optional

from fastdelete import __version__
from fastdelete.deleter import FastDeleter, DeletionStats
from fastdelete.errors import (
    FastDeleteError,
    FilterParseError,
    InvalidTargetError,
    SafetyError,
)
from fastdelete.filters import DeletionFilter, parse_duration, parse_size
from fastdelete.progress import ProgressReporter
from fastdelete.safety import (
    inspect_target,
    safe_path_str,
    validate_safety,
)


def create_parser() -> argparse.ArgumentParser:
    """Build the command-line argument parser."""
    parser = argparse.ArgumentParser(
        prog="fastdelete",
        description="Fast, safe, and robust CLI tool for deleting large directory trees and files with unusual names.",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
Examples:
  fastdelete /path/to/folder
  fastdelete /path/to/file.txt
  fastdelete /path/to/folder --dry-run
  fastdelete /path/to/folder --yes
  fastdelete /path/to/folder --verbose
  fastdelete /path/to/folder --workers 8
  fastdelete /path/to/folder --force
  fastdelete /path/to/folder --max-depth 5
  fastdelete /path/to/folder --include "*.log" --older-than 30d
  fastdelete "/path/with/a/very/long/name..."
        """,
    )

    parser.add_argument(
        "targets",
        nargs="+",
        metavar="TARGET",
        help="One or more files or directories to delete. Use '--' before targets beginning with '-'.",
    )

    parser.add_argument(
        "-y", "--yes",
        action="store_true",
        help="Skip interactive confirmation prompts and proceed directly with deletion.",
    )

    parser.add_argument(
        "-n", "--dry-run",
        action="store_true",
        help="Simulate deletion without modifying or deleting any files.",
    )

    parser.add_argument(
        "-f", "--force",
        action="store_true",
        help="Attempt to fix permissions (e.g. read-only files) to complete deletion where OS permits.",
    )

    parser.add_argument(
        "-w", "--workers",
        type=int,
        default=1,
        metavar="N",
        help="Number of parallel worker threads for deletion (default: 1).",
    )

    parser.add_argument(
        "-v", "--verbose",
        action="store_true",
        help="Print detailed action logs for each unlinked file or directory.",
    )

    parser.add_argument(
        "-q", "--quiet",
        action="store_true",
        help="Suppress live progress reporting, summary, and non-error output.",
    )

    parser.add_argument(
        "-x", "--one-file-system",
        action="store_true",
        help="Do not cross filesystem/mount boundaries during recursive directory traversal.",
    )

    # Filtering options
    filter_group = parser.add_argument_group("Filtering Options")
    filter_group.add_argument(
        "--include",
        action="append",
        dest="includes",
        metavar="PATTERN",
        help="Only delete files matching the given glob pattern (can be specified multiple times).",
    )
    filter_group.add_argument(
        "--exclude",
        action="append",
        dest="excludes",
        metavar="PATTERN",
        help="Exclude files/directories matching the given glob pattern (can be specified multiple times).",
    )
    filter_group.add_argument(
        "--min-size",
        metavar="SIZE",
        help="Only delete files larger than or equal to SIZE (e.g. 100M, 1.5GB, 500k).",
    )
    filter_group.add_argument(
        "--max-size",
        metavar="SIZE",
        help="Only delete files smaller than or equal to SIZE (e.g. 10M, 500k).",
    )
    filter_group.add_argument(
        "--older-than",
        metavar="DURATION",
        help="Only delete files modified longer ago than DURATION (e.g. 30d, 12h, 15m, 3600s).",
    )
    filter_group.add_argument(
        "--newer-than",
        metavar="DURATION",
        help="Only delete files modified more recently than DURATION (e.g. 1d, 2h).",
    )
    filter_group.add_argument(
        "--max-depth",
        type=int,
        metavar="N",
        help="Descend at most N directory levels below the target.",
    )
    filter_group.add_argument(
        "--min-depth",
        type=int,
        metavar="N",
        help="Do not delete items at depth levels less than N.",
    )
    filter_group.add_argument(
        "--files-only",
        action="store_true",
        help="Only delete files and symlinks; preserve directory structures.",
    )
    filter_group.add_argument(
        "--dirs-only",
        action="store_true",
        help="Only delete directories; do not delete files.",
    )
    filter_group.add_argument(
        "--empty-dirs-only",
        action="store_true",
        help="Only delete empty directories.",
    )

    # Logging and Safety overrides
    safety_group = parser.add_argument_group("Safety & Logging Options")
    safety_group.add_argument(
        "--log",
        dest="log_file",
        metavar="LOG_FILE",
        help="Record failure details and final summary to the specified log file.",
    )
    safety_group.add_argument(
        "--allow-root",
        action="store_true",
        help="Allow deletion of root filesystem or critical system paths (requires extra confirmation).",
    )
    safety_group.add_argument(
        "--allow-home",
        action="store_true",
        help="Allow deletion of current user's home directory (requires extra confirmation).",
    )

    parser.add_argument(
        "--version",
        action="version",
        version=f"%(prog)s {__version__}",
    )

    return parser


def build_filter(args: argparse.Namespace) -> DeletionFilter:
    """Construct DeletionFilter instance from CLI arguments."""
    min_size = parse_size(args.min_size) if args.min_size else None
    max_size = parse_size(args.max_size) if args.max_size else None
    older_than = parse_duration(args.older_than) if args.older_than else None
    newer_than = parse_duration(args.newer_than) if args.newer_than else None

    if args.max_depth is not None and args.max_depth < 0:
        raise FilterParseError("--max-depth must be non-negative.")
    if args.min_depth is not None and args.min_depth < 0:
        raise FilterParseError("--min-depth must be non-negative.")
    if args.workers < 1:
        raise FilterParseError("--workers must be at least 1.")

    return DeletionFilter(
        include_patterns=args.includes or [],
        exclude_patterns=args.excludes or [],
        min_size=min_size,
        max_size=max_size,
        older_than=older_than,
        newer_than=newer_than,
        max_depth=args.max_depth,
        min_depth=args.min_depth,
        files_only=args.files_only,
        dirs_only=args.dirs_only,
        empty_dirs_only=args.empty_dirs_only,
        one_file_system=args.one_file_system,
    )


def confirm_deletion(
    target_raw: str,
    identity,
    allow_root: bool = False,
    allow_home: bool = False,
) -> bool:
    """
    Prompt user for confirmation according to safety specifications.
    """
    print(f"\nTarget:\n  {safe_path_str(identity.abs_path)}")
    print(f"Type: {identity.type_description}")

    # Dangerous target extra check
    is_root_or_sys = allow_root
    is_home = allow_home

    if identity.is_dir:
        print("\nType the exact path to confirm:")
        try:
            user_input = input().strip()
        except (EOFError, KeyboardInterrupt):
            print("\nConfirmation aborted.")
            return False

        # Match exact raw path, abs path, or normpath
        valid_matches = {
            target_raw.strip(),
            identity.abs_path.strip(),
            os.path.normpath(target_raw).strip(),
            os.path.normpath(identity.abs_path).strip(),
        }

        if user_input not in valid_matches:
            print(f"Confirmation mismatch. Entered {user_input!r}. Aborting.")
            return False

        if is_root_or_sys or is_home:
            print("\n\033[1;31mWARNING: You are deleting a system or home directory!\033[0m")
            print("Type 'DELETE' to confirm:")
            try:
                secondary = input().strip()
            except (EOFError, KeyboardInterrupt):
                print("\nConfirmation aborted.")
                return False
            if secondary != "DELETE":
                print("Aborting.")
                return False

        return True
    else:
        # Single file confirmation
        try:
            user_input = input(f"Delete {identity.type_description.lower()} '{safe_path_str(identity.abs_path)}'? [y/N]: ").strip().lower()
        except (EOFError, KeyboardInterrupt):
            print("\nConfirmation aborted.")
            return False
        return user_input in ("y", "yes")


def main(argv: Optional[List[str]] = None) -> int:
    """Main CLI entry point."""
    parser = create_parser()
    args = parser.parse_args(argv)

    abort_event = threading.Event()

    def signal_handler(signum, frame):
        abort_event.set()
        sys.stderr.write("\n\033[1;33m[!] Interrupt signal received. Stopping fastdelete cleanly...\033[0m\n")
        sys.stderr.flush()

    signal.signal(signal.SIGINT, signal_handler)
    if hasattr(signal, "SIGTERM"):
        signal.signal(signal.SIGTERM, signal_handler)

    try:
        deletion_filter = build_filter(args)
    except FilterParseError as e:
        sys.stderr.write(f"Error: {e}\n")
        return 2

    overall_failed = 0

    for target in args.targets:
        if abort_event.is_set():
            break

        try:
            identity = inspect_target(target)
        except InvalidTargetError as e:
            sys.stderr.write(f"Error: {e}\n")
            overall_failed += 1
            continue

        try:
            validate_safety(
                identity,
                allow_root=args.allow_root,
                allow_home=args.allow_home,
            )
        except SafetyError as e:
            sys.stderr.write(f"\033[1;31mSafety Error: {e}\033[0m\n")
            return 2

        # Display target info
        if not args.quiet and not args.yes and not args.dry_run:
            confirmed = confirm_deletion(
                target_raw=target,
                identity=identity,
                allow_root=args.allow_root,
                allow_home=args.allow_home,
            )
            if not confirmed:
                sys.stderr.write("Operation cancelled by user.\n")
                return 2

        progress = ProgressReporter(
            target_path=identity.abs_path,
            quiet=args.quiet,
            verbose=args.verbose,
            dry_run=args.dry_run,
        )

        deleter = FastDeleter(
            target_path=identity.abs_path,
            dry_run=args.dry_run,
            force=args.force,
            workers=args.workers,
            deletion_filter=deletion_filter,
            progress_reporter=progress,
            log_file=args.log_file,
            abort_event=abort_event,
        )

        stats = deleter.run()
        if stats.failed > 0:
            overall_failed += stats.failed

    if abort_event.is_set():
        return 130

    return 1 if overall_failed > 0 else 0


if __name__ == "__main__":
    sys.exit(main())
