"""
Tests for fastdelete safety checks, target inspection, and path sanitization.
"""

import os
import sys
import pytest
from pathlib import Path

from fastdelete.errors import InvalidTargetError, SafetyError
from fastdelete.safety import (
    get_dangerous_paths,
    get_user_home,
    inspect_target,
    safe_path_str,
    validate_safety,
)


def test_safe_path_str_escapes_control_characters():
    """Verify that control characters and escape codes are sanitized."""
    assert safe_path_str("/tmp/test\nfile.txt") == r"/tmp/test\nfile.txt"
    assert safe_path_str("/tmp/test\rfile.txt") == r"/tmp/test\rfile.txt"
    assert safe_path_str("/tmp/test\tfile.txt") == r"/tmp/test\tfile.txt"
    assert safe_path_str("/tmp/test\x1b[31mfile.txt") == r"/tmp/test\x1b[31mfile.txt"
    assert safe_path_str("/tmp/normal_file.txt") == "/tmp/normal_file.txt"


def test_inspect_target_regular_file(tmp_path):
    """Test inspection of a regular file."""
    file_path = tmp_path / "test_file.txt"
    file_path.write_text("hello world")

    identity = inspect_target(str(file_path))
    assert identity.is_file is True
    assert identity.is_dir is False
    assert identity.is_symlink is False
    assert identity.type_description == "Regular file"
    assert identity.st_size == 11
    
    unchanged, msg = identity.verify_unchanged()
    assert unchanged is True
    assert msg is None


def test_inspect_target_directory(tmp_path):
    """Test inspection of a directory."""
    dir_path = tmp_path / "test_dir"
    dir_path.mkdir()

    identity = inspect_target(str(dir_path))
    assert identity.is_file is False
    assert identity.is_dir is True
    assert identity.is_symlink is False
    assert identity.type_description == "Directory"


def test_inspect_target_symlink_to_file(tmp_path):
    """Test inspection of a symlink pointing to a file."""
    target = tmp_path / "target.txt"
    target.write_text("sample")
    link = tmp_path / "link.txt"
    link.symlink_to(target)

    identity = inspect_target(str(link))
    assert identity.is_symlink is True
    assert identity.is_dir is False
    assert "Symbolic link" in identity.type_description


def test_inspect_target_symlink_to_directory(tmp_path):
    """Test inspection of a symlink pointing to a directory."""
    target_dir = tmp_path / "target_dir"
    target_dir.mkdir()
    link_dir = tmp_path / "link_dir"
    link_dir.symlink_to(target_dir)

    identity = inspect_target(str(link_dir))
    assert identity.is_symlink is True
    # The symlink itself is NOT a directory
    assert identity.is_dir is False
    assert "Symbolic link (pointing to directory)" in identity.type_description


def test_inspect_target_broken_symlink(tmp_path):
    """Test inspection of a broken symlink."""
    non_existent = tmp_path / "non_existent.txt"
    link = tmp_path / "broken_link.txt"
    link.symlink_to(non_existent)

    identity = inspect_target(str(link))
    assert identity.is_symlink is True
    assert identity.type_description == "Broken symbolic link"


def test_inspect_target_nonexistent():
    """Test that inspect_target raises InvalidTargetError for missing paths."""
    with pytest.raises(InvalidTargetError):
        inspect_target("/path/that/does/not/exist_12345")


def test_safety_refuses_root():
    """Verify that root directory deletion is refused by default."""
    root_identity = inspect_target("/")
    with pytest.raises(SafetyError) as exc_info:
        validate_safety(root_identity, allow_root=False)
    assert "Refusing to delete root" in str(exc_info.value)


def test_safety_allows_root_with_override():
    """Verify that root directory deletion check passes if allow_root=True."""
    root_identity = inspect_target("/")
    validate_safety(root_identity, allow_root=True)


def test_safety_refuses_system_directories():
    """Verify that critical system directories (/etc, /usr, /boot, /var) are refused."""
    for sys_dir in ["/etc", "/usr", "/boot", "/var", "/bin", "/home"]:
        if os.path.exists(sys_dir):
            identity = inspect_target(sys_dir)
            with pytest.raises(SafetyError) as exc_info:
                validate_safety(identity, allow_root=False)
            assert "Refusing to delete" in str(exc_info.value)


def test_safety_refuses_user_home():
    """Verify that the current user's home directory is refused unless overridden."""
    user_home = get_user_home()
    if user_home and os.path.exists(user_home):
        identity = inspect_target(user_home)
        with pytest.raises(SafetyError) as exc_info:
            validate_safety(identity, allow_home=False, allow_root=False)
        assert "user home directory" in str(exc_info.value)

        # Passes with allow_home
        validate_safety(identity, allow_home=True, allow_root=False)


def test_safety_allows_temp_directories(tmp_path):
    """Verify that normal temporary user directories pass safety validation."""
    identity = inspect_target(str(tmp_path))
    validate_safety(identity)
