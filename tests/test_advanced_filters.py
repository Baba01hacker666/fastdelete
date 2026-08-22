"""
Tests for advanced regex, file type, empty files, and gitignore filtering.
"""


from fastdelete.filters import DeletionFilter
from fastdelete.deleter import FastDeleter


def test_filter_regex(tmp_path):
    (tmp_path / "img_001.jpg").write_text("1")
    (tmp_path / "img_002.png").write_text("2")
    (tmp_path / "doc_001.txt").write_text("3")

    # Only delete files matching regex r"img_\d+\.jpg"
    filt = DeletionFilter(include_regex=[r"img_\d+\.jpg"])
    deleter = FastDeleter(str(tmp_path), deletion_filter=filt, delete_root_dir=False)
    deleter.run()

    assert not (tmp_path / "img_001.jpg").exists()
    assert (tmp_path / "img_002.png").exists()
    assert (tmp_path / "doc_001.txt").exists()


def test_filter_empty_files_only(tmp_path):
    f_empty = tmp_path / "empty.txt"
    f_empty.touch()

    f_nonempty = tmp_path / "full.txt"
    f_nonempty.write_text("non-empty")

    filt = DeletionFilter(empty_files_only=True)
    deleter = FastDeleter(str(tmp_path), deletion_filter=filt, delete_root_dir=False)
    deleter.run()

    assert not f_empty.exists()
    assert f_nonempty.exists()


def test_filter_file_types(tmp_path):
    f = tmp_path / "file.txt"
    f.write_text("file")

    d = tmp_path / "subdir"
    d.mkdir()

    # Only delete files ('f'), not dirs
    filt = DeletionFilter(file_types={"f"})
    deleter = FastDeleter(str(tmp_path), deletion_filter=filt, delete_root_dir=False)
    deleter.run()

    assert not f.exists()
    assert d.exists()
