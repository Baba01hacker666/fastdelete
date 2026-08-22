"""
Tests for developer workspace cleanup presets in fastdelete.presets.
"""


from fastdelete.presets import (
    get_preset,
    list_presets,
    find_preset_targets,
    run_preset_clean,
)


def test_list_presets():
    presets = list_presets()
    names = [p.name for p in presets]
    assert "python" in names
    assert "node" in names
    assert "rust" in names
    assert "c" in names
    assert "all-dev" in names


def test_get_preset_alias():
    py = get_preset("py")
    assert py.name == "python"

    js = get_preset("js")
    assert js.name == "node"


def test_find_preset_targets_python(tmp_path):
    # Setup simulated Python repo
    (tmp_path / "app.py").write_text("print('hello')")
    pycache = tmp_path / "__pycache__"
    pycache.mkdir()
    (pycache / "app.cpython-313.pyc").write_text("bytecode")

    pytest_cache = tmp_path / ".pytest_cache"
    pytest_cache.mkdir()

    dirs, files = find_preset_targets(tmp_path, get_preset("python"))
    assert str(pycache) in dirs
    assert str(pytest_cache) in dirs


def test_run_preset_clean(tmp_path):
    pycache = tmp_path / "__pycache__"
    pycache.mkdir()
    (pycache / "mod.pyc").write_text("bytecode")

    source_file = tmp_path / "main.py"
    source_file.write_text("import sys")

    run_preset_clean("python", root_path=tmp_path)
    assert not pycache.exists()
    assert source_file.exists()


def test_preset_python_cleans_coverage_data_file(tmp_path):
    """The .coverage data file is a regular file and must be cleaned by the python preset."""
    coverage_file = tmp_path / ".coverage"
    coverage_file.write_text("coverage sqlite data")
    keep_file = tmp_path / "app.py"
    keep_file.write_text("print('hi')")

    dirs, files = find_preset_targets(tmp_path, get_preset("python"))
    assert str(coverage_file) in files

    stats = run_preset_clean("python", root_path=tmp_path)
    assert not coverage_file.exists()
    assert keep_file.exists()
    assert stats.files_deleted >= 1


def test_preset_temp_cleans_ds_store_and_thumbs_db_files(tmp_path):
    """.DS_Store and Thumbs.db are files, not directories."""
    ds_store = tmp_path / ".DS_Store"
    thumbs = tmp_path / "Thumbs.db"
    ds_store.write_bytes(b"\x00\x01")
    thumbs.write_bytes(b"\x00\x02")

    _, files = find_preset_targets(tmp_path, get_preset("temp"))
    assert str(ds_store) in files
    assert str(thumbs) in files
