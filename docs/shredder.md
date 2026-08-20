# 🛡️ Secure Data Shredder Guide

FastDelete includes an enterprise-grade multi-pass cryptographic data sanitization engine in `fastdelete.shredder` and the `fastdelete shred` CLI subcommand.

---

## 🔒 Why Standard `rm` / `unlink` Leaves Data at Risk

When a normal `unlink()` or `rm` command deletes a file:
1. The operating system removes the directory entry and marks the storage blocks as available.
2. **The actual file data remains on disk** until overwritten by future write operations.
3. Forensic tools and data recovery software can recover sensitive documents, keys, database dumps, and credentials.

---

## ⚙️ Sanitization Algorithms

FastDelete supports multiple sanitization standards:

### 1. DoD 5220.22-M (Default: `--shred-method dod`)
The United States Department of Defense standard for media sanitization:
- **Pass 1**: Overwrite all bytes with `0x00` (zeros).
- **Pass 2**: Overwrite all bytes with `0xFF` (ones).
- **Pass 3**: Overwrite all bytes with cryptographically secure pseudo-random bytes.

### 2. DoD 5220.22-M (ECE) 7-Pass (`--shred-method dod7`)
Extended 7-pass military sanitization:
- Alternating bit patterns (`0x00`, `0xFF`, `0xAA`, `0x55`, `0x96`, `0x69`) followed by random noise.

### 3. Gutmann 35-Pass Algorithm (`--shred-method gutmann`)
Developed by Peter Gutmann (1996) to defeat magnetic force microscopy:
- 4 passes of random data
- 27 passes of tailored magnetic bit transitions
- 4 final passes of random data

### 4. Zero-Fill (`--shred-method zero`)
- High-speed 1-pass sanitization overwriting all bytes with `0x00`.

### 5. Pseudo-Random (`--shred-method random`)
- 1-pass sanitization using system cryptographic randomness (`secrets.token_bytes`).

---

## 🔐 Advanced Security Safeguards

1. **Hardware `fsync()` Flush**:
   Every pass explicitly issues `os.fsync()` / `fdatasync()` system calls to force hardware write caches to flush to physical flash or platter storage before proceeding.

2. **File Truncation**:
   After overwrite passes complete, the file descriptor is truncated to 0 bytes (`ftruncate`) and synced before unlinking.

3. **Filename Obfuscation**:
   To prevent metadata and journal recovery of sensitive filenames, FastDelete renames the file multiple times to random alphanumeric strings in the same directory before executing the final `unlink()`.

4. **Symlink Immunity**:
   Symlinks are never shredded through the link target; the symlink itself is removed directly.
