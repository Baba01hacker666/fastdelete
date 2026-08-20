"""
Tests for duplicate file detection and cleanup in fastdelete.duplicates.
"""

from pathlib import Path
import pytest

from fastdelete.duplicates import (
    find_duplicates,
    clean_duplicates,
    render_duplicates_report,
)


def test_find_and_clean_duplicates(tmp_path):
    d = tmp_path / "data"
    d.mkdir()

    content1 = b"identical content 12345" * 100
    content2 = b"unique content abcdef" * 50

    f1 = d / "orig.dat"
    f2 = d / "copy1.dat"
    f3 = d / "copy2.dat"
    f4 = d / "unique.dat"

    f1.write_bytes(content1)
    f2.write_bytes(content1)
    f3.write_bytes(content1)
    f4.write_bytes(content2)

    report = find_duplicates(d)
    assert report.total_duplicate_files == 2
    assert len(report.groups) == 1
    assert len(report.groups[0].paths) == 3

    rendered = render_duplicates_report(report)
    assert "DUPLICATE FILES REPORT" in rendered

    # Clean duplicates
    stats = clean_duplicates(report, action="delete")
    assert stats.files_deleted == 2

    # Exactly 1 of the 3 identical files should remain
    remaining = [f for f in [f1, f2, f3] if f.exists()]
    assert len(remaining) == 1
    assert f4.exists()
