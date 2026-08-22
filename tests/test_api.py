"""
Tests for high-level public Python API in fastdelete.api.
"""


from fastdelete import (
    delete,
    delete_many,
    shred,
    analyze,
    duplicates,
)


def test_api_delete_file(tmp_path):
    f = tmp_path / "test.txt"
    f.write_text("hello world")
    assert f.exists()

    stats = delete(f)
    assert stats.files_deleted == 1
    assert not f.exists()


def test_api_delete_directory(tmp_path):
    d = tmp_path / "subdir"
    d.mkdir()
    (d / "a.txt").write_text("a")
    (d / "b.txt").write_text("b")

    stats = delete(d)
    assert stats.files_deleted == 2
    assert stats.directories_deleted == 1
    assert not d.exists()


def test_api_delete_dry_run(tmp_path):
    f = tmp_path / "preserve.txt"
    f.write_text("keep me")

    stats = delete(f, dry_run=True)
    assert stats.files_deleted == 1
    assert f.exists()


def test_api_delete_many(tmp_path):
    f1 = tmp_path / "f1.txt"
    f2 = tmp_path / "f2.txt"
    d1 = tmp_path / "d1"
    d1.mkdir()
    (d1 / "nested.txt").write_text("nested")

    f1.write_text("1")
    f2.write_text("2")

    stats = delete_many([f1, f2, d1])
    assert stats.files_deleted == 3
    assert stats.directories_deleted == 1
    assert not f1.exists()
    assert not f2.exists()
    assert not d1.exists()


def test_api_shred(tmp_path):
    f = tmp_path / "secret.key"
    f.write_text("supersecretkey12345")
    assert f.exists()

    stats = shred(f, passes=1, method="zero")
    assert stats.files_deleted == 1
    assert not f.exists()


def test_api_analyze(tmp_path):
    d = tmp_path / "analysis_dir"
    d.mkdir()
    (d / "big.bin").write_bytes(b"x" * 1024)
    (d / "small.txt").write_text("hello")

    summary = analyze(d)
    assert summary.total_files == 2
    assert summary.total_bytes >= 1024
    assert len(summary.largest_files) == 2


def test_api_duplicates(tmp_path):
    d = tmp_path / "dupe_dir"
    d.mkdir()
    content = b"exact duplicate payload"
    (d / "copy1.bin").write_bytes(content)
    (d / "copy2.bin").write_bytes(content)
    (d / "unique.bin").write_bytes(b"something else")

    report = duplicates(d)
    assert report.total_duplicate_files == 1
    assert len(report.groups) == 1
    assert len(report.groups[0].paths) == 2
