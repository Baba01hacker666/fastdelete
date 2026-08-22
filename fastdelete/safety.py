"""
Safety checks, path resolution, and path sanitization for fastdelete.
"""

from __future__ import annotations

import os
import sys
import stat
import dataclasses
from pathlib import Path
from typing import Optional, Set

from fastdelete.errors import InvalidTargetError, SafetyError


# Standard POSIX critical system directories
POSIX_DANGEROUS_PATHS: Set[str] = {
    "/",
    "/boot",
    "/etc",
    "/usr",
    "/var",
    "/bin",
    "/sbin",
    "/lib",
    "/lib64",
    "/lib32",
    "/libx32",
    "/opt",
    "/root",
    "/home",
    "/sys",
    "/proc",
    "/dev",
    "/run",
    "/srv",
    "/mnt",
    "/media",
}

# Standard Windows critical system environment keys and directory names
WINDOWS_SYSTEM_DIRS: Set[str] = {
    "windows",
    "system32",
    "syswow64",
    "program files",
    "program files (x86)",
    "users",
    "programdata",
    "boot",
    "recovery",
}


def normalize_long_path(path: str) -> str:
    r"""
    On Windows, format long paths with the \\?\ prefix if not already present
    to support paths longer than 260 characters (MAX_PATH).
    On POSIX systems, returns the path unmodified.
    """
    if sys.platform != "win32":
        return path

    abs_path = os.path.abspath(path)
    if abs_path.startswith("\\\\?\\") or abs_path.startswith("\\\\.\\"):
        return abs_path

    if abs_path.startswith("\\\\"):
        # UNC path: \\server\share -> \\?\UNC\server\share
        return "\\\\?\\UNC\\" + abs_path[2:]
    return "\\\\?\\" + abs_path


def safe_path_str(path: str | Path | os.DirEntry) -> str:
    """
    Safely format a file or directory path for terminal display without
    executing escape sequences or corrupting the terminal.

    Escapes control characters (0x00 - 0x1F, 0x7F - 0x9F) such as newlines,
    tabs, carriage returns, and ANSI escape codes (\x1b).
    """
    if isinstance(path, os.DirEntry):
        s = path.path
    elif isinstance(path, Path):
        s = str(path)
    else:
        s = str(path)

    out = []
    for ch in s:
        code = ord(ch)
        if ch == "\n":
            out.append(r"\n")
        elif ch == "\r":
            out.append(r"\r")
        elif ch == "\t":
            out.append(r"\t")
        elif ch == "\b":
            out.append(r"\b")
        elif ch == "\x1b":
            out.append(r"\x1b")
        elif code < 32 or (127 <= code <= 159):
            out.append(f"\\x{code:02x}")
        else:
            out.append(ch)
    return "".join(out)


@dataclasses.dataclass(frozen=True)
class TargetIdentity:
    """Encapsulates the inspected state and metadata of a target."""
    raw_path: str
    abs_path: str
    real_path: str
    st_dev: int
    st_ino: int
    st_mode: int
    st_size: int
    st_mtime: float
    is_symlink: bool
    is_dir: bool
    is_file: bool
    is_special: bool
    type_description: str

    def verify_unchanged(self, target_path: Optional[str] = None) -> tuple[bool, Optional[str]]:
        """
        Verify that the target filesystem object has not changed identity
        (e.g., replaced with a symlink or another file) since inspection.
        """
        check_path = target_path or self.raw_path
        try:
            current_stat = os.lstat(check_path)
        except (FileNotFoundError, OSError) as e:
            return False, f"Target no longer accessible: {e}"

        # On POSIX, st_dev and st_ino uniquely identify an inode
        if sys.platform != "win32":
            if current_stat.st_dev != self.st_dev or current_stat.st_ino != self.st_ino:
                return False, (
                    f"Target identity changed: inode/device mismatch "
                    f"(expected dev={self.st_dev}, ino={self.st_ino}; "
                    f"got dev={current_stat.st_dev}, ino={current_stat.st_ino})"
                )

        current_is_symlink = stat.S_ISLNK(current_stat.st_mode)
        if current_is_symlink != self.is_symlink:
            return False, "Target symlink status changed"

        current_is_dir = stat.S_ISDIR(current_stat.st_mode) and not current_is_symlink
        if current_is_dir != self.is_dir:
            return False, "Target directory status changed"

        return True, None


def get_dangerous_paths() -> Set[str]:
    """Retrieve the set of canonicalized dangerous system paths for the current OS."""
    dangerous = set()

    if sys.platform == "win32":
        # Windows drive roots (C:\, D:\, etc.)
        for letter in "ABCDEFGHIJKLMNOPQRSTUVWXYZ":
            drive = f"{letter}:\\"
            if os.path.exists(drive):
                dangerous.add(os.path.normpath(drive).lower())

        # System directory environment variables
        env_vars = [
            "SystemDrive",
            "SystemRoot",
            "WinDir",
            "ProgramFiles",
            "ProgramFiles(x86)",
            "ProgramData",
            "USERPROFILE",
            "ALLUSERSPROFILE",
            "APPDATA",
            "LOCALAPPDATA",
        ]
        for var in env_vars:
            val = os.environ.get(var)
            if val and os.path.exists(val):
                dangerous.add(os.path.normpath(val).lower())
    else:
        for p in POSIX_DANGEROUS_PATHS:
            dangerous.add(os.path.normpath(p))
            try:
                real_p = os.path.realpath(p)
                dangerous.add(os.path.normpath(real_p))
            except (OSError, ValueError):
                pass

    return dangerous


