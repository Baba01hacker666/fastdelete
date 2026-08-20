"""
Tests for safe trash operations in fastdelete.trash.
"""

import os
from pathlib import Path
import pytest

from fastdelete.trash import (
    get_trash_dir,
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
