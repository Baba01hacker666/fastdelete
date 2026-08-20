"""
Tests for disk space tree analyzer in fastdelete.analyzer.
"""

from pathlib import Path
import pytest

from fastdelete.analyzer import (
    analyze_directory,
    render_analyzer_report,
)


def test_analyze_directory(tmp_path):
    sub1 = tmp_path / "sub1"
    sub2 = tmp_path / "sub2"
    sub1.mkdir()
    sub2.mkdir()

    (sub1 / "large.bin").write_bytes(b"A" * 50000)
    (sub2 / "small.txt").write_bytes(b"B" * 1000)
    (tmp_path / "root_file.log").write_bytes(b"C" * 2000)

    summary = analyze_directory(tmp_path)

    assert summary.total_files == 3
    assert summary.total_dirs >= 2
    assert summary.total_bytes >= 53000
    assert len(summary.largest_files) == 3
    assert summary.largest_files[0][1] == 50000

    assert ".bin" in summary.by_extension
    assert ".txt" in summary.by_extension
    assert ".log" in summary.by_extension

    report_str = render_analyzer_report(summary)
    assert "DISK USAGE ANALYSIS" in report_str
    assert "TOP LARGEST FILES" in report_str