def get_user_home() -> Optional[str]:
    """Get the resolved home directory path of the current user."""
    try:
        home = str(Path.home().resolve())
        return os.path.normpath(home)
    except Exception:
        home_env = os.environ.get("HOME") or os.environ.get("USERPROFILE")
        if home_env:
            return os.path.normpath(os.path.abspath(home_env))
    return None


def inspect_target(target_path: str | Path) -> TargetIdentity:
    """
    Resolve and inspect a target path using lstat (does NOT follow target symlinks).
    Returns a TargetIdentity with full classification.
    """
    path_str = str(target_path)
    if not path_str or path_str.strip() == "":
        raise InvalidTargetError("Target path cannot be empty.")

    abs_path = os.path.abspath(path_str)
    
    try:
        st = os.lstat(abs_path)
    except FileNotFoundError:
        raise InvalidTargetError(f"Target does not exist: {safe_path_str(abs_path)}")
    except PermissionError as e:
        raise InvalidTargetError(f"Permission denied accessing target {safe_path_str(abs_path)}: {e}")
    except OSError as e:
        raise InvalidTargetError(f"Cannot inspect target {safe_path_str(abs_path)}: {e}")

    try:
        real_path = os.path.realpath(abs_path)
    except Exception:
        real_path = abs_path

    mode = st.st_mode
    is_symlink = stat.S_ISLNK(mode)
    is_dir = stat.S_ISDIR(mode) and not is_symlink
    is_file = stat.S_ISREG(mode) and not is_symlink
    is_special = not (is_dir or is_file or is_symlink)

    # Determine descriptive type
    if is_symlink:
        try:
            target_stat = os.stat(abs_path)
            if stat.S_ISDIR(target_stat.st_mode):
                type_desc = "Symbolic link (pointing to directory)"
            else:
                type_desc = "Symbolic link (pointing to file)"
        except FileNotFoundError:
            type_desc = "Broken symbolic link"
        except OSError:
            type_desc = "Symbolic link"
    elif is_dir:
        type_desc = "Directory"
    elif is_file:
        type_desc = "Regular file"
    elif stat.S_ISFIFO(mode):
        type_desc = "FIFO / Named Pipe"
    elif stat.S_ISSOCK(mode):
        type_desc = "Socket"
    elif stat.S_ISCHR(mode):
        type_desc = "Character device"
    elif stat.S_ISBLK(mode):
        type_desc = "Block device"
    else:
        type_desc = "Special filesystem object"

    return TargetIdentity(
        raw_path=path_str,
        abs_path=abs_path,
        real_path=real_path,
        st_dev=st.st_dev,
        st_ino=st.st_ino,
        st_mode=st.st_mode,
        st_size=st.st_size,
        st_mtime=st.st_mtime,
        is_symlink=is_symlink,
        is_dir=is_dir,
        is_file=is_file,
        is_special=is_special,
        type_description=type_desc,
    )


def classify_target_danger(identity: TargetIdentity) -> tuple:
    """
    Classify how dangerous a deletion target is.

    Returns a tuple (is_root, is_system_critical, is_home):
      - is_root: target (or its resolved path) is a filesystem root.
      - is_system_critical: target matches a protected system path that is
        NOT merely the user's home directory.
      - is_home: target is the current user's home directory.
    """
    target_norm = os.path.normpath(identity.abs_path)
    real_norm = os.path.normpath(identity.real_path)

    is_root = target_norm == "/" or real_norm == "/"
    if sys.platform == "win32":
        target_lower = target_norm.lower()
        if len(target_lower) == 3 and target_lower[1:] == ":\\":
            is_root = True
        real_lower = real_norm.lower()
        if len(real_lower) == 3 and real_lower[1:] == ":\\":
            is_root = True

    user_home = get_user_home()
    home_norm = os.path.normpath(user_home) if user_home else None
    is_home = False
    if home_norm:
        if sys.platform == "win32":
            is_home = (
                target_norm.lower() == home_norm.lower()
                or real_norm.lower() == home_norm.lower()
            )
        else:
            is_home = target_norm == home_norm or real_norm == home_norm

    is_system = False
    dangerous_paths = get_dangerous_paths()
    check_targets = {target_norm, real_norm}
    if sys.platform == "win32":
        check_targets = {t.lower() for t in check_targets}
        home_cmp = home_norm.lower() if home_norm else None
    else:
        home_cmp = home_norm

    for dt in check_targets:
        if dt in dangerous_paths and dt != home_cmp:
            is_system = True
            break

    return is_root, is_system, is_home


def validate_safety(
    identity: TargetIdentity,
    allow_root: bool = False,
    allow_home: bool = False,
) -> None:
    """
    Validate that the target is safe to delete.
    Raises SafetyError if target is dangerous and appropriate override is not provided.
    """
    is_root, is_system, is_home = classify_target_danger(identity)

    if is_root and not allow_root:
        raise SafetyError(
            f"Refusing to delete root filesystem '{safe_path_str(identity.abs_path)}'. "
            f"Root deletion is blocked by safety policy."
        )

    if is_home and not allow_home and not allow_root:
        raise SafetyError(
            f"Refusing to delete user home directory '{safe_path_str(identity.abs_path)}'. "
            f"Override with --allow-home if this is intentional."
        )

    # Protected system directories require --allow-root even when --allow-home
    # is set, unless the matched protected path IS the home directory itself.
    if is_system and not allow_root:
        raise SafetyError(
            f"Refusing to delete critical system directory '{safe_path_str(identity.abs_path)}' "
            f"(matches a protected system path). "
            f"Override with --allow-root if this is intentional."
        )
