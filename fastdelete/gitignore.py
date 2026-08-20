"""
Parser and matcher for .gitignore and .fastdeleteignore rules.
Implements gitignore pattern specification including negation, directory-only matches, and globstars.
"""

from __future__ import annotations

import fnmatch
import os
import re
from dataclasses import dataclass
from pathlib import Path
from typing import List, Optional, Tuple, Union


@dataclass
class GitIgnoreRule:
    """Represents a single rule from an ignore file."""
    pattern: str
    is_negation: bool
    is_dir_only: bool
    is_anchored: bool
    regex: re.Pattern


def _translate_gitignore_to_regex(pattern: str, is_dir_only: bool, is_anchored: bool) -> re.Pattern:
    """Translate gitignore glob pattern to a compiled regex pattern."""
    p = pattern
    # Normalize slashes
    p = p.replace("\\", "/")

    # Escape special regex chars except * and ?
    res = []
    i = 0
    n = len(p)

    if is_anchored:
        res.append("^")
    else:
        res.append("(?:^|/)")

    while i < n:
        c = p[i]
        if c == "*":
            if i + 1 < n and p[i + 1] == "*":
                # Double asterisk **
                if i + 2 < n and p[i + 2] == "/":
                    res.append("(?:.+/)?")
                    i += 3
                    continue
                else:
                    res.append(".*")
                    i += 2
                    continue
            else:
                # Single asterisk * matches anything except /
                res.append("[^/]*")
                i += 1
                continue
        elif c == "?":
            res.append("[^/]")
            i += 1
            continue
        elif c in r"\.+^$()[]{}|":
            res.append("\\" + c)
            i += 1
            continue
        else:
            res.append(c)
            i += 1

    if is_dir_only:
        res.append("(?:/.*)?$")
    else:
        res.append("(?:/.*)?$")

    pattern_str = "".join(res)
    return re.compile(pattern_str)


def parse_gitignore_line(line: str) -> Optional[GitIgnoreRule]:
    """Parse a single line from an ignore file into a GitIgnoreRule."""
    raw = line.rstrip("\r\n")
    # Trailing spaces are ignored unless escaped
    raw = raw.rstrip(" ")
    if not raw or raw.startswith("#"):
        return None

    is_negation = False
    if raw.startswith("!"):
        is_negation = True
        raw = raw[1:]

    if not raw:
        return None

    is_dir_only = False
    if raw.endswith("/"):
        is_dir_only = True
        raw = raw.rstrip("/")

    is_anchored = False
    if raw.startswith("/"):
        is_anchored = True
        raw = raw[1:]
    elif "/" in raw:
        is_anchored = True

    try:
        regex = _translate_gitignore_to_regex(raw, is_dir_only, is_anchored)
    except re.error:
        return None

    return GitIgnoreRule(
        pattern=raw,
        is_negation=is_negation,
        is_dir_only=is_dir_only,
        is_anchored=is_anchored,
        regex=regex,
    )


class GitIgnoreMatcher:
    """
    Evaluates relative paths against a collection of gitignore rules.
    """

    def __init__(self, rules: Optional[List[GitIgnoreRule]] = None, base_path: Optional[str] = None):
        self.rules = rules or []
        self.base_path = os.path.abspath(base_path) if base_path else None

    @classmethod
    def from_file(cls, ignore_path: Union[str, Path], base_path: Optional[str] = None) -> GitIgnoreMatcher:
        """Construct matcher from a .gitignore or .fastdeleteignore file."""
        p = Path(ignore_path)
        if not p.exists():
            return cls(rules=[], base_path=base_path)

        rules: List[GitIgnoreRule] = []
        try:
            content = p.read_text(encoding="utf-8", errors="replace")
            for line in content.splitlines():
                rule = parse_gitignore_line(line)
                if rule is not None:
                    rules.append(rule)
        except Exception:
            pass

        base = base_path or str(p.parent)
        return cls(rules=rules, base_path=base)

    def matches(self, path: str, is_dir: bool = False) -> bool:
        """
        Check if the given path matches the ignore rules.
        Path should be relative to base_path or an absolute path under base_path.
        """
        if not self.rules:
            return False

        if self.base_path and os.path.isabs(path):
            try:
                rel = os.path.relpath(path, self.base_path).replace("\\", "/")
            except ValueError:
                rel = path.replace("\\", "/")
        else:
            rel = path.replace("\\", "/").lstrip("/")

        matched = False
        for rule in self.rules:
            if rule.is_dir_only and not is_dir:
                continue

            if rule.regex.search(rel):
                if rule.is_negation:
                    matched = False
                else:
                    matched = True

        return matched
