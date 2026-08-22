"""
Tests for CLI subcommands and JSON outputs.
"""

import json

from fastdelete.cli import main


def test_cli_clean_subcommand_list(capsys):
    exit_code = main(["clean", "--list"])
    assert exit_code == 0
    captured = capsys.readouterr().out
    assert "python" in captured
    assert "node" in captured


def test_cli_clean_subcommand_execution(tmp_path, capsys):
    pycache = tmp_path / "__pycache__"
    pycache.mkdir()
    (pycache / "file.pyc").write_text("bin")

    exit_code = main(["clean", "python", str(tmp_path), "--json"])
    assert exit_code == 0
    assert not pycache.exists()


def test_cli_du_subcommand(tmp_path, capsys):
    (tmp_path / "sample.txt").write_text("analysis test")
    exit_code = main(["du", str(tmp_path), "--json"])
    assert exit_code == 0
    out = capsys.readouterr().out
    data = json.loads(out)
    assert data["total_files"] == 1


def test_cli_du_missing_path(tmp_path, capsys):
    exit_code = main(["du", str(tmp_path / "does_not_exist")])
    assert exit_code == 1
    assert "does not exist" in capsys.readouterr().err


def test_cli_dupes_missing_path(tmp_path, capsys):
    exit_code = main(["dupes", str(tmp_path / "does_not_exist")])
    assert exit_code == 1
    assert "does not exist" in capsys.readouterr().err


def test_cli_dupes_subcommand(tmp_path, capsys):
    (tmp_path / "a.txt").write_text("duplicate text")
    (tmp_path / "b.txt").write_text("duplicate text")

    exit_code = main(["dupes", str(tmp_path), "--json"])
    assert exit_code == 0
    out = capsys.readouterr().out
    data = json.loads(out)
    assert data["total_duplicate_files"] == 1


def test_cli_trash_subcommand(tmp_path, monkeypatch, capsys):
    custom_trash = tmp_path / "custom_trash"
    monkeypatch.setenv("FASTDELETE_TRASH_DIR", str(custom_trash))
    monkeypatch.setenv("XDG_DATA_HOME", str(custom_trash))

    f = tmp_path / "target.txt"
    f.write_text("trash me")

    exit_code = main(["trash", str(f)])
    assert exit_code == 0
    assert not f.exists()


def test_cli_json_output(tmp_path, capsys):
    f = tmp_path / "data.json"
    f.write_text("{}")

    exit_code = main([str(f), "--yes", "--json"])
    assert exit_code == 0
    out = capsys.readouterr().out
    data = json.loads(out)
    assert data["files_deleted"] == 1
    assert not f.exists()
