# 🗑️ Safe Trash Bin & Recovery Guide

FastDelete provides cross-platform safe deletion compliant with the [FreeDesktop.org Trash Specification](https://specifications.freedesktop.org/trash-spec/trashspec-latest.html).

---

## 🧭 How FastDelete Trash Works

Instead of permanently unlinking files, `fastdelete trash` moves the target into the user's desktop Trash directory and creates a corresponding `.trashinfo` metadata file.

### Directory Structure:
```
~/.local/share/Trash/ (or custom $FASTDELETE_TRASH_DIR)
├── files/
│   ├── document.pdf
│   └── project_backup/
└── info/
    ├── document.pdf.trashinfo
    └── project_backup.trashinfo
```

### `.trashinfo` Metadata Format:
```ini
[Trash Info]
Path=/home/user/documents/document.pdf
DeletionDate=2026-08-20T14:30:00
```

---

## 🛠️ CLI Operations

### Move to Trash
```bash
fastdelete trash /path/to/my_folder
```

### List Trash Contents
```bash
fastdelete trash --list
```
Output:
```
Trash Contents (2 items):
  • [my_folder] /path/to/my_folder (2026-08-20 14:30:00)
  • [data.csv] /home/user/data.csv (2026-08-20 14:25:10)
```

### Restore Items from Trash
```bash
# Restore to original path
fastdelete restore my_folder

# Restore to a new destination
fastdelete restore my_folder --dest /tmp/restored_folder
```

### Empty Trash Permanently
Uses FastDelete's high-speed engine to purge the entire Trash directory:
```bash
fastdelete trash --empty
```
