# fastdelete

A production-grade, memory-efficient, and safe Python CLI tool for deleting massive directory trees, millions of files, and items with extremely long or unusual filenames.

## Core Features

- **Extreme Memory Efficiency ($O(\text{depth})$)**: Uses `os.scandir()` with an iterative post-order traversal stack instead of loading giant directory trees into memory or hitting Python's recursion depth limit. Millions of files can be traversed and deleted in megabytes of RAM.
- **Direct System Primitives**: Performs deletions directly via `os.unlink()` for files/symlinks/special objects and `os.rmdir()` for empty directories. Never invokes unsafe shell subshells or `shutil.rmtree()`.
- **Bulletproof Filename Handling**: Handles long paths, Unicode/emoji names, newlines (`\n`), tabs, spaces, quotes, shell metacharacters, non-ASCII characters, hidden files, and files starting with `-`. Safely escapes control characters during terminal output to prevent terminal corruption.
- **Safety First**:
  - Automatically resolves and inspects target paths prior to deletion.
  - Hard refuses critical system directories (`/`, `/boot`, `/etc`, `/usr`, `/var`, `/bin`, `/home`, Windows system folders, user home directory) unless explicit override flags are passed.
  - Never recursively traverses directory symlinks (unlinks the symlink itself).
  - Exact-path interactive confirmation for recursive directory deletions (skippable with `--yes`).
  - Pre-inspection target identity tracking to detect filesystem race conditions and swapped inodes.
- **Dry-Run Mode (`--dry-run` / `-n`)**: Accurately simulates deletion, tests filters, and collects statistics without modifying anything on disk.
- **Fine-Grained Filtering**: Filter candidates by glob patterns (`--include`, `--exclude`), file sizes (`--min-size`, `--max-size`), modification ages (`--older-than`, `--newer-than`), recursion depth (`--max-depth`, `--min-depth`), and filesystem boundaries (`--one-file-system`).
- **Parallel Worker Engine (`--workers N`)**: Optional multi-threaded batch deletion for high-latency filesystems (NFS, SMB, cloud mounts) while maintaining strict post-order directory removal.
- **Force Mode (`--force` / `-f`)**: Automatically resets read-only permissions on files/directories where permissible by the OS and retries deletion.
- **Signal Handling**: Intercepts `Ctrl+C` (SIGINT) and `SIGTERM`, safely completes or aborts active worker batches, and outputs a partial summary.
- **Structured Failure Logging (`--log FILE`)**: Records timestamped error logs for failed deletions without slowing down fast deletions.
- **Live Terminal Progress**: Clean, non-intrusive live progress reporting with file counters, rate calculation (items/sec), and elapsed time.

---

## Installation

### From Source

```bash
# Clone the repository
git clone https://github.com/your-repo/fastdelete.git
cd fastdelete

# Install with pip (editable mode)
pip install -e .

# Or install directly
pip install .
```

### Standalone Usage

`fastdelete` requires Python 3.8+ and has **zero external runtime dependencies** (standard library only). You can also run it directly without installation:

```bash
python3 -m fastdelete.cli /path/to/target --yes
```

---

## CLI Usage & Examples

### Basic Deletion

```bash
# Delete a single file (prompts for confirmation)
fastdelete /path/to/file.txt

# Delete a directory tree (prompts to type the exact path to confirm)
fastdelete /path/to/folder

# Skip interactive confirmation
fastdelete /path/to/folder --yes
```

### Dry Run & Verbose Logging

```bash
# Simulate deletion of a directory and view statistics without touching files
fastdelete /path/to/folder --dry-run

# Show verbose real-time actions for each unlinked file
fastdelete /path/to/folder --verbose --yes
```

### High-Performance Multi-Threaded Deletion

```bash
# Run with 8 parallel worker threads
fastdelete /path/to/folder --workers 8 --yes
```

### Handling Read-Only Files (`--force`)

```bash
# Fix permissions on read-only files and directories before unlinking
fastdelete /path/to/folder --force --yes
```

### Filesystem Boundary Protection (`--one-file-system`)

```bash
# Prevent deletion from traversing into mounted filesystems or device boundaries
fastdelete /mnt/data --one-file-system --yes
```

### Advanced Filtering

