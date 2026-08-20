# fastdelete ⚡

[![PyPI version](https://img.shields.io/pypi/v/fastdelete.svg?color=blue)](https://pypi.org/project/fastdelete/)
[![Python versions](https://img.shields.io/pypi/pyversions/fastdelete.svg)](https://pypi.org/project/fastdelete/)
[![CI Status](https://github.com/Baba01hacker666/fastdelete/actions/workflows/ci.yml/badge.svg)](https://github.com/Baba01hacker666/fastdelete/actions/workflows/ci.yml)
[![License: MIT](https://img.shields.io/badge/License-MIT-green.svg)](https://opensource.org/licenses/MIT)
[![Code style](https://img.shields.io/badge/code%20style-pep8-orange.svg)](https://peps.python.org/pep-0008/)

A high-performance, enterprise-grade, memory-efficient, and safety-focused filesystem toolkit for ultra-fast directory tree deletion, developer workspace cleaning, secure multi-pass data shredding, safe trash bin management, disk space analysis, and duplicate detection.

---

## ⚡ Key Highlights

- **$O(\text{depth})$ Memory Footprint**: Uses `os.scandir()` with an iterative post-order traversal stack instead of loading full trees into memory or hitting Python's recursion limit. Delete millions of files in mere megabytes of RAM.
- **Direct POSIX & Win32 System Calls**: Performs deletions directly using `os.unlink()` and `os.rmdir()`. **Never invokes subshells (`rm -rf`)** or `shutil.rmtree()`.
- **Native C Engine Acceleration**: Includes optional compiled C extension (`_fastdelete_c.so`) for raw native POSIX syscall throughput.
- **Smart Workspace Cleaners (`fastdelete clean <preset>`)**: One-command instant cleanup presets for **Python**, **Node.js / npm**, **Rust / Cargo**, **C / C++**, **Java / JVM**, **Go**, **Temp**, **Logs**, and composite **all-dev**.
- **DoD / Gutmann Secure Shredder (`fastdelete shred`)**: Cryptographic multi-pass file wiping (Zero-fill, Pseudo-Random, DoD 5220.22-M 3-pass & 7-pass, Gutmann 35-pass) with filename obfuscation, zero-truncation, and hardware fsync.
- **Safe Trash & Recycle Bin (`fastdelete trash`)**: FreeDesktop.org-compliant trash management with `.trashinfo` metadata, instant restoration (`fastdelete restore`), and fast emptying.
- **Disk Usage Tree Analyzer (`fastdelete du`)**: High-speed recursive disk consumption analyzer with largest file and subdirectory breakdown.
- **3-Stage Fast Duplicate Finder (`fastdelete dupes`)**: Rapid duplicate detection using file size grouping, 4KB header/footer sample hashing, full SHA-256 verification, and automatic deduplication / hardlinking.
- **Comprehensive Pattern & Gitignore Filtering**: Filter by glob patterns, regular expressions (`--regex`), file types (`--type f,l,d,s,p`), empty files (`--empty-files-only`), `.gitignore` rules (`--gitignore`), size ranges, modified times, accessed times, and created times.
- **Asyncio Native Python API**: First-class asynchronous non-blocking deletion (`fastdelete.delete_async()`) and synchronous API (`fastdelete.delete()`) for web services (FastAPI, Celery, Django, etc.).
- **Machine-Readable JSON & Event Streaming**: Full `--json` summary and `--ndjson` real-time event streaming for CI/CD pipelines and monitoring agents.
- **Unusual Filename Resilience**: Fully handles long paths, Unicode/emoji names, newlines (`\n`), tabs, spaces, quotes, non-ASCII characters, hidden files, and names beginning with `-`.
- **Strict Safety Engine**: Hard-blocks critical system directories (`/`, `/boot`, `/etc`, `/usr`, `/var`, `/home`, Windows system folders, user home directory) by default.
- **Symlink Protection**: **Never follows directory symlinks**. Unlinks symlinks directly without traversing into linked folders.
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

## 🚀 CLI Commands & Examples

### 1. Ultra-Fast Safe Deletion (`fastdelete`)

```bash
# Delete a directory tree (asks confirmation)
fastdelete /path/to/folder

# Skip confirmation prompts
fastdelete /path/to/folder --yes

# Dry run simulation (calculates metrics without touching disk)
fastdelete /path/to/folder --dry-run

# Parallel worker threads (e.g. for network storage or massive trees)
fastdelete /path/to/folder --workers 8 --yes

# Reset permissions on read-only files automatically
fastdelete /path/to/folder --force --yes

# Filesystem boundary guard (do not cross mount points)
fastdelete /mnt/data --one-file-system --yes
```

### 2. Workspace Cleaner Presets (`fastdelete clean`)

Clean build artifacts, dependency caches, and junk files across your repositories:

```bash
# List all available cleaner presets
fastdelete clean --list

# Clean Python bytecode (__pycache__, *.pyc, .pytest_cache, .mypy_cache, .tox, dist, build)
fastdelete clean python

# Clean Node.js build outputs (node_modules, .next, .nuxt, .turbo, dist, build, *.log)
fastdelete clean node

# Clean Rust Cargo target directory
fastdelete clean rust

# Clean C/C++ build artifacts (*.o, *.so, *.a, build/, cmake-build-*/)
fastdelete clean c

# Clean OS temporary files, swap files, editor backups (*.tmp, *~, .DS_Store, Thumbs.db)
fastdelete clean temp

# Clean all developer caches across the current workspace
fastdelete clean all-dev --dry-run
```

### 3. Secure File Shredding (`fastdelete shred`)

Permanently sanitize sensitive files to prevent forensic data recovery:

```bash
# 3-pass DoD 5220.22-M sanitization (zeros -> ones -> random)
fastdelete shred secret_data.db

# 1-pass fast zero-fill
fastdelete shred /path/to/file.dat --shred-method zero

# 35-pass Gutmann algorithm
fastdelete shred /path/to/keys.pem --shred-method gutmann

# Custom 10-pass overwrite
fastdelete shred confidential.docx --shred-method custom --shred-passes 10
```

### 4. Safe Trash Bin (`fastdelete trash` & `fastdelete restore`)

Move items to the system Trash bin with metadata for easy recovery:

```bash
# Move file or directory to Trash
fastdelete trash /path/to/project_old

# List all items currently in Trash
fastdelete trash --list

# Restore an item from Trash to its original location
fastdelete restore project_old

# Restore to a custom destination
fastdelete restore project_old --dest /path/to/restored_folder

# Empty the Trash bin permanently
fastdelete trash --empty
```

### 5. Disk Usage Tree Analyzer (`fastdelete du`)

High-speed recursive directory inspection:

```bash
# Inspect current directory
fastdelete du

# Show top 20 largest files and subdirectories
fastdelete du /var/log --top 20

# Output analysis as JSON
fastdelete du /data --json
```

### 6. Duplicate File Finder (`fastdelete dupes`)

Find redundant files and reclaim storage:

```bash
# Search for duplicate files larger than 1MB
fastdelete dupes /data --min-size 1M

# Automatically delete duplicate copies (preserves primary copy)
fastdelete dupes /data --delete

# Replace duplicate files with hardlinks to save disk space
fastdelete dupes /data --hardlink
```

### 7. Advanced Filtering

```bash
# Filter by glob patterns
fastdelete /var/log --include "*.log" --older-than 30d --yes

# Filter by regular expressions
fastdelete /tmp/data --regex "^test_\\d+\\.tmp$" --yes

# Delete only 0-byte empty files
fastdelete /path/to/dir --empty-files-only --yes

# Delete only symlinks and regular files, preserving directory structures
fastdelete /path/to/folder --files-only --yes

# Filter by file type ('f' = file, 'l' = symlink, 'd' = directory)
fastdelete /path/to/folder --type f,l --yes

# Filter by access time or creation time
fastdelete /data/cache --accessed-older-than 60d --yes

# Respect .gitignore exclusion rules
fastdelete /repo --gitignore .gitignore --yes
```

### 8. Machine-Readable Output & Real-Time Event Streaming

```bash
# Structured JSON summary
fastdelete /path/to/target --yes --json

# Real-time NDJSON event stream for CI/CD or orchestrators
fastdelete /path/to/target --yes --ndjson
```

---

## 🐍 Python Developer API

`fastdelete` provides a clean, Pythonic synchronous and asynchronous API:

### Synchronous API

```python
import fastdelete

# 1. Simple deletion
stats = fastdelete.delete("/path/to/folder", workers=4)
print(f"Deleted {stats.total_deleted():,} items in {stats.elapsed_seconds():.2f}s")
print(stats.to_json(indent=2))

# 2. Deleting with filters
from fastdelete import DeletionFilter

filter_rules = DeletionFilter(
    include_patterns=["*.tmp", "*.log"],
    min_size=1024 * 1024, # 1 MB
    older_than=86400 * 7,  # 7 days
)
stats = fastdelete.delete("/var/log", filter=filter_rules, dry_run=True)

# 3. Secure file shredding
fastdelete.shred("/path/to/confidential.txt", method="dod", passes=3)

# 4. Trash & Restore
item = fastdelete.trash("/path/to/document.pdf")
fastdelete.restore(item.id)

# 5. Clean workspace preset
fastdelete.clean("python", root_path=".")

# 6. Disk space analysis
summary = fastdelete.analyze("/data", top_n=10)
print(f"Total space: {summary.total_bytes:,} bytes across {summary.total_files:,} files")

# 7. Find duplicate files
report = fastdelete.duplicates("/data", min_size=1024)
print(f"Found {report.total_duplicate_files:,} duplicates wasting {report.total_wasted_bytes:,} bytes")
```

### Asynchronous API (`asyncio`)

Non-blocking deletion for async web frameworks (FastAPI, aiohttp, Celery, asyncio):

```python
import asyncio
import fastdelete

async def cleanup_task():
    stats = await fastdelete.delete_async("/tmp/scratch_job", workers=4)
    return stats.to_dict()

asyncio.run(cleanup_task())
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
| `--shred` | | Securely overwrite file data before unlinking. |
| `--shred-method METHOD`| | Sanitization standard: `zero`, `random`, `dod`, `dod7`, `gutmann`, `custom`. |
| `--shred-passes N` | | Number of overwrite passes for custom shredding. |
| `--trash` | `-t` | Move items to OS/FreeDesktop Trash instead of deleting. |
| `--json` | | Output final summary statistics in JSON format. |
| `--ndjson` / `--stream-json`| | Stream live deletion events as newline-delimited JSON. |
| `--one-file-system` | `-x` | Do not cross filesystem/mount boundaries during traversal. |
| `--include PATTERN` | | Only delete files matching glob pattern (repeatable). |
| `--exclude PATTERN` | | Exclude files/dirs matching glob pattern (repeatable). |
| `--regex REGEX` | | Only delete files matching regular expression (repeatable). |
| `--exclude-regex REGEX`| | Exclude files matching regular expression (repeatable). |
| `--type TYPES` | | Filter by file types: `f` (file), `d` (dir), `l` (symlink), `s` (socket), `p` (fifo). |
| `--min-size SIZE` | | Minimum file size to delete (e.g. `100M`, `1.5GB`, `500k`). |
| `--max-size SIZE` | | Maximum file size to delete (e.g. `10M`, `100k`). |
| `--older-than DURATION`| | Only delete files modified longer ago than duration (e.g. `30d`, `12h`). |
| `--newer-than DURATION`| | Only delete files modified more recently than duration (e.g. `1d`, `2h`). |
| `--accessed-older-than`| | Only delete files accessed longer ago than duration. |
| `--accessed-newer-than`| | Only delete files accessed more recently than duration. |
| `--created-older-than` | | Only delete files created longer ago than duration. |
| `--created-newer-than` | | Only delete files created more recently than duration. |
| `--max-depth N` | | Limit directory traversal depth to N levels. |
| `--min-depth N` | | Do not delete items at depth levels less than N. |
| `--files-only` | | Delete only files/symlinks, preserving directory structure. |
| `--dirs-only` | | Delete only directories; do not delete files. |
| `--empty-dirs-only` | | Only delete empty directories. |
| `--empty-files-only`| | Only delete empty 0-byte regular files. |
| `--gitignore [FILE]` | | Respect exclusion rules from `.gitignore` or custom ignore file. |
| `--log FILE` | | Write failure logs and summary to specified file. |
| `--allow-root` | | Allow deleting root filesystem or critical system paths. |
| `--allow-home` | | Allow deleting current user's home directory. |
| `--version` | | Show version and exit. |

---

## 🛡️ Safety Architecture

### Protected Paths Blacklist
`fastdelete` strictly rejects deletion of critical system paths by default:
- **POSIX**: `/`, `/boot`, `/etc`, `/usr`, `/var`, `/bin`, `/sbin`, `/lib`, `/lib64`, `/home`, `/root`, `/sys`, `/proc`, `/dev`, `/run`, `/srv`, `/mnt`, `/media`.
- **Windows**: `C:\`, `C:\Windows`, `C:\Windows\System32`, `Program Files`, `ProgramData`, user profiles.
- **User Home Directory**: `~` / `$HOME` / `%USERPROFILE%`.

### Inode & Symlink Integrity
1. **Never Follows Directory Symlinks**: Symlinks are unlinked directly without recursing into target directories.
2. **Path Identity Verification**: Inspects target device/inode identity before and after confirmation to prevent symlink race swaps during execution.

---

## 📄 License

MIT License © 2026 Baba01hacker666
