"""
Tests for fastdelete filters, size/duration parsing, and traversal rules.
"""

import os
import time
import pytest

from fastdelete.errors import FilterParseError
from fastdelete.filters import (
    DeletionFilter,
    parse_duration,
    parse_size,
)


def test_parse_size_valid():
    """Test valid size string parsing across multiple units."""
    assert parse_size("100") == 100
    assert parse_size("100B") == 100
    assert parse_size("1k") == 1024
    assert parse_size("10KB") == 10 * 1024
    assert parse_size("2MiB") == 2 * 1024 * 1024
    assert parse_size("1.5M") == int(1.5 * 1024 * 1024)
    assert parse_size("1G") == 1024 * 1024 * 1024
    assert parse_size("2.5GB") == int(2.5 * 1024 * 1024 * 1024)
    assert parse_size("1T") == 1024 * 1024 * 1024 * 1024


def test_parse_size_invalid():
    """Test invalid size strings raise FilterParseError."""
    with pytest.raises(FilterParseError):
        parse_size("")
    with pytest.raises(FilterParseError):
        parse_size("invalid")
    with pytest.raises(FilterParseError):
        parse_size("100XYZ")


def test_parse_duration_valid():
    """Test valid duration string parsing across various units."""
    assert parse_duration("30s") == 30.0
    assert parse_duration("10m") == 600.0
    assert parse_duration("2h") == 7200.0
    assert parse_duration("3d") == 3 * 86400.0
    assert parse_duration("1w") == 7 * 86400.0
    assert parse_duration("1y") == 365 * 86400.0
    assert parse_duration("1.5d") == 1.5 * 86400.0


def test_parse_duration_invalid():
    """Test invalid duration strings raise FilterParseError."""
    with pytest.raises(FilterParseError):
        parse_duration("")
    with pytest.raises(FilterParseError):
        parse_duration("not_a_duration")
    with pytest.raises(FilterParseError):
        parse_duration("100lightyears")


def test_filter_include_and_exclude(tmp_path):
    """Test include and exclude glob filtering on files."""
    f1 = tmp_path / "app.log"
    f1.write_text("log content")
    f2 = tmp_path / "app.py"
    f2.write_text("code content")
    f3 = tmp_path / "secret.log"
    f3.write_text("secret log")

    with os.scandir(str(tmp_path)) as it:
        entries = {e.name: e for e in it}

    filt = DeletionFilter(
        include_patterns=["*.log"],
        exclude_patterns=["secret*"],
    )

    # app.log: included and not excluded -> matches
    match1, _ = filt.matches_file(entries["app.log"], depth=1, rel_path="app.log")
    assert match1 is True

    # app.py: not included -> does not match
    match2, reason2 = filt.matches_file(entries["app.py"], depth=1, rel_path="app.py")
    assert match2 is False
    assert "include pattern" in reason2

    # secret.log: excluded -> does not match
    match3, reason3 = filt.matches_file(entries["secret.log"], depth=1, rel_path="secret.log")
    assert match3 is False
    assert "exclude pattern" in reason3


def test_filter_size(tmp_path):
    """Test min_size and max_size filtering."""
    small_file = tmp_path / "small.dat"
    small_file.write_bytes(b"A" * 100)

    large_file = tmp_path / "large.dat"
    large_file.write_bytes(b"B" * 5000)

    with os.scandir(str(tmp_path)) as it:
        entries = {e.name: e for e in it}

    filt_min = DeletionFilter(min_size=1000)
    assert filt_min.matches_file(entries["small.dat"], depth=1, rel_path="small.dat")[0] is False
    assert filt_min.matches_file(entries["large.dat"], depth=1, rel_path="large.dat")[0] is True

    filt_max = DeletionFilter(max_size=1000)
    assert filt_max.matches_file(entries["small.dat"], depth=1, rel_path="small.dat")[0] is True
    assert filt_max.matches_file(entries["large.dat"], depth=1, rel_path="large.dat")[0] is False


def test_filter_age(tmp_path):
    """Test older_than and newer_than filtering."""
    old_file = tmp_path / "old.txt"
    old_file.write_text("old")
    # Set mtime to 10 days ago
    ten_days_ago = time.time() - (10 * 86400)
    os.utime(str(old_file), (ten_days_ago, ten_days_ago))

    new_file = tmp_path / "new.txt"
    new_file.write_text("new")

    with os.scandir(str(tmp_path)) as it:
        entries = {e.name: e for e in it}

    # Filter older than 5 days
    filt_older = DeletionFilter(older_than=5 * 86400, reference_time=time.time())
    assert filt_older.matches_file(entries["old.txt"], depth=1, rel_path="old.txt")[0] is True
    assert filt_older.matches_file(entries["new.txt"], depth=1, rel_path="new.txt")[0] is False

    # Filter newer than 5 days
    filt_newer = DeletionFilter(newer_than=5 * 86400, reference_time=time.time())
    assert filt_newer.matches_file(entries["old.txt"], depth=1, rel_path="old.txt")[0] is False
    assert filt_newer.matches_file(entries["new.txt"], depth=1, rel_path="new.txt")[0] is True


def test_filter_depth_and_directory_traversal(tmp_path):
    """Test max_depth and directory exclusion on traversal."""
    sub_dir = tmp_path / "sub"
    sub_dir.mkdir()
    git_dir = tmp_path / ".git"
    git_dir.mkdir()

    with os.scandir(str(tmp_path)) as it:
        entries = {e.name: e for e in it}

    filt = DeletionFilter(
        exclude_patterns=[".git"],
        max_depth=2,
    )

    # Sub directory at depth 1 with max_depth 2 should be traversed
    should_sub, _ = filt.should_traverse_directory(entries["sub"], depth=1, rel_path="sub")
    assert should_sub is True

    # .git directory should NOT be traversed
    should_git, reason_git = filt.should_traverse_directory(entries[".git"], depth=1, rel_path=".git")
    assert should_git is False
    assert "exclude pattern" in reason_git

    # Exceeding max_depth
    should_deep, reason_deep = filt.should_traverse_directory(entries["sub"], depth=3, rel_path="sub/deep")
    assert should_deep is False
    assert "exceeds max-depth" in reason_deep
