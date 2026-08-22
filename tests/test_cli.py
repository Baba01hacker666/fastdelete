"""
Tests for fastdelete CLI argument parsing, interactive confirmations, and execution.
"""

from unittest.mock import patch

from fastdelete.cli import build_filter, create_parser, main


def test_cli_parser_defaults():
    """Verify default parser settings."""
    parser = create_parser()
    args = parser.parse_args(["/tmp/target"])
    assert args.targets == ["/tmp/target"]
    assert args.yes is False
    assert args.dry_run is False
    assert args.force is False
    assert args.workers == 1
    assert args.verbose is False
    assert args.quiet is False
    assert args.one_file_system is False


def test_cli_parser_all_flags():
    """Verify parsing with comprehensive flags."""
    parser = create_parser()
    args = parser.parse_args([
        "/tmp/target",
        "-y",
        "-n",
        "-f",
        "-w", "8",
        "-v",
        "-x",
        "--include", "*.log",
        "--include", "*.tmp",
        "--exclude", ".git",
        "--min-size", "100M",
        "--max-size", "1G",
        "--older-than", "30d",
        "--newer-than", "1d",
        "--max-depth", "5",
        "--min-depth", "1",
        "--log", "deletion.log",
    ])
    assert args.yes is True
    assert args.dry_run is True
    assert args.force is True
    assert args.workers == 8
    assert args.verbose is True
    assert args.one_file_system is True
    assert args.includes == ["*.log", "*.tmp"]
    assert args.excludes == [".git"]
    assert args.min_size == "100M"
    assert args.max_size == "1G"
    assert args.older_than == "30d"
    assert args.newer_than == "1d"
    assert args.max_depth == 5
    assert args.min_depth == 1
    assert args.log_file == "deletion.log"

    filt = build_filter(args)
    assert filt.min_size == 100 * 1024 * 1024
    assert filt.max_size == 1024 * 1024 * 1024
    assert filt.older_than == 30 * 86400.0
    assert filt.newer_than == 1 * 86400.0
    assert filt.max_depth == 5
    assert filt.min_depth == 1


def test_cli_main_dry_run_directory(tmp_path):
    """Test running main() on a directory in dry-run mode."""
    target_dir = tmp_path / "cli_test_dir"
    target_dir.mkdir()
    (target_dir / "sample.txt").write_text("sample")

    exit_code = main([str(target_dir), "--dry-run", "--yes"])
    assert exit_code == 0
    assert target_dir.exists()
    assert (target_dir / "sample.txt").exists()


def test_cli_main_actual_deletion(tmp_path):
    """Test running main() on a directory with --yes."""
    target_dir = tmp_path / "delete_me"
    target_dir.mkdir()
    (target_dir / "file.txt").write_text("hello")

    exit_code = main([str(target_dir), "--yes"])
    assert exit_code == 0
    assert not target_dir.exists()


def test_cli_main_interactive_confirm_exact_match(tmp_path):
    """Test interactive confirmation with exact path typed."""
    target_dir = tmp_path / "confirm_dir"
    target_dir.mkdir()

    # User types exact path
    with patch("builtins.input", return_value=str(target_dir)):
        exit_code = main([str(target_dir)])
        assert exit_code == 0
        assert not target_dir.exists()


def test_cli_main_interactive_confirm_mismatch(tmp_path):
    """Test interactive confirmation aborted on mismatch."""
    target_dir = tmp_path / "mismatch_dir"
    target_dir.mkdir()

    # User types wrong string
    with patch("builtins.input", return_value="wrong_string"):
        exit_code = main([str(target_dir)])
        assert exit_code == 2
        assert target_dir.exists()


def test_cli_main_safety_refusal():
    """Test safety refusal when target is root filesystem."""
    exit_code = main(["/", "--yes"])
    assert exit_code == 2


def test_cli_main_nonexistent():
    """Test main with a non-existent path."""
    exit_code = main(["/path/does/not/exist_987654321", "--yes"])
    assert exit_code == 1
