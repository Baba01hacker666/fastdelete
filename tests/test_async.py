"""
Tests for asynchronous deletion in fastdelete.api.
Uses standard library asyncio.run to execute async coroutines independently of pytest plugins.
"""

import asyncio

from fastdelete import delete_async


def test_delete_async_file(tmp_path):
    f = tmp_path / "async_file.txt"
    f.write_text("async deletion content")
    assert f.exists()

    async def runner():
        return await delete_async(f)

    stats = asyncio.run(runner())
    assert stats.files_deleted == 1
    assert not f.exists()


def test_delete_async_directory(tmp_path):
    d = tmp_path / "async_dir"
    d.mkdir()
    for i in range(10):
        (d / f"file_{i}.txt").write_text(f"content {i}")

    async def runner():
        return await delete_async(d, workers=2)

    stats = asyncio.run(runner())
    assert stats.files_deleted == 10
    assert stats.directories_deleted == 1
    assert not d.exists()
