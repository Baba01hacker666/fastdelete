# fastdelete ⚡

[![PyPI version](https://img.shields.io/pypi/v/fastdelete.svg?color=blue)](https://pypi.org/project/fastdelete/)
[![Python versions](https://img.shields.io/pypi/pyversions/fastdelete.svg)](https://pypi.org/project/fastdelete/)
[![CI Status](https://github.com/Baba01hacker666/fastdelete/actions/workflows/ci.yml/badge.svg)](https://github.com/Baba01hacker666/fastdelete/actions/workflows/ci.yml)
[![License: MIT](https://img.shields.io/badge/License-MIT-green.svg)](https://opensource.org/licenses/MIT)

**FastDelete** is a high-performance, safety-focused filesystem toolkit for ultra-fast directory deletion, workspace cache cleaning, secure data shredding, safe trash bin management, and disk inspection.

---

## ⚡ Highlights

- **$O(\text{depth})$ Memory Footprint**: Deletes millions of files in mere megabytes of RAM without recursion limits.
- **Direct System Calls**: Uses native `os.unlink()` and `os.rmdir()` — never shells out to `rm -rf`.
- **Optional Native C Accelerator**: High-throughput POSIX C engine compiled for maximum I/O performance.
- **Developer Cleaner Presets**: Instant cleaning for Python, Node.js, Rust, C/C++, Java, temp files, and logs.
- **DoD & Gutmann Shredder**: Cryptographic multi-pass sanitization with filename obfuscation and hardware `fsync`.
- **Safe Trash & Restore**: FreeDesktop.org Trash specification compliance with instant restoration.
- **Disk Usage & Duplicate Finder**: High-speed recursive directory tree sizing and 3-stage duplicate detection.
- **Zero Runtime Dependencies**: Built entirely on standard Python 3.8+ primitives.

## 📦 Installation

### From PyPI
```bash
pip install fastdelete
```

### From Source (Local Development)
```bash
git clone https://github.com/Baba01hacker666/fastdelete.git
cd fastdelete
pip install -e .
```

### Standalone (Zero Install)
```bash
python3 -m fastdelete.cli /path/to/folder --yes
```

---

## 🚀 Quick Start

### 1. Ultra-Fast Deletion
```bash
# Delete with confirmation prompt
fastdelete /path/to/large_folder

# Delete immediately without prompt
fastdelete /path/to/large_folder --yes

# Parallel deletion with 8 worker threads
fastdelete /path/to/large_folder --workers 8 --yes

# Dry run preview (simulate without deleting)
fastdelete /path/to/large_folder --dry-run
```

### 2. Workspace Cleaner Presets
```bash
# Clean Python bytecode & caches (__pycache__, *.pyc, .pytest_cache, dist)
fastdelete clean python

# Clean Node.js build bloat (node_modules, .next, .nuxt, dist, *.log)
fastdelete clean node

# Clean all dev build caches in current directory
fastdelete clean all-dev
```

### 3. Secure File Shredding
```bash
# Overwrite with DoD 5220.22-M standard (zeros -> ones -> random)
fastdelete shred secret_keys.pem

# 35-pass Gutmann sanitization
fastdelete shred confidential.db --shred-method gutmann
```

### 4. Safe Trash & Restore
```bash
# Move to system Trash bin
fastdelete trash /path/to/old_project

# List items in Trash
fastdelete trash --list

# Restore item from Trash
fastdelete restore old_project
```

### 5. Disk Space & Duplicate Analysis
```bash
# Inspect recursive disk usage and top hogs
fastdelete du /var/log --top 10

# Find duplicate files and delete redundant copies
fastdelete dupes /data --delete
```

---

## 🐍 Python Developer API

FastDelete provides both synchronous and `asyncio` non-blocking APIs:

```python
import fastdelete

# 1. Simple deletion
stats = fastdelete.delete("/tmp/cache_folder", workers=4)
print(f"Deleted {stats.total_deleted():,} items in {stats.elapsed_seconds():.2f}s")

# 2. Async deletion (FastAPI / aiohttp / Celery)
import asyncio

async def main():
    stats = await fastdelete.delete_async("/tmp/scratch", workers=4)
    print(stats.to_dict())

asyncio.run(main())

# 3. Clean workspace preset
fastdelete.clean("python", root_path=".")

# 4. Secure shredding
fastdelete.shred("/path/to/secrets.json", method="dod")

# 5. Disk usage analysis
summary = fastdelete.analyze("/var/log", top_n=5)
```

---

## 📚 Complete Documentation

Explore the detailed guides in the [`docs/`](docs/index.md) folder:

| Guide | Description |
|---|---|
| **[CLI Reference](docs/cli.md)** | Complete CLI syntax, all flags, filtering options, and subcommands. |
| **[Python Developer API](docs/api.md)** | Full API reference, classes, async functions, filters, and event callbacks. |
| **[Architecture & Safety](docs/architecture.md)** | $O(\text{depth})$ iterative traversal, symlink safety, and system protection blacklists. |
| **[Secure Shredder](docs/shredder.md)** | DoD 5220.22-M, Gutmann, filename obfuscation, and hardware flushing. |
| **[Workspace Presets](docs/presets.md)** | Built-in cleaning rules for Python, Node, Rust, C/C++, Java, temp, and logs. |
| **[Trash Bin & Recovery](docs/trash.md)** | FreeDesktop.org Trash specification, `.trashinfo` format, and restoration. |
| **[Benchmarks](docs/benchmarks.md)** | Performance measurements across 50,000+ files and comparisons with `rm -rf`. |

---

## 🛡️ Safety Architecture

- **Protected System Paths**: Rejects deletion of `/`, `/boot`, `/etc`, `/usr`, `/var`, `/home`, `C:\Windows`, or user `$HOME` by default.
- **Symlink Protection**: **Never follows directory symlinks** — unlinks the symlink directly without modifying target folders.
- **Device & Inode Verification**: Verifies inode identity before root removal to prevent race-condition symlink swaps.

---

## 📄 License

MIT License © 2026 Baba01hacker666
