"""
Command-line interface and argument parsing for fastdelete.
Supports standard fast deletion, developer preset cleaners, secure shredding,
safe trash operations, disk usage analysis, and duplicate detection.
"""

from __future__ import annotations

import argparse
import json
import os
import signal
import sys
import threading
from pathlib import Path
from typing import List, Optional, Set

from fastdelete import __version__
from fastdelete.analyzer import analyze_directory, render_analyzer_report
from fastdelete.deleter import DeletionStats, FastDeleter
from fastdelete.duplicates import (
    clean_duplicates,
    find_duplicates,
    render_duplicates_report,
)
from fastdelete.errors import (
    FastDeleteError,
    FilterParseError,
    InvalidTargetError,
    SafetyError,
)
from fastdelete.filters import DeletionFilter, parse_duration, parse_size
from fastdelete.gitignore import GitIgnoreMatcher
from fastdelete.presets import (
    list_presets,
    run_preset_clean,
)
from fastdelete.progress import ProgressReporter
from fastdelete.safety import (
    classify_target_danger,
    inspect_target,
    safe_path_str,
    validate_safety,
)
from fastdelete.trash import (
    empty_trash,
    list_trash,
    move_to_trash,
    restore_trash_item,
)


def create_parser() -> argparse.ArgumentParser:
    """Build the command-line argument parser."""
    parser = argparse.ArgumentParser(
        prog="fastdelete",
        description="Production-grade CLI tool for high-performance file and tree deletion, workspace cleaning, secure shredding, and disk inspection.",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
Commands:
  fastdelete <TARGETS...>              Fast safe deletion (default)
  fastdelete clean <PRESET> [PATH]     Clean dev caches (python, node, rust, c, temp, logs, all-dev)
  fastdelete shred <TARGETS...>        Securely wipe files with multi-pass overwrites
  fastdelete trash <TARGETS...>        Move items safely to OS/FreeDesktop Trash
  fastdelete restore <TRASH_ID>        Restore item from Trash
  fastdelete du [PATH]                 Analyze recursive disk usage and hogs
  fastdelete dupes [PATH]              Find duplicate files and reclaim wasted space
  fastdelete bench                     Run performance benchmark

Examples:
  fastdelete /path/to/folder --yes
  fastdelete /path/to/folder --dry-run
  fastdelete /path/to/folder --workers 8
  fastdelete /path/to/folder --include "*.log" --older-than 30d
  fastdelete /path/to/secret.dat --shred --shred-method dod
  fastdelete clean python --dry-run
  fastdelete du /var/log
  fastdelete dupes /data --min-size 10M
        """,
    )

    parser.add_argument(
        "targets",
        nargs="*",
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

    # Shredding and Trash
    secure_group = parser.add_argument_group("Shredding & Trash Options")
    secure_group.add_argument(
        "--shred",
        action="store_true",
        help="Securely overwrite file data before unlinking to prevent data recovery.",
    )
    secure_group.add_argument(
        "--shred-method",
        choices=["zero", "random", "dod", "dod7", "gutmann", "custom"],
        default="dod",
        help="Sanitization algorithm for shredding (default: dod).",
    )
    secure_group.add_argument(
        "--shred-passes",
        type=int,
        metavar="N",
        help="Number of overwrite passes for custom shredding.",
    )
    secure_group.add_argument(
        "-t", "--trash",
        action="store_true",
        help="Move target to FreeDesktop/OS Trash instead of unlinking permanently.",
    )

    # Machine-readable output
    output_group = parser.add_argument_group("Output Formatting")
    output_group.add_argument(
        "--json",
        action="store_true",
        help="Output final results and statistics in JSON format.",
    )
    output_group.add_argument(
        "--ndjson", "--stream-json",
        action="store_true",
        dest="ndjson",
        help="Stream live events as newline-delimited JSON objects.",
    )

    # Filtering options
    filter_group = parser.add_argument_group("Filtering Options")
    filter_group.add_argument(
        "--include",
        action="append",
        dest="includes",
        metavar="PATTERN",
        help="Only delete files matching glob pattern (repeatable).",
    )
    filter_group.add_argument(
        "--exclude",
        action="append",
        dest="excludes",
        metavar="PATTERN",
        help="Exclude files/directories matching glob pattern (repeatable).",
    )
    filter_group.add_argument(
        "--regex",
        action="append",
        dest="include_regex",
        metavar="REGEX",
        help="Only delete files matching regular expression (repeatable).",
    )
    filter_group.add_argument(
        "--exclude-regex",
        action="append",
        dest="exclude_regex",
        metavar="REGEX",
        help="Exclude files/directories matching regular expression (repeatable).",
    )
    filter_group.add_argument(
        "--type",
        dest="file_types",
        metavar="TYPES",
        help="Filter by file type: 'f' (file), 'd' (directory), 'l' (symlink), 's' (socket), 'p' (fifo). E.g. --type f,l",
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
        "--accessed-older-than",
        metavar="DURATION",
        help="Only delete files accessed longer ago than DURATION.",
    )
    filter_group.add_argument(
        "--accessed-newer-than",
        metavar="DURATION",
        help="Only delete files accessed more recently than DURATION.",
    )
    filter_group.add_argument(
        "--created-older-than",
        metavar="DURATION",
        help="Only delete files created/changed longer ago than DURATION.",
    )
    filter_group.add_argument(
        "--created-newer-than",
        metavar="DURATION",
        help="Only delete files created/changed more recently than DURATION.",
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
    filter_group.add_argument(
        "--empty-files-only",
        action="store_true",
        help="Only delete 0-byte empty regular files.",
    )
    filter_group.add_argument(
        "--gitignore",
        nargs="?",
        const=".gitignore",
        metavar="FILE",
        help="Respect gitignore exclusion rules from the given ignore file (default: .gitignore).",
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
    accessed_older_than = parse_duration(args.accessed_older_than) if getattr(args, "accessed_older_than", None) else None
    accessed_newer_than = parse_duration(args.accessed_newer_than) if getattr(args, "accessed_newer_than", None) else None
    created_older_than = parse_duration(args.created_older_than) if getattr(args, "created_older_than", None) else None
    created_newer_than = parse_duration(args.created_newer_than) if getattr(args, "created_newer_than", None) else None

    if args.max_depth is not None and args.max_depth < 0:
        raise FilterParseError("--max-depth must be non-negative.")
    if args.min_depth is not None and args.min_depth < 0:
        raise FilterParseError("--min-depth must be non-negative.")
    if (
        args.min_depth is not None
        and args.max_depth is not None
        and args.min_depth > args.max_depth
    ):
        raise FilterParseError("--min-depth cannot be greater than --max-depth.")
    if args.workers < 1:
        raise FilterParseError("--workers must be at least 1.")
    if args.empty_dirs_only and (args.files_only or args.dirs_only):
        raise FilterParseError(
            "--empty-dirs-only cannot be combined with --files-only or --dirs-only."
        )

    file_types: Optional[Set[str]] = None
    if getattr(args, "file_types", None):
        file_types = {t.strip().lower() for t in args.file_types.split(",")}

    gitignore_matcher = None
    if getattr(args, "gitignore", None):
        ignore_file = args.gitignore
        if os.path.exists(ignore_file):
            gitignore_matcher = GitIgnoreMatcher.from_file(ignore_file)

    return DeletionFilter(
        include_patterns=args.includes or [],
        exclude_patterns=args.excludes or [],
        include_regex=getattr(args, "include_regex", None) or [],
        exclude_regex=getattr(args, "exclude_regex", None) or [],
        file_types=file_types,
        min_size=min_size,
        max_size=max_size,
        older_than=older_than,
        newer_than=newer_than,
        accessed_older_than=accessed_older_than,
        accessed_newer_than=accessed_newer_than,
        created_older_than=created_older_than,
        created_newer_than=created_newer_than,
        max_depth=args.max_depth,
        min_depth=args.min_depth,
        files_only=args.files_only,
        dirs_only=args.dirs_only,
        empty_dirs_only=args.empty_dirs_only,
        empty_files_only=getattr(args, "empty_files_only", False),
        one_file_system=args.one_file_system,
        gitignore_matcher=gitignore_matcher,
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

    is_root, is_sys, is_home = classify_target_danger(identity)
    is_root_or_sys = is_root or is_sys

    if identity.is_dir:
        print("\nType the exact path to confirm:")
        try:
            user_input = input().strip()
        except (EOFError, KeyboardInterrupt):
            print("\nConfirmation aborted.")
            return False

        valid_matches = {
            target_raw.strip(),
            identity.abs_path.strip(),
            os.path.normpath(target_raw).strip(),
            os.path.normpath(identity.abs_path).strip(),
        }

        if user_input not in valid_matches:
            print(f"Confirmation mismatch. Entered {user_input!r}. Aborting.")
            return False

        if (is_root_or_sys or is_home) and (allow_root or allow_home):
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
        try:
            user_input = input(f"Delete {identity.type_description.lower()} '{safe_path_str(identity.abs_path)}'? [y/N]: ").strip().lower()
        except (EOFError, KeyboardInterrupt):
            print("\nConfirmation aborted.")
            return False
        return user_input in ("y", "yes")


# Subcommand handlers
def handle_clean_subcommand(sub_args: List[str]) -> int:
    """Handle `fastdelete clean <preset>`."""
    parser = argparse.ArgumentParser(prog="fastdelete clean", description="Clean workspace caches and build artifacts.")
    parser.add_argument("preset", nargs="?", help="Preset name (e.g. python, node, rust, c, java, temp, logs, all-dev)")
    parser.add_argument("path", nargs="?", default=".", help="Root directory to clean (default: current directory)")
    parser.add_argument("-n", "--dry-run", action="store_true", help="Simulate clean without deleting files.")
    parser.add_argument("-f", "--force", action="store_true", help="Reset permissions on read-only files.")
    parser.add_argument("-w", "--workers", type=int, default=1, help="Parallel worker threads.")
    parser.add_argument("-q", "--quiet", action="store_true", help="Suppress progress output.")
    parser.add_argument("--list", action="store_true", help="List all available cleanup presets.")
    parser.add_argument("--json", action="store_true", help="Output results as JSON.")

    args = parser.parse_args(sub_args)

    if args.list or not args.preset:
        print("Available Clean Presets:")
        for p in list_presets():
            print(f"  • {p.name:<12s} - {p.description}")
        return 0

    try:
        stats = run_preset_clean(
            preset_name=args.preset,
            root_path=args.path,
            dry_run=args.dry_run,
            force=args.force,
            workers=args.workers,
            quiet=args.quiet,
        )
        if args.json:
            print(stats.to_json(indent=2))
        else:
            mode = " (DRY-RUN)" if args.dry_run else ""
            print(f"\n[+] Cleaned preset '{args.preset}'{mode}:")
            print(f"    Files Deleted: {stats.files_deleted:,}")
            print(f"    Dirs Deleted:  {stats.directories_deleted:,}")
            print(f"    Bytes Freed:   {stats.bytes_deleted:,}")
            print(f"    Elapsed Time:  {stats.elapsed_seconds():.3f}s")
        return 1 if stats.failed > 0 else 0
    except FastDeleteError as e:
        sys.stderr.write(f"Error: {e}\n")
        return 2


def handle_du_subcommand(sub_args: List[str]) -> int:
    """Handle `fastdelete du [path]`."""
    parser = argparse.ArgumentParser(prog="fastdelete du", description="Analyze recursive disk usage and top disk hogs.")
    parser.add_argument("path", nargs="?", default=".", help="Directory to analyze (default: current directory)")
    parser.add_argument("-t", "--top", type=int, default=10, help="Number of largest files/dirs to show (default: 10)")
    parser.add_argument("--max-depth", type=int, help="Limit traversal depth.")
    parser.add_argument("--json", action="store_true", help="Output analysis in JSON format.")

    args = parser.parse_args(sub_args)

    if not os.path.exists(args.path):
        sys.stderr.write(f"Error: path does not exist: {args.path}\n")
        return 1

    summary = analyze_directory(args.path, top_n=args.top, max_depth=args.max_depth)

    if args.json:
        print(json.dumps(summary.to_dict(), indent=2))
    else:
        print(render_analyzer_report(summary))
    return 0


def handle_dupes_subcommand(sub_args: List[str]) -> int:
    """Handle `fastdelete dupes [path]`."""
    parser = argparse.ArgumentParser(prog="fastdelete dupes", description="Find and clean duplicate files.")
    parser.add_argument("path", nargs="?", default=".", help="Directory to search (default: current directory)")
    parser.add_argument("--min-size", default="1", help="Minimum file size to evaluate (e.g. 1M, 500k).")
    parser.add_argument("--json", action="store_true", help="Output duplicate report as JSON.")
    parser.add_argument("--delete", action="store_true", help="Automatically delete duplicate copies (keeps first).")
    parser.add_argument("--hardlink", action="store_true", help="Replace duplicates with hardlinks.")
    parser.add_argument("--dry-run", action="store_true", help="Simulate deletion of duplicates.")
    parser.add_argument(
        "--keep",
        choices=["first", "newest", "oldest"],
        default="first",
        help="Which copy to keep when deleting/hardlinking duplicates (default: first).",
    )

    args = parser.parse_args(sub_args)

    if not os.path.isdir(args.path):
        sys.stderr.write(f"Error: directory does not exist: {args.path}\n")
        return 1

    min_sz = parse_size(args.min_size) if args.min_size else 1
    report = find_duplicates(args.path, min_size=min_sz)

    if args.json:
        print(json.dumps(report.to_dict(), indent=2))
    else:
        print(render_duplicates_report(report))

    if args.delete or args.hardlink or args.dry_run:
        action = "hardlink" if args.hardlink else ("dry-run" if args.dry_run else "delete")
        stats = clean_duplicates(report, keep_strategy=args.keep, action=action)
        print(f"\n[+] Action '{action}' complete: {stats.files_deleted} duplicates processed.")

    return 0


def handle_trash_subcommand(sub_args: List[str]) -> int:
    """Handle `fastdelete trash <targets>`."""
    parser = argparse.ArgumentParser(prog="fastdelete trash", description="Move items to Trash bin.")
    parser.add_argument("targets", nargs="*", help="Files or directories to trash.")
    parser.add_argument("--list", action="store_true", help="List all items currently in Trash.")
    parser.add_argument("--empty", action="store_true", help="Empty Trash bin permanently.")
    parser.add_argument("--restore", metavar="ID", help="Restore item by trash ID or name.")
    parser.add_argument("--dest", metavar="DEST", help="Optional restore destination path.")

    args = parser.parse_args(sub_args)

    if args.list:
        items = list_trash()
        print(f"Trash Contents ({len(items)} items):")
        for it in items:
            t_str = it.deletion_date.strftime("%Y-%m-%d %H:%M:%S")
            print(f"  • [{it.id}] {safe_path_str(it.original_path)} ({t_str})")
        return 0

    if args.empty:
        cnt = empty_trash()
        print(f"[+] Trash emptied: {cnt} items removed.")
        return 0

    if args.restore:
        try:
            restored = restore_trash_item(args.restore, destination=args.dest)
            print(f"[+] Restored '{args.restore}' -> {restored}")
            return 0
        except Exception as e:
            sys.stderr.write(f"Error restoring from Trash: {e}\n")
            return 1

    if not args.targets:
        parser.print_help()
        return 1

    for t in args.targets:
        try:
            item = move_to_trash(t)
            print(f"[+] Moved to Trash: {safe_path_str(item.original_path)} (ID: {item.id})")
        except Exception as e:
            sys.stderr.write(f"Error trashing '{t}': {e}\n")
            return 1

    return 0


def handle_bench_subcommand(sub_args: List[str]) -> int:
    """Handle `fastdelete bench`."""
    bench_script = Path(__file__).resolve().parent.parent / "bench" / "test_speed.py"
    if bench_script.exists():
        import subprocess
        return subprocess.run([sys.executable, str(bench_script)] + sub_args).returncode
    sys.stderr.write("Benchmark script not found.\n")
    return 1


def main(argv: Optional[List[str]] = None) -> int:
    """Main CLI entry point."""
    raw_args = list(sys.argv[1:] if argv is None else argv)

    # Subcommand routing
    if raw_args:
        first = raw_args[0].lower()
        if first == "clean":
            return handle_clean_subcommand(raw_args[1:])
        elif first in ("du", "analyze", "disk-usage"):
            return handle_du_subcommand(raw_args[1:])
        elif first in ("dupes", "duplicates", "find-duplicates"):
            return handle_dupes_subcommand(raw_args[1:])
        elif first in ("trash", "recycle"):
            return handle_trash_subcommand(raw_args[1:])
        elif first in ("trash-list", "trash-ls"):
            return handle_trash_subcommand(["--list"] + raw_args[1:])
        elif first in ("trash-empty", "empty-trash"):
            return handle_trash_subcommand(["--empty"] + raw_args[1:])
        elif first == "restore":
            return handle_trash_subcommand(["--restore"] + raw_args[1:])
        elif first == "shred":
            raw_args = ["--shred"] + raw_args[1:]
        elif first == "rm":
            raw_args = raw_args[1:]
        elif first == "bench":
            return handle_bench_subcommand(raw_args[1:])

    parser = create_parser()
    args = parser.parse_args(raw_args)

    if not args.targets:
        parser.print_help()
        return 1

    abort_event = threading.Event()
    active_deleter = None

    def signal_handler(signum, frame):
        abort_event.set()
        if active_deleter is not None:
            active_deleter.request_abort()
        if not args.quiet and not getattr(args, "ndjson", False):
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

    def event_streamer(evt: dict):
        if getattr(args, "ndjson", False):
            sys.stdout.write(json.dumps(evt) + "\n")
            sys.stdout.flush()

    overall_failed = 0
    all_stats: List[DeletionStats] = []

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

        # Confirmation prompt
        if not args.quiet and not args.yes and not args.dry_run and not args.json and not getattr(args, "ndjson", False):
            confirmed = confirm_deletion(
                target_raw=target,
                identity=identity,
                allow_root=args.allow_root,
                allow_home=args.allow_home,
            )
            if not confirmed:
                sys.stderr.write("Operation cancelled by user.\n")
                return 2

        progress = None
        if not args.quiet and not args.json and not getattr(args, "ndjson", False):
            progress = ProgressReporter(
                target_path=identity.abs_path,
                quiet=args.quiet,
                verbose=args.verbose,
                dry_run=args.dry_run,
            )

        active_deleter = FastDeleter(
            target_path=identity.abs_path,
            dry_run=args.dry_run,
            force=args.force,
            workers=args.workers,
            deletion_filter=deletion_filter,
            progress_reporter=progress,
            log_file=args.log_file,
            abort_event=abort_event,
            shred=args.shred,
            shred_method=args.shred_method,
            shred_passes=args.shred_passes,
            trash=args.trash,
            event_callback=event_streamer,
        )

        stats = active_deleter.run()
        all_stats.append(stats)
        if stats.failed > 0:
            overall_failed += stats.failed

    if args.json:
        if len(all_stats) == 1:
            print(all_stats[0].to_json(indent=2))
        else:
            print(json.dumps([s.to_dict() for s in all_stats], indent=2))

    if abort_event.is_set():
        return 130

    return 1 if overall_failed > 0 else 0


if __name__ == "__main__":
    sys.exit(main())
