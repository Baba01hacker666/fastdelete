# 🐍 FastDelete Python API Reference

The `fastdelete` library provides a high-level synchronous and asynchronous Python API for direct integration into web applications, data pipelines, task queues, and CLI utilities.

---

## ⚡ Quick Start

```python
import fastdelete

# Simple deletion
stats = fastdelete.delete("/path/to/folder", workers=4)
print(f"Deleted {stats.total_deleted():,} items in {stats.elapsed_seconds():.2f}s")
```

---

## 📖 API Functions

### `fastdelete.delete(target, ...)`
Synchronously delete a file or directory tree.

```python
def delete(
    target: Union[str, Path],
    *,
    dry_run: bool = False,
    force: bool = False,
    workers: int = 1,
    filter: Optional[DeletionFilter] = None,
    shred: bool = False,
    shred_method: Union[ShredMethod, str] = ShredMethod.DOD,
    shred_passes: Optional[int] = None,
    trash: bool = False,
    allow_root: bool = False,
    allow_home: bool = False,
    quiet: bool = True,
    verbose: bool = False,
    delete_root_dir: bool = True,
    log_file: Optional[str] = None,
    callback: Optional[Callable[[Dict[str, Any]], None]] = None,
) -> DeletionStats
```

**Parameters:**
- `target`: Path to file or directory.
- `dry_run`: If `True`, simulates deletion and calculates metrics without modifying disk contents.
- `force`: If `True`, fixes permissions on read-only files before unlinking.
- `workers`: Worker threads for parallel deletion (default: `1`).
- `filter`: Optional `DeletionFilter` instance.
- `shred`: If `True`, performs multi-pass data sanitization before unlinking.
- `trash`: If `True`, moves items to the OS/FreeDesktop Trash directory.
- `callback`: Real-time event listener receiving dictionary payloads for every event.

**Returns:**
- `DeletionStats` instance.

---

### `fastdelete.delete_async(target, ...)`
Asynchronously delete a target in a worker thread. Non-blocking for `asyncio` event loops (FastAPI, aiohttp, Celery, Tornado).

```python
import asyncio
import fastdelete

async def cleanup():
    stats = await fastdelete.delete_async("/tmp/scratch_dir", workers=4)
    print(stats.to_dict())

asyncio.run(cleanup())
```

---

### `fastdelete.delete_many(targets, ...)`
Delete multiple paths in sequence, returning combined cumulative statistics:

```python
stats = fastdelete.delete_many(["/tmp/cache1", "/tmp/cache2", "/tmp/old.log"])
```

---

### `fastdelete.shred(target, passes=3, method="dod", ...)`
Convenience wrapper to sanitize and shred sensitive files:

```python
fastdelete.shred("/path/to/passwords.txt", method="dod", passes=3)
```

---

### `fastdelete.trash(target)` & `fastdelete.restore(trash_id)`
Move items to Trash and restore them:

```python
# Trash
item = fastdelete.trash("/path/to/project")
print(f"Trashed with ID: {item.id}")

# Restore
restored_path = fastdelete.restore(item.id)
print(f"Restored to {restored_path}")
```

---

### `fastdelete.clean(preset_name, root_path=".", ...)`
Execute developer workspace cleaning presets:

```python
stats = fastdelete.clean("python", root_path=".")
```

---

### `fastdelete.analyze(target, top_n=10, max_depth=None)`
Calculate recursive disk space metrics and top disk hogs:

```python
summary = fastdelete.analyze("/var/log", top_n=5)
print(f"Total: {summary.total_bytes:,} bytes")
for path, size in summary.largest_files:
    print(f"  {path} -> {size:,} bytes")
```

---

### `fastdelete.duplicates(target, min_size=1)`
Detect duplicate files using 3-stage progressive hashing:

```python
report = fastdelete.duplicates("/data", min_size=1024 * 1024)
print(f"Found {report.total_duplicate_files:,} redundant copies.")
```

---

## 📊 `DeletionStats` Class

The `DeletionStats` object provides metrics and JSON serialization:

```python
stats = fastdelete.delete("/tmp/dataset")

# Numerical properties
print(stats.files_discovered)
print(stats.files_deleted)
print(stats.directories_deleted)
print(stats.bytes_deleted)
print(stats.failed)
print(stats.skipped)
print(stats.elapsed_seconds())
print(stats.rate_items_per_second())

# Dictionary and JSON export
data = stats.to_dict()
json_str = stats.to_json(indent=2)
```
