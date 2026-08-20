# fastdelete

[![PyPI version](https://img.shields.io/pypi/v/fastdelete.svg?color=blue)](https://pypi.org/project/fastdelete/)
[![Python versions](https://img.shields.io/pypi/pyversions/fastdelete.svg)](https://pypi.org/project/fastdelete/)
[![CI Status](https://github.com/Baba01hacker666/fastdelete/actions/workflows/ci.yml/badge.svg)](https://github.com/Baba01hacker666/fastdelete/actions/workflows/ci.yml)
[![License: MIT](https://img.shields.io/badge/License-MIT-green.svg)](https://opensource.org/licenses/MIT)
[![Code style](https://img.shields.io/badge/code%20style-pep8-orange.svg)](https://peps.python.org/pep-0008/)

A production-grade, memory-efficient, and safety-focused Python CLI tool for deleting massive directory trees, millions of files, and items with extremely long, non-ASCII, or unusual filenames.

---

## ⚡ Key Highlights

- **$O(\text{depth})$ Memory Footprint**: Uses `os.scandir()` with an iterative post-order traversal stack instead of loading full trees into memory or hitting Python's recursion limit. Delete millions of files in mere megabytes of RAM.
- **Direct POSIX & Win32 System Calls**: Performs deletions directly using `os.unlink()` for files/symlinks/pipes/devices and `os.rmdir()` for directories. **Never invokes subshells (`rm -rf`)** or `shutil.rmtree()`.
- **Unusual Filename Resilience**: Fully handles long paths, Unicode/emoji names, newlines (`\n`), tabs, spaces, quotes, non-ASCII characters, hidden files, and names beginning with `-`.
- **Terminal Protection**: Safely sanitizes control characters during terminal output to prevent ANSI sequence execution or terminal corruption.
- **Strict Safety Engine**: Hard-blocks critical system directories (`/`, `/boot`, `/etc`, `/usr`, `/var`, `/home`, Windows system folders, user home directory) by default.
- **Symlink Protection**: **Never follows directory symlinks**. Unlinks symlinks directly without traversing into linked folders.
- **Dry-Run Mode (`--dry-run` / `-n`)**: Safely simulates deletion operations, verifies filters, and reports statistics without modifying disk contents.
- **Multi-Threaded Worker Pool (`--workers N`)**: Accelerates deletion throughput across network drives (NFS, SMB) and cloud mounts while strictly preserving post-order directory removal.
- **Force Mode (`--force` / `-f`)**: Automatically resets permissions on read-only files and directories where permissible by the OS.
- **Filesystem Boundary Guard (`--one-file-system` / `-x`)**: Traversal will not cross mount points or device boundaries.
- **Zero External Runtime Dependencies**: Built entirely on standard Python 3.8+ library primitives.

---

## 📦 Installation

### From PyPI (Recommended)

```bash
pip install fastdelete
```

### From Source

```bash
git clone https://github.com/Baba01hacker666/fastdelete.git
cd fastdelete
pip install .
```

### Standalone (Zero Install)

`fastdelete` has zero third-party runtime dependencies. You can run it directly with standard Python 3.8+:

```bash
python3 -m fastdelete.cli /path/to/target --yes
```

---

## 🚀 CLI Examples

### Basic Deletion

```bash
# Delete a single file (asks confirmation)
fastdelete /path/to/file.txt

# Delete a directory tree (prompts to type exact path to confirm)
fastdelete /path/to/folder

# Skip confirmation prompts
fastdelete /path/to/folder --yes
```

### Dry Run & Verbose Logging

```bash
# Simulate deletion and display calculated statistics without touching disk
fastdelete /path/to/folder --dry-run

# Show real-time verbose output for each unlinked file and directory
fastdelete /path/to/folder --verbose --yes
```

### Multi-Threaded Parallel Deletion

```bash
# Accelerate deletion on network mounts using 8 parallel worker threads
fastdelete /path/to/folder --workers 8 --yes
```

### Read-Only Files & Force Mode

```bash
# Fix permissions on read-only files and directories before unlinking
fastdelete /path/to/folder --force --yes
```

### Mount / Filesystem Boundary Protection

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

### Handling Files with Dangerous / Unusual Names

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

## ⚙️ CLI Options Reference

| Option | Flag | Description |
|---|---|---|
| `TARGET` | Positional | One or more file or directory paths to delete. |
| `--yes` | `-y` | Skip interactive confirmation prompts. |
| `--dry-run` | `-n` | Simulate deletion without modifying anything on disk. |
| `--force` | `-f` | Adjust permissions on read-only files to allow deletion. |
| `--workers N` | `-w N` | Number of worker threads for parallel deletion (default: `1`). |
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
| `--dirs-only` | | Delete only directories; do not delete files. |
| `--empty-dirs-only` | | Only delete empty directories. |
| `--log FILE` | | Write failure logs and summary to specified file. |
| `--allow-root` | | Allow deleting root filesystem or critical system paths. |
| `--allow-home` | | Allow deleting current user's home directory. |
| `--version` | | Show version and exit. |

---

## 🛡️ Safety Architecture

### Protected Paths Blacklist
`fastdelete` rejects deletion of critical system paths by default:
- **POSIX**: `/`, `/boot`, `/etc`, `/usr`, `/var`, `/bin`, `/sbin`, `/lib`, `/lib64`, `/home`, `/root`, `/sys`, `/proc`, `/dev`, `/run`, `/srv`.
- **Windows**: `C:\`, `C:\Windows`, `C:\Windows\System32`, `Program Files`, `ProgramData`, user profiles.
- **User Home Directory**: `~` / `$HOME` / `%USERPROFILE%`.

### Symlink Integrity
`fastdelete` **never follows directory symlinks**. When a directory symlink is encountered:
1. The symlink itself is unlinked via `os.unlink()`.
2. Target directory contents are **never** traversed or deleted.

---

## 🏷️ Tags & Keywords

`cli`, `fast`, `delete`, `rm`, `remove`, `unlink`, `filesystem`, `safety`, `large-files`, `deep-trees`, `multithreaded`, `performance`

---

## 📄 License

MIT License © 2026 Baba01hacker666
