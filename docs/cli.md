# 💻 FastDelete CLI Reference

`fastdelete` provides a fast, robust command-line interface with safety protections, interactive confirmation, machine-readable JSON streaming, and specialized subcommands.

---

## 🛠️ Main Deletion Command

```bash
fastdelete [OPTIONS] TARGETS...
```

### Basic Flags

| Flag | Long Option | Description |
|---|---|---|
| `-y` | `--yes` | Skip interactive confirmation prompts and delete immediately. |
| `-n` | `--dry-run` | Simulate deletion without touching or modifying any files on disk. |
| `-f` | `--force` | Reset permissions on read-only files and folders to complete deletion. |
| `-w N` | `--workers N` | Number of worker threads for parallel deletion (default: `1`). |
| `-v` | `--verbose` | Print real-time action lines for each unlinked file or directory. |
| `-q` | `--quiet` | Suppress live progress reporting and summary banners. |
| `-x` | `--one-file-system` | Do not cross filesystem mount boundaries during traversal. |
| | `--log FILE` | Record deletion failures and summary to a specified log file. |
| | `--json` | Output final deletion statistics in formatted JSON. |
| | `--ndjson` / `--stream-json` | Stream live events as newline-delimited JSON objects. |

---

## 🔍 Filtering Options

FastDelete allows granular file and directory selection:

```bash
# Glob pattern matching
fastdelete /var/log --include "*.log" --include "*.tmp" --yes

# Exclude patterns
fastdelete /data --exclude "*.git" --exclude "node_modules" --yes

# Regular expression matching
fastdelete /tmp --regex "^cache_[0-9]+\\.bin$" --yes

# Filter by file type ('f'=regular file, 'd'=dir, 'l'=symlink, 's'=socket, 'p'=fifo)
fastdelete /path/to/folder --type f,l --yes

# Size range filtering
fastdelete /data --min-size 100M --max-size 2GB --yes

# Time-based filtering (mtime, atime, ctime)
fastdelete /tmp --older-than 30d --yes
fastdelete /data/cache --accessed-older-than 60d --yes
fastdelete /data/temp --created-newer-than 1d --yes

# Depth limits
fastdelete /folder --max-depth 2 --min-depth 1 --yes

# Empty file and directory flags
fastdelete /folder --empty-files-only --yes
fastdelete /folder --empty-dirs-only --yes
fastdelete /folder --files-only --yes

# Gitignore integration
fastdelete /repo --gitignore .gitignore --yes
```

---

## 📦 Subcommands

### 1. Cleaner Presets (`fastdelete clean`)
Clean development build artifacts, caches, and dependency folders:

```bash
# List all presets
fastdelete clean --list

# Clean Python repo caches (__pycache__, *.pyc, .pytest_cache, dist, build)
fastdelete clean python /path/to/repo

# Clean Node.js build outputs (node_modules, .next, .nuxt, dist, build, *.log)
fastdelete clean node

# Clean all dev bloat across workspace
fastdelete clean all-dev --dry-run
```

### 2. Secure Shredding (`fastdelete shred`)
Multi-pass cryptographic data wiping:

```bash
# DoD 5220.22-M 3-pass sanitization (zeros -> ones -> random)
fastdelete shred confidential_file.db

# 1-pass fast zero-fill
fastdelete shred sensitive.raw --shred-method zero

# 35-pass Gutmann algorithm
fastdelete shred keys.pem --shred-method gutmann

# Custom 7-pass overwrite
fastdelete shred /data/secret.tar --shred-method custom --shred-passes 7
```

### 3. Safe Trash Bin (`fastdelete trash` & `fastdelete restore`)
FreeDesktop.org-compliant safe deletion:

```bash
# Move folder or file to Trash
fastdelete trash /path/to/old_folder

# List items in Trash
fastdelete trash --list

# Restore item to original location
fastdelete restore old_folder

# Empty Trash bin permanently
fastdelete trash --empty
```

### 4. Disk Usage Analyzer (`fastdelete du`)
High-speed recursive directory inspection:

```bash
# Analyze current directory
fastdelete du

# Show top 20 largest files and subdirectories
fastdelete du /var/log --top 20

# Output as JSON
fastdelete du /data --json
```

### 5. Duplicate File Finder (`fastdelete dupes`)
Find and clean redundant files:

```bash
# Find duplicate files larger than 1MB
fastdelete dupes /data --min-size 1M

# Automatically delete duplicates (retains primary copy)
fastdelete dupes /data --delete

# Deduplicate by replacing redundant files with hardlinks
fastdelete dupes /data --hardlink
```

### 6. Benchmark Suite (`fastdelete bench`)
Run the built-in performance comparison benchmark:

```bash
fastdelete bench
```
