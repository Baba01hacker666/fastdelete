"""
Safe trash bin and recycle bin operations compliant with FreeDesktop.org Trash Specification.
Allows moving files/folders to Trash, listing items, restoring items, and emptying Trash.
"""

from __future__ import annotations

import os
import shutil
import sys
import time
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import List, Optional, Union
from urllib.parse import quote, unquote

from fastdelete.errors import FastDeleteError, InvalidTargetError
from fastdelete.safety import normalize_long_path


@dataclass
class TrashItem:
    """Represents an item stored in the Trash directory."""
    id: str
    original_path: str
    trash_path: str
    info_path: str
    deletion_date: datetime
    is_dir: bool
    size: int


def get_trash_dir() -> Path:
    """Get the active Trash directory for the current user and platform."""
    if sys.platform == "darwin":
        trash = Path.home() / ".Trash"
    else:
        xdg_data = os.environ.get("XDG_DATA_HOME")
        if xdg_data:
            trash = Path(xdg_data) / "Trash"
        else:
            trash = Path.home() / ".local" / "share" / "Trash"

    trash.mkdir(parents=True, exist_ok=True)
    (trash / "files").mkdir(parents=True, exist_ok=True)
    (trash / "info").mkdir(parents=True, exist_ok=True)
    return trash


def _get_unique_trash_name(files_dir: Path, info_dir: Path, base_name: str) -> str:
    """Generate a collision-free filename in the trash directory."""
    candidate = base_name
    counter = 1
    stem, ext = os.path.splitext(base_name)
    while (files_dir / candidate).exists() or (info_dir / f"{candidate}.trashinfo").exists():
        candidate = f"{stem}.{counter}{ext}"
        counter += 1
    return candidate


def _calculate_size(path: Path) -> int:
    """Calculate size in bytes for a file or directory."""
    try:
        if path.is_symlink() or not path.is_dir():
            return path.lstat().st_size
        total = 0
        for entry in path.rglob("*"):
            try:
                total += entry.lstat().st_size
            except OSError:
                pass
        return total
    except OSError:
        return 0


def move_to_trash(target_path: Union[str, Path]) -> TrashItem:
    """
    Move a file or directory to the Trash bin with .trashinfo metadata.
    Returns the created TrashItem.
    """
    target = Path(target_path).resolve()
    if not target.exists() and not target.is_symlink():
        raise InvalidTargetError(f"Target does not exist: {target}")

    trash_root = get_trash_dir()
    files_dir = trash_root / "files"
    info_dir = trash_root / "info"

    trash_name = _get_unique_trash_name(files_dir, info_dir, target.name)
    dest_path = files_dir / trash_name
    info_path = info_dir / f"{trash_name}.trashinfo"

    is_dir = target.is_dir() and not target.is_symlink()
    item_size = _calculate_size(target)
    now = datetime.now(timezone.utc)
    date_str = now.strftime("%Y-%m-%dT%H:%M:%S")

    # Write .trashinfo file
    # Format according to FreeDesktop Trash Specification
    # Path is URL-encoded or absolute path
    info_content = (
        "[Trash Info]\n"
        f"Path={target}\n"
        f"DeletionDate={date_str}\n"
    )
    info_path.write_text(info_content, encoding="utf-8")

    # Move target to files/
    try:
        shutil.move(str(target), str(dest_path))
    except Exception as e:
        # Clean up info file if move failed
        if info_path.exists():
            info_path.unlink()
        raise FastDeleteError(f"Failed to move '{target}' to Trash: {e}") from e

    return TrashItem(
        id=trash_name,
        original_path=str(target),
        trash_path=str(dest_path),
        info_path=str(info_path),
        deletion_date=now,
        is_dir=is_dir,
        size=item_size,
    )


def list_trash() -> List[TrashItem]:
    """List all items currently in the Trash directory."""
    trash_root = get_trash_dir()
    info_dir = trash_root / "info"
    files_dir = trash_root / "files"

    items: List[TrashItem] = []
    if not info_dir.exists():
        return items

    for info_file in info_dir.glob("*.trashinfo"):
        try:
            content = info_file.read_text(encoding="utf-8", errors="replace")
            orig_path = ""
            date_obj = datetime.now(timezone.utc)

            for line in content.splitlines():
                line = line.strip()
                if line.startswith("Path="):
                    orig_path = line[5:].strip()
                elif line.startswith("DeletionDate="):
                    d_str = line[13:].strip()
                    try:
                        date_obj = datetime.fromisoformat(d_str)
                    except Exception:
                        pass

            trash_name = info_file.stem  # remove .trashinfo
            trash_path = files_dir / trash_name

            if trash_path.exists() or trash_path.is_symlink():
                is_dir = trash_path.is_dir() and not trash_path.is_symlink()
                size = _calculate_size(trash_path)
                items.append(
                    TrashItem(
                        id=trash_name,
                        original_path=orig_path or str(trash_path),
                        trash_path=str(trash_path),
                        info_path=str(info_file),
                        deletion_date=date_obj,
                        is_dir=is_dir,
                        size=size,
                    )
                )
        except Exception:
            continue

    items.sort(key=lambda x: x.deletion_date, reverse=True)
    return items


def restore_trash_item(item_id_or_name: str, destination: Optional[Union[str, Path]] = None) -> str:
    """
    Restore an item from the Trash back to its original location or a custom destination.
    Returns the restored path.
    """
    trash_root = get_trash_dir()
    files_dir = trash_root / "files"
    info_dir = trash_root / "info"

    # Match by exact ID or filename
    cand_id = item_id_or_name
    info_file = info_dir / f"{cand_id}.trashinfo"
    if not info_file.exists():
        # Try matching by original basename in all trash items
        matched = [it for it in list_trash() if it.id == item_id_or_name or Path(it.original_path).name == item_id_or_name]
        if not matched:
            raise InvalidTargetError(f"Trash item '{item_id_or_name}' not found in Trash.")
        item = matched[0]
        cand_id = item.id
        info_file = Path(item.info_path)

    trash_file = files_dir / cand_id
    if not trash_file.exists() and not trash_file.is_symlink():
        raise InvalidTargetError(f"Trash payload file '{trash_file}' is missing.")

    # Read original path
    orig_path = ""
    try:
        content = info_file.read_text(encoding="utf-8")
        for line in content.splitlines():
            if line.startswith("Path="):
                orig_path = line[5:].strip()
                break
    except Exception:
        pass

    target_dest = Path(destination) if destination else Path(orig_path)
    if not target_dest:
        raise FastDeleteError("Could not determine restoration path.")

    # Create parent directory if needed
    target_dest.parent.mkdir(parents=True, exist_ok=True)

    if target_dest.exists():
        raise FileExistsError(f"Restore target already exists: {target_dest}")

    shutil.move(str(trash_file), str(target_dest))
    if info_file.exists():
        info_file.unlink()

    return str(target_dest)


def empty_trash() -> int:
    """
    Permanently delete all items from the Trash bin using fastdelete.
    Returns the number of items deleted.
    """
    from fastdelete.deleter import FastDeleter

    trash_root = get_trash_dir()
    files_dir = trash_root / "files"
    info_dir = trash_root / "info"

    count = 0
    for folder in [files_dir, info_dir]:
        if folder.exists():
            deleter = FastDeleter(str(folder), delete_root_dir=False)
            stats = deleter.run()
            count += stats.total_deleted()

    return count