```bash
# Delete only log files modified more than 30 days ago
fastdelete /var/log/app --include "*.log" --older-than 30d --yes

# Delete files between 10MB and 1GB, excluding git repositories
fastdelete /data/cache --min-size 10M --max-size 1G --exclude "*.git" --yes

# Delete direct children only (depth 1)
fastdelete /tmp/scratch --max-depth 1 --yes

# Delete only files and preserve empty directory structure
fastdelete /path/to/folder --files-only --yes
```

### Files with Unusual Names

```bash
# Targets beginning with a dash (-)
fastdelete -- -unusual-file.txt --yes

# Targets containing newlines, spaces, or quotes
fastdelete "/tmp/folder with spaces and\nnewline" --yes
```

### Structured Error Logging

```bash
# Record any deletion failures to a log file
fastdelete /path/to/target --log /var/log/deletion_errors.log --yes
```

---

## CLI Options Reference

| Option | Flag | Description |
|---|---|---|
| `TARGET` | Positional | One or more file or directory paths to delete. |
| `--yes` | `-y` | Skip interactive confirmation prompts. |
| `--dry-run` | `-n` | Simulate deletion without modifying anything on disk. |
| `--force` | `-f` | Adjust permissions on read-only files to allow deletion. |
| `--workers N` | `-w N` | Number of worker threads for parallel deletion (default: 1). |
| `--verbose` | `-v` | Print detailed action line for each unlinked file or directory. |
| `--quiet` | `-q` | Suppress progress output and summary banners. |
| `--one-file-system` | `-x` | Do not cross filesystem/mount boundaries during traversal. |
| `--include PATTERN` | | Only delete files matching glob pattern (repeatable). |
| `--exclude PATTERN` | | Exclude files/dirs matching glob pattern (repeatable). |
| `--min-size SIZE` | | Minimum file size to delete (e.g. `100M`, `1.5GB`, `500k`). |
| `--max-size SIZE` | | Maximum file size to delete (e.g. `10M`, `100k`). |
| `--older-than DURATION`| | Only delete files older than duration (e.g. `30d`, `12h`, `15m`). |
| `--newer-than DURATION`| | Only delete files newer than duration (e.g. `1d`, `2h`). |
| `--max-depth N` | | Limit directory traversal depth to N levels. |
| `--min-depth N` | | Do not delete items at depth levels less than N. |
| `--files-only` | | Delete only files/symlinks, preserving directory structure. |
| `--dirs-only` | | Delete only empty directories. |
| `--empty-dirs-only` | | Only delete empty directories. |
| `--log FILE` | | Write failure logs and summary to specified file. |
| `--allow-root` | | Allow deleting root filesystem or critical system paths. |
| `--allow-home` | | Allow deleting current user's home directory. |
| `--version` | | Show version and exit. |

---

## Safety Policy & Architecture

### Protected Paths Blacklist

By default, `fastdelete` refuses to delete:
- POSIX root (`/`) and critical system paths (`/boot`, `/etc`, `/usr`, `/var`, `/bin`, `/sbin`, `/lib`, `/lib64`, `/home`, `/root`, `/sys`, `/proc`, `/dev`, `/run`, `/srv`).
- Windows system drives (`C:\`), Windows system roots (`C:\Windows`, `C:\Windows\System32`), `Program Files`, `ProgramData`, and user profiles.
- Current user's home directory (`~`).

Attempting to delete these paths will abort immediately with exit code `2` unless `--allow-root` or `--allow-home` is explicitly supplied alongside secondary confirmation.

### Symbolic Link Handling

`fastdelete` **never follows directory symlinks**. When a directory symlink is encountered during traversal or as the root target:
- It is unlinked directly via `os.unlink()`.
- Its target directory contents are **never** traversed or deleted.

---

## Architecture

```
fastdelete/
├── fastdelete/
│   ├── __init__.py      # Package exports and version metadata
│   ├── cli.py           # Command-line interface and argument parsing
│   ├── scanner.py       # Iterative os.scandir post-order traversal
│   ├── deleter.py       # Deletion engine (single-threaded & worker pool)
│   ├── safety.py        # Target inspection, safety checks & path sanitization
│   ├── progress.py      # Terminal progress and summary rendering
│   ├── filters.py       # Filtering logic (globs, sizes, times, depths)
│   └── errors.py        # Exception hierarchy and DeletionErrorRecord
├── tests/               # Comprehensive pytest test suite
├── pyproject.toml       # Build configuration and packaging metadata
└── README.md            # Documentation and usage guide
```

---

## Running Tests

Run the full test suite with `pytest`:

```bash
pytest
```

Or with coverage report:

```bash
pytest --cov=fastdelete
```
