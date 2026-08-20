"""
Secure file shredding and data sanitization for fastdelete.
Implements DoD 5220.22-M, Gutmann, zero-fill, and pseudo-random multi-pass wiping.
"""

from __future__ import annotations

import os
import random
import secrets
import string
import time
from enum import Enum
from pathlib import Path
from typing import Optional, Union

from fastdelete.errors import FastDeleteError
from fastdelete.safety import normalize_long_path


class ShredMethod(str, Enum):
    """Supported secure wiping standards and patterns."""
    ZERO = "zero"           # 1 pass with 0x00
    RANDOM = "random"       # 1 pass with random bytes
    DOD = "dod"             # DoD 5220.22-M 3-pass (zeros -> ones -> random)
    DOD_7PASS = "dod7"      # DoD 5220.22-M (ECE) 7-pass
    GUTMANN = "gutmann"     # Peter Gutmann 35-pass algorithm
    CUSTOM = "custom"       # Custom N passes of random bytes


_BUFFER_SIZE = 64 * 1024  # 64 KB write buffer


def _get_pass_bytes(pass_index: int, total_passes: int, method: ShredMethod, size: int) -> bytes:
    """Generate the byte pattern for a specific wipe pass."""
    if method == ShredMethod.ZERO:
        return b"\x00" * size

    if method == ShredMethod.RANDOM or method == ShredMethod.CUSTOM:
        return secrets.token_bytes(size)

    if method == ShredMethod.DOD:
        # DoD 5220.22-M (3 passes: 0x00, 0xFF, Random)
        if pass_index == 0:
            return b"\x00" * size
        elif pass_index == 1:
            return b"\xFF" * size
        else:
            return secrets.token_bytes(size)

    if method == ShredMethod.DOD_7PASS:
        # 7-pass DoD 5220.22-M (ECE)
        patterns = [b"\x00", b"\xFF", b"\xAA", b"\x55", b"\x96", b"\x69"]
        if pass_index < len(patterns):
            return patterns[pass_index] * size
        return secrets.token_bytes(size)

    if method == ShredMethod.GUTMANN:
        # Gutmann 35 passes: 4 random + 27 specific magnetic patterns + 4 random
        if pass_index < 4 or pass_index >= 31:
            return secrets.token_bytes(size)
        gutmann_patterns = [
            b"\x55", b"\xAA", b"\x92\x49\x24", b"\x49\x24\x92", b"\x24\x92\x49",
            b"\x00", b"\x11", b"\x22", b"\x33", b"\x44", b"\x55", b"\x66",
            b"\x77", b"\x88", b"\x99", b"\xAA", b"\xBB", b"\xCC", b"\xDD",
            b"\xEE", b"\xFF", b"\x92\x49\x24", b"\x49\x24\x92", b"\x24\x92\x49",
            b"\x6D\xB6\xDB", b"\xB6\xDB\x6D", b"\xDB\x6D\xB6"
        ]
        pat = gutmann_patterns[(pass_index - 4) % len(gutmann_patterns)]
        repetitions = (size // len(pat)) + 1
        return (pat * repetitions)[:size]

    return secrets.token_bytes(size)


def _get_num_passes(method: ShredMethod, custom_passes: Optional[int] = None) -> int:
    """Determine the number of passes for the given method."""
    if custom_passes is not None and custom_passes > 0:
        return custom_passes
    if method == ShredMethod.ZERO:
        return 1
    if method == ShredMethod.RANDOM:
        return 1
    if method == ShredMethod.DOD:
        return 3
    if method == ShredMethod.DOD_7PASS:
        return 7
    if method == ShredMethod.GUTMANN:
        return 35
    return 3


def _obfuscate_and_unlink(path: str) -> None:
    """
    Obfuscate the filename by renaming it to multiple random alphanumeric names
    before unlinking, preventing directory entry / filesystem journal recovery.
    """
    dirname = os.path.dirname(path)
    base_name = os.path.basename(path)
    curr_path = path

    # Attempt up to 3 random renames in the same directory
    for _ in range(3):
        rand_name = "".join(random.choices(string.ascii_letters + string.digits, k=max(8, len(base_name))))
        new_path = os.path.join(dirname, rand_name)
        try:
            os.rename(curr_path, new_path)
            curr_path = new_path
        except OSError:
            break

    try:
        os.unlink(curr_path)
    except FileNotFoundError:
        pass


def shred_file(
    file_path: Union[str, Path],
    method: Union[ShredMethod, str] = ShredMethod.DOD,
    passes: Optional[int] = None,
    zero_fill_final: bool = True,
    obfuscate_name: bool = True,
) -> int:
    """
    Securely shred a file by overwriting its contents with multi-pass patterns,
    flushing writes to physical disk, truncating, and unlinking.

    Returns the number of bytes overwritten.
    """
    raw_path = str(file_path)
    path = normalize_long_path(raw_path)

    if isinstance(method, str):
        try:
            method = ShredMethod(method.lower())
        except ValueError:
            method = ShredMethod.CUSTOM

    num_passes = _get_num_passes(method, passes)

    try:
        st = os.lstat(path)
    except FileNotFoundError:
        return 0

    # If it's a symlink, do not follow it! Unlink symlink directly.
    if os.path.islink(path):
        os.unlink(path)
        return 0

    # If it's a directory, cannot shred as file
    if os.path.isdir(path):
        raise IsADirectoryError(f"Cannot shred directory as a file: {path}")

    file_size = st.st_size

    # If file is empty, just truncate/obfuscate and unlink
    if file_size == 0:
        if obfuscate_name:
            _obfuscate_and_unlink(path)
        else:
            os.unlink(path)
        return 0

    # Overwrite passes
    try:
        flags = os.O_WRONLY
        if hasattr(os, "O_BINARY"):
            flags |= os.O_BINARY

        fd = os.open(path, flags)
        try:
            for p in range(num_passes):
                os.lseek(fd, 0, os.SEEK_SET)
                bytes_left = file_size
                while bytes_left > 0:
                    chunk_size = min(_BUFFER_SIZE, bytes_left)
                    data = _get_pass_bytes(p, num_passes, method, chunk_size)
                    os.write(fd, data)
                    bytes_left -= chunk_size

                # Flush to physical storage
                try:
                    os.fsync(fd)
                except OSError:
                    pass

            # Optional final zero pass if last pass wasn't zeros
            if zero_fill_final and method != ShredMethod.ZERO:
                os.lseek(fd, 0, os.SEEK_SET)
                zero_buf = b"\x00" * _BUFFER_SIZE
                bytes_left = file_size
                while bytes_left > 0:
                    chunk_size = min(_BUFFER_SIZE, bytes_left)
                    os.write(fd, zero_buf[:chunk_size])
                    bytes_left -= chunk_size
                try:
                    os.fsync(fd)
                except OSError:
                    pass

            # Truncate file to 0 bytes
            try:
                os.ftruncate(fd, 0)
                os.fsync(fd)
            except OSError:
                pass
        finally:
            os.close(fd)

    except PermissionError:
        # Try chmod if read-only
        try:
            os.chmod(path, 0o666)
            return shred_file(
                file_path=path,
                method=method,
                passes=passes,
                zero_fill_final=zero_fill_final,
                obfuscate_name=obfuscate_name,
            )
        except Exception as e:
            raise FastDeleteError(f"Failed to shred file '{path}': {e}") from e

    # Obfuscate filename and remove
    if obfuscate_name:
        _obfuscate_and_unlink(path)
    else:
        try:
            os.unlink(path)
        except FileNotFoundError:
            pass

    return file_size
