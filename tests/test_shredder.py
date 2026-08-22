"""
Tests for secure file shredder in fastdelete.shredder.
"""

import os
import pytest

from fastdelete.shredder import (
    ShredMethod,
    shred_file,
)


def test_shred_file_zero(tmp_path):
    f = tmp_path / "zero_shred.bin"
    f.write_bytes(b"A" * 4096)
    assert f.exists()

    bytes_shredded = shred_file(f, method=ShredMethod.ZERO, obfuscate_name=False)
    assert bytes_shredded == 4096
    assert not f.exists()


def test_shred_file_dod(tmp_path):
    f = tmp_path / "dod_shred.bin"
    f.write_bytes(b"B" * 2048)
    assert f.exists()

    bytes_shredded = shred_file(f, method=ShredMethod.DOD, passes=3, obfuscate_name=True)
    assert bytes_shredded == 2048
    assert not f.exists()


def test_shred_file_gutmann(tmp_path):
    f = tmp_path / "gutmann_shred.bin"
    f.write_bytes(b"C" * 1024)

    bytes_shredded = shred_file(f, method=ShredMethod.GUTMANN, obfuscate_name=False)
    assert bytes_shredded == 1024
    assert not f.exists()


def test_shred_empty_file(tmp_path):
    f = tmp_path / "empty.txt"
    f.touch()
    assert f.exists()

    bytes_shredded = shred_file(f, method=ShredMethod.ZERO)
    assert bytes_shredded == 0
    assert not f.exists()


def test_shred_symlink_does_not_destroy_target(tmp_path):
    target = tmp_path / "real_target.txt"
    target.write_text("precious target content")

    link = tmp_path / "symlink_to_target.txt"
    try:
        os.symlink(str(target), str(link))
    except (OSError, NotImplementedError):
        pytest.skip("Symlinks not supported on this platform")

    assert link.is_symlink()
    shred_file(link)

    # Symlink is gone, but target must be intact!
    assert not link.exists()
    assert target.exists()
    assert target.read_text() == "precious target content"
