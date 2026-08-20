# 🏗️ FastDelete Architecture & Safety Guarantees

FastDelete is designed from the ground up for maximum speed, $O(\text{depth})$ memory efficiency, and absolute filesystem safety.

---

## ⚡ Traversal Engine ($O(\text{depth})$ Memory Footprint)

Traditional recursive directory deletion approaches (`shutil.rmtree()` or naive recursion) encounter two fatal limitations:
1. **Memory Exhaustion**: Storing entire directory trees in memory crashes when processing trees with tens of millions of files.
2. **Recursion Limit**: Deeply nested folder structures exceed Python's maximum recursion stack depth (`RecursionError`).

### How FastDelete Solves This:
FastDelete uses **streaming `os.scandir()` iterators** managed on an **iterative post-order stack**:
- **Constant Memory per Directory Level**: Only the active directory iterator at each level of depth is kept open in memory.
- **Strict Post-Order Removal**: Child entries (files, symlinks, sockets, fifos) are processed and deleted before the parent directory is removed via `os.rmdir()`.
- **Arbitrary Tree Depth**: Trees thousands of levels deep are processed without recursion or memory bloat.

```
       [Root Dir]
      /          \
  [Dir A]      [Dir B]
  /     \         |
File1  File2    File3

1. Stream Dir A -> Unlink File1, Unlink File2
2. Remove Dir A (rmdir)
3. Stream Dir B -> Unlink File3
4. Remove Dir B (rmdir)
5. Remove Root Dir (rmdir)
```

---

## 🚀 Native POSIX C Acceleration Engine

When the target deletion does not require custom user filters or verbosity, FastDelete automatically routes execution to a compiled C engine (`fastdelete/_fastdelete_c.so`).

### Key C Engine Features:
- **Direct System Calls**: Uses POSIX `opendir()`, `readdir()`, `unlink()`, and `rmdir()`.
- **Zero Python Overhead**: Bypasses Python object allocation and GIL context switching during file unlinking loops.
- **Dynamic Growth Stack**: Stack frames dynamically double in capacity (`realloc`) allowing arbitrary directory nesting.
- **Graceful Fallback**: If a C compiler is not available on the target system, FastDelete transparently falls back to the pure Python streaming engine.

---

## 🛡️ Strict Safety Engine

### 1. System Directories Blacklist
FastDelete hard-blocks deletion of critical system directories by default:
- **Linux / POSIX**: `/`, `/boot`, `/etc`, `/usr`, `/var`, `/bin`, `/sbin`, `/lib`, `/lib64`, `/home`, `/root`, `/sys`, `/proc`, `/dev`, `/run`, `/srv`, `/mnt`, `/media`.
- **Windows**: `C:\`, `C:\Windows`, `C:\Windows\System32`, `Program Files`, `ProgramData`, user profiles.
- **User Home**: `$HOME` / `%USERPROFILE%`.

System directory deletion requires explicit override flags (`--allow-root` or `--allow-home`) and an interactive typing confirmation (`DELETE`).

### 2. Symlink Protection (No Follow)
FastDelete **never follows directory symlinks**.
- When a directory symlink is encountered, `os.unlink()` removes the symlink pointer itself.
- Target folders and their contents are **never traversed or modified**.

### 3. Inode Identity Verification
Before removing a root target directory, FastDelete inspects `st_dev` and `st_ino` (device and inode numbers) to verify the target directory was not replaced by a symlink race condition during execution.
