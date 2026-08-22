"""
Tests for safe trash operations in fastdelete.trash.
"""

from pathlib import Path
import pytest

from fastdelete.trash import (
    move_to_trash,
    list_trash,
    restore_trash_item,
    empty_trash,
)


@pytest.fixture(autouse=True)
def isolated_trash_dir(tmp_path, monkeypatch):
    """Ensure every test gets an isolated custom trash directory on all OS platforms."""
    custom_trash = tmp_path / "custom_trash"
    monkeypatch.setenv("FASTDELETE_TRASH_DIR", str(custom_trash))
    monkeypatch.setenv("XDG_DATA_HOME", str(custom_trash))
    return custom_trash


def test_move_to_trash_and_list(tmp_path):
    f = tmp_path / "document.pdf"
    f.write_text("important document")

    item = move_to_trash(f)
    assert not f.exists()
    assert item.original_path == str(f)
    assert Path(item.trash_path).exists()
    assert Path(item.info_path).exists()

    items = list_trash()
    assert len(items) >= 1
    assert any(it.id == item.id for it in items)


def test_restore_trash_item(tmp_path):
    f = tmp_path / "restore_me.txt"
    f.write_text("content to restore")

    item = move_to_trash(f)
    assert not f.exists()

    restored_path = restore_trash_item(item.id)
    assert restored_path == str(f)
    assert f.exists()
    assert f.read_text() == "content to restore"


def test_empty_trash(tmp_path):
    f1 = tmp_path / "t1.txt"
    f2 = tmp_path / "t2.txt"
    f1.write_text("1")
    f2.write_text("2")

    move_to_trash(f1)
    move_to_trash(f2)
    assert len(list_trash()) == 2

    empty_trash()
    assert len(list_trash()) == 0


def test_trash_symlink_moves_link_not_target(tmp_path):
    """Trashing a symlink must move the link itself, never its target file."""
    real_file = tmp_path / "real_target.txt"
    real_file.write_text("precious data")
    link = tmp_path / "link.txt"
    link.symlink_to(real_file)

    item = move_to_trash(link)

    # The link is gone from its original spot...
    assert not link.exists()
    # ...but the actual target MUST remain untouched at its original path.
    assert real_file.exists()
    assert real_file.read_text() == "precious data"
    # The trashed payload IS the symlink, not the target.
    assert Path(item.trash_path).is_symlink()


def test_restore_with_missing_original_path_requires_destination(tmp_path):
    """Restore of an item with no recorded Path= must fail instead of restoring to cwd."""
    f = tmp_path / "no_orig.txt"
    f.write_text("data")
    item = move_to_trash(f)

    # Corrupt the info file by removing the Path entry
    info = Path(item.info_path)
    lines = [l for l in info.read_text().splitlines() if not l.startswith("Path=")]
    info.write_text("\n".join(lines) + "\n")

    import pytest
    from fastdelete.errors import FastDeleteError

    with pytest.raises(FastDeleteError):
        restore_trash_item(item.id)
