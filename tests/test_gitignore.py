"""
Tests for gitignore pattern parser and matcher in fastdelete.gitignore.
"""


from fastdelete.gitignore import (
    GitIgnoreMatcher,
    parse_gitignore_line,
)


def test_parse_gitignore_rules():
    r1 = parse_gitignore_line("*.log")
    assert r1 is not None
    assert not r1.is_negation
    assert not r1.is_dir_only

    r2 = parse_gitignore_line("!important.log")
    assert r2 is not None
    assert r2.is_negation

    r3 = parse_gitignore_line("build/")
    assert r3 is not None
    assert r3.is_dir_only

    r4 = parse_gitignore_line("# comment")
    assert r4 is None


def test_gitignore_matcher_matching(tmp_path):
    gi_file = tmp_path / ".gitignore"
    gi_file.write_text(
        "*.log\n"
        "!keep.log\n"
        "build/\n"
        "temp_*\n"
    )

    matcher = GitIgnoreMatcher.from_file(gi_file, base_path=str(tmp_path))

    assert matcher.matches("error.log", is_dir=False)
    assert not matcher.matches("keep.log", is_dir=False)
    assert matcher.matches("build", is_dir=True)
    assert matcher.matches("temp_file.txt", is_dir=False)
    assert not matcher.matches("main.py", is_dir=False)
