"""
High-performance iterative directory scanner using os.scandir().
"""

from __future__ import annotations

import os
import stat
from dataclasses import dataclass
from typing import Generator, List, Optional

from fastdelete.filters import DeletionFilter


@dataclass
class ScanItem:
    """Action item produced by the directory scanner."""
    action: str  # 'FILE', 'DIR_POST', 'DIR_SKIP', 'FILE_SKIP', 'SCAN_ERROR'
    path: str
    name: str
    depth: int
    rel_path: str
    is_symlink: bool = False
    is_dir: bool = False
    is_file: bool = False
    size: int = 0
    error: Optional[Exception] = None
    reason: Optional[str] = None
    dir_entry: Optional[os.DirEntry] = None


# Backward-compatibility alias
ScanAction = ScanItem


class DirectoryScanner:
    """
    Iterative, memory-efficient post-order directory scanner.
    Never loads full trees into memory and never exceeds Python recursion limits.
    """

    def __init__(
        self,
        root_path: str,
        deletion_filter: Optional[DeletionFilter] = None,
        delete_root_dir: bool = True,
    ):
        self.root_path = os.path.abspath(root_path)
        self.filter = deletion_filter or DeletionFilter()
        self.delete_root_dir = delete_root_dir
        self._open_iterators: List[os.ScandirIterator] = []

    def close(self) -> None:
        """Close any remaining open scandir iterators."""
        while self._open_iterators:
            it = self._open_iterators.pop()
            try:
                it.close()
            except Exception:
                pass

    def scan(self) -> Generator[ScanItem, None, None]:
        """
        Stream items for deletion in post-order (children before directory).
        Yields ScanItem instances.
        """
        try:
            # Check root target stat without following symlinks
            try:
                root_stat = os.lstat(self.root_path)
            except FileNotFoundError:
                yield ScanItem(
                    action="SCAN_ERROR",
                    path=self.root_path,
                    name=os.path.basename(self.root_path),
                    depth=0,
                    rel_path="",
                    error=FileNotFoundError(f"Target does not exist: {self.root_path}"),
                )
                return
            except PermissionError as e:
                yield ScanItem(
                    action="SCAN_ERROR",
                    path=self.root_path,
                    name=os.path.basename(self.root_path),
                    depth=0,
                    rel_path="",
                    error=e,
                )
                return
            except OSError as e:
                yield ScanItem(
                    action="SCAN_ERROR",
                    path=self.root_path,
                    name=os.path.basename(self.root_path),
                    depth=0,
                    rel_path="",
                    error=e,
                )
                return

            # Set base device for filesystem boundary protection
            if self.filter.one_file_system and self.filter.base_dev is None:
                self.filter.base_dev = root_stat.st_dev

            # Handle case where root is a symlink or regular file or special file
            is_root_symlink = stat.S_ISLNK(root_stat.st_mode)
            is_root_dir = stat.S_ISDIR(root_stat.st_mode) and not is_root_symlink

            if not is_root_dir:
                # Single item target (file, symlink, device, socket, fifo)
                yield ScanItem(
                    action="FILE",
                    path=self.root_path,
                    name=os.path.basename(self.root_path),
                    depth=0,
                    rel_path=os.path.basename(self.root_path),
                    is_symlink=is_root_symlink,
                    is_dir=False,
                    is_file=not is_root_symlink,
                    size=root_stat.st_size if not is_root_symlink else 0,
                )
                return

            # Stack entries: (dir_path, depth, rel_path, iterator)
            try:
                root_it = os.scandir(self.root_path)
                self._open_iterators.append(root_it)
            except (PermissionError, OSError) as e:
                yield ScanItem(
                    action="SCAN_ERROR",
                    path=self.root_path,
                    name=os.path.basename(self.root_path),
                    depth=0,
                    rel_path="",
                    error=e,
                )
                return

            stack = [(self.root_path, 0, "", root_it)]

            while stack:
                curr_dir, curr_depth, curr_rel, curr_it = stack[-1]

                try:
                    entry = next(curr_it)
                except StopIteration:
                    try:
                        curr_it.close()
                    except Exception:
                        pass
                    if self._open_iterators and self._open_iterators[-1] is curr_it:
                        self._open_iterators.pop()
                    stack.pop()

                    # Post-order: contents are processed, now emit directory for removal
                    if curr_depth == 0:
                        if self.delete_root_dir:
                            can_remove, reason = self.filter.matches_dir_removal(
                                depth=0,
                                rel_path="",
                                dir_name=os.path.basename(curr_dir),
                            )
                            if can_remove:
                                yield ScanItem(
                                    action="DIR_POST",
                                    path=curr_dir,
                                    name=os.path.basename(curr_dir),
                                    depth=0,
                                    rel_path="",
                                    is_dir=True,
                                )
                            else:
                                yield ScanItem(
                                    action="DIR_SKIP",
                                    path=curr_dir,
                                    name=os.path.basename(curr_dir),
                                    depth=0,
                                    rel_path="",
                                    reason=reason,
                                    is_dir=True,
                                )
                    else:
                        can_remove, reason = self.filter.matches_dir_removal(
                            depth=curr_depth,
                            rel_path=curr_rel,
                            dir_name=os.path.basename(curr_dir),
                        )
                        if can_remove:
                            yield ScanItem(
                                action="DIR_POST",
                                path=curr_dir,
                                name=os.path.basename(curr_dir),
                                depth=curr_depth,
                                rel_path=curr_rel,
                                is_dir=True,
                            )
                        else:
                            yield ScanItem(
                                action="DIR_SKIP",
                                path=curr_dir,
                                name=os.path.basename(curr_dir),
                                depth=curr_depth,
                                rel_path=curr_rel,
                                reason=reason,
                                is_dir=True,
                            )
                    continue
                except (PermissionError, OSError) as e:
                    try:
                        curr_it.close()
                    except Exception:
                        pass
                    if self._open_iterators and self._open_iterators[-1] is curr_it:
                        self._open_iterators.pop()
                    stack.pop()
                    yield ScanItem(
                        action="SCAN_ERROR",
                        path=curr_dir,
                        name=os.path.basename(curr_dir),
                        depth=curr_depth,
                        rel_path=curr_rel,
                        error=e,
                    )
                    continue

                # Process current directory entry
                child_rel = f"{curr_rel}/{entry.name}" if curr_rel else entry.name
                child_depth = curr_depth + 1

                try:
                    is_sym = entry.is_symlink()
                except OSError:
                    # If is_symlink fails (e.g. entry vanished), treat safely
                    is_sym = False

                if is_sym:
                    # NEVER recursively traverse directory symlinks!
                    # Treat symlink as a file entry to be unlinked.
                    matches, reason = self.filter.matches_file(
                        entry=entry,
                        depth=child_depth,
                        rel_path=child_rel,
                    )
                    if matches:
                        yield ScanItem(
                            action="FILE",
                            path=entry.path,
                            name=entry.name,
                            depth=child_depth,
                            rel_path=child_rel,
                            is_symlink=True,
                            is_dir=False,
                            is_file=False,
                            dir_entry=entry,
                        )
                    else:
                        yield ScanItem(
                            action="FILE_SKIP",
                            path=entry.path,
                            name=entry.name,
                            depth=child_depth,
                            rel_path=child_rel,
                            is_symlink=True,
                            reason=reason,
                            dir_entry=entry,
                        )
                    continue

                # Check if it's a real directory
                try:
                    is_dir = entry.is_dir(follow_symlinks=False)
                except OSError:
                    is_dir = False

                if is_dir:
                    should_traverse, reason = self.filter.should_traverse_directory(
                        entry=entry,
                        depth=child_depth,
                        rel_path=child_rel,
                    )
                    if not should_traverse:
                        yield ScanItem(
                            action="DIR_SKIP",
                            path=entry.path,
                            name=entry.name,
                            depth=child_depth,
                            rel_path=child_rel,
                            is_dir=True,
                            reason=reason,
                            dir_entry=entry,
                        )
                        continue

                    try:
                        sub_it = os.scandir(entry.path)
                        self._open_iterators.append(sub_it)
                        stack.append((entry.path, child_depth, child_rel, sub_it))
                    except (PermissionError, OSError) as e:
                        yield ScanItem(
                            action="SCAN_ERROR",
                            path=entry.path,
                            name=entry.name,
                            depth=child_depth,
                            rel_path=child_rel,
                            error=e,
                            is_dir=True,
                        )
                    continue

                # Regular file, socket, fifo, device node
                matches, reason = self.filter.matches_file(
                    entry=entry,
                    depth=child_depth,
                    rel_path=child_rel,
                )
                if matches:
                    size = 0
                    try:
                        size = entry.stat(follow_symlinks=False).st_size
                    except (OSError, PermissionError):
                        pass

                    yield ScanItem(
                        action="FILE",
                        path=entry.path,
                        name=entry.name,
                        depth=child_depth,
                        rel_path=child_rel,
                        is_symlink=False,
                        is_dir=False,
                        is_file=True,
                        size=size,
                        dir_entry=entry,
                    )
                else:
                    yield ScanItem(
                        action="FILE_SKIP",
                        path=entry.path,
                        name=entry.name,
                        depth=child_depth,
                        rel_path=child_rel,
                        is_symlink=False,
                        reason=reason,
                        dir_entry=entry,
                    )
        finally:
            self.close()
