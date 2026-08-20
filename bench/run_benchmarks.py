#!/usr/bin/env python3
"""
Benchmark comparison suite: fastdelete vs rm -rf vs Pure C (nftw).
Tests performance and correctness on large directory trees with unusual filenames and symlinks.
"""

import os
import subprocess
import time
import shutil
import sys
from pathlib import Path

BENCH_DIR = Path(__file__).resolve().parent
GENERATOR_SRC = BENCH_DIR / "bench_generator.c"
GENERATOR_BIN = BENCH_DIR / "bench_generator"
C_DELETE_SRC = BENCH_DIR / "bench_c_delete.c"
C_DELETE_BIN = BENCH_DIR / "bench_c_delete"

TEST_ROOT = Path("/tmp/fastdelete_benchmark")
FILES_COUNT = 50000


def compile_binaries():
    print("================================================================================")
    print("==> Compiling Native C Benchmark Generator and Deleter...")
    subprocess.run(
        ["gcc", "-O3", "-pthread", str(GENERATOR_SRC), "-o", str(GENERATOR_BIN)],
        check=True,
    )
    subprocess.run(
        ["gcc", "-O3", str(C_DELETE_SRC), "-o", str(C_DELETE_BIN)],
        check=True,
    )
    print("==> Compilation successful.\n")


def generate_tree(target_path: Path, count: int):
    if target_path.exists():
        shutil.rmtree(str(target_path), ignore_errors=True)
    target_path.parent.mkdir(parents=True, exist_ok=True)
    target_path.mkdir(parents=True, exist_ok=True)
    subprocess.run([str(GENERATOR_BIN), str(target_path), str(count)], check=True)


def count_entries(path: Path) -> int:
    if not path.exists():
        return 0
    count = 0
    for root, dirs, files in os.walk(path):
        count += len(dirs) + len(files)
    return count + 1  # include root dir


def run_benchmark_trial(name: str, cmd: list, target_path: Path):
    print(f"--> [Benchmark] {name}")
    print(f"    Generating test tree with ~{FILES_COUNT:,} items...")
    generate_tree(target_path, FILES_COUNT)

    initial_items = count_entries(target_path)
    print(f"    Starting deletion on {initial_items:,} items...")

    start = time.perf_counter()
    proc = subprocess.run(
        cmd,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        text=True,
    )
    end = time.perf_counter()
    elapsed = max(0.0001, end - start)

    remaining = count_entries(target_path)
    success = proc.returncode == 0 and remaining == 0
    deleted = initial_items - remaining
    rate = deleted / elapsed

    print(f"    Completed: {deleted:,} items deleted in {elapsed:.3f}s ({rate:,.0f} items/s)")
    print(f"    Validation: Remaining items = {remaining} [Success = {success}]\n")

    return {
        "name": name,
        "items": deleted,
        "elapsed": elapsed,
        "rate": rate,
        "success": success,
        "remaining": remaining,
    }


def main():
    compile_binaries()

    methods = [
        ("Pure C (nftw baseline)", [str(C_DELETE_BIN), str(TEST_ROOT / "c_test")], TEST_ROOT / "c_test"),
        ("System rm -rf", ["rm", "-rf", str(TEST_ROOT / "rm_test")], TEST_ROOT / "rm_test"),
        ("fastdelete (1 worker)", [sys.executable, "-m", "fastdelete.cli", str(TEST_ROOT / "fd1_test"), "--yes", "-q"], TEST_ROOT / "fd1_test"),
        ("fastdelete (4 workers)", [sys.executable, "-m", "fastdelete.cli", str(TEST_ROOT / "fd4_test"), "--workers", "4", "--yes", "-q"], TEST_ROOT / "fd4_test"),
        ("fastdelete (8 workers)", [sys.executable, "-m", "fastdelete.cli", str(TEST_ROOT / "fd8_test"), "--workers", "8", "--yes", "-q"], TEST_ROOT / "fd8_test"),
    ]

    results = []

    for name, cmd, target in methods:
        res = run_benchmark_trial(name, cmd, target)
        results.append(res)

    # Clean up test root
    if TEST_ROOT.exists():
        shutil.rmtree(str(TEST_ROOT), ignore_errors=True)

    # Print summary table
    print("=" * 84)
    print(f"{'Deletion Method':<26} | {'Items Deleted':<14} | {'Time (s)':<10} | {'Rate (items/s)':<16} | {'Correctness'}")
    print("-" * 84)
    for r in results:
        status = "PASSED (0 left)" if r["success"] else f"FAILED ({r['remaining']} left)"
        print(f"{r['name']:<26} | {r['items']:>14,d} | {r['elapsed']:>10.3f} | {r['rate']:>16,.0f} | {status}")
    print("=" * 84)


if __name__ == "__main__":
    main()
