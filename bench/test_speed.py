#!/usr/bin/env python3
"""
Speed and Correctness Benchmark: fastdelete (C Accelerator & Pure Python) vs system rm -rf
Generates a huge tree of 50,000+ files with unusual characters, Unicode, emojis, symlinks, and subdirs.
"""

import os
import sys
import time
import shutil
import subprocess
from pathlib import Path

BENCH_DIR = Path(__file__).resolve().parent
GENERATOR_BIN = BENCH_DIR / "bench_generator"
TEST_DIR = Path("/tmp/fastdelete_speed_test")
NUM_FILES = 50000


def ensure_generator():
    if not GENERATOR_BIN.exists():
        print("Compiling C test tree generator...")
        subprocess.run(
            ["gcc", "-O3", "-pthread", str(BENCH_DIR / "bench_generator.c"), "-o", str(GENERATOR_BIN)],
            check=True,
        )


def generate_dataset(target: Path):
    if target.exists():
        shutil.rmtree(str(target), ignore_errors=True)
    target.parent.mkdir(parents=True, exist_ok=True)
    target.mkdir(parents=True, exist_ok=True)
    subprocess.run([str(GENERATOR_BIN), str(target), str(NUM_FILES)], check=True, stdout=subprocess.PIPE)


def count_files_fast(path: Path) -> int:
    if not path.exists():
        return 0
    total = 0
    for root, dirs, files in os.walk(path):
        total += len(dirs) + len(files)
    return total + 1


def benchmark_method(label: str, run_cmd: list, target: Path):
    print(f"\n[+] Preparing dataset for '{label}'...")
    generate_dataset(target)
    count = count_files_fast(target)
    print(f"    Dataset created: {count:,} items.")
    print(f"    Running '{label}'...")

    t0 = time.perf_counter()
    proc = subprocess.run(run_cmd, stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True)
    t1 = time.perf_counter()
    elapsed = max(0.0001, t1 - t0)

    remaining = count_files_fast(target)
    success = proc.returncode == 0 and remaining == 0
    deleted = count - remaining
    rate = deleted / elapsed

    print(f"    Finished in {elapsed:.4f}s | Rate: {rate:,.0f} files/sec | Correctness: {'PASSED' if success else 'FAILED'}")
    return {
        "label": label,
        "items": deleted,
        "elapsed": elapsed,
        "rate": rate,
        "success": success,
    }


def main():
    ensure_generator()
    print("=" * 80)
    print(f"  FASTDELETE SPEED & CORRECTNESS BENCHMARK ({NUM_FILES:,} files)")
    print("=" * 80)

    results = []

    # 1. System rm -rf
    target1 = TEST_DIR / "rm_rf"
    res1 = benchmark_method("System rm -rf", ["rm", "-rf", str(target1)], target1)
    results.append(res1)

    # 2. fastdelete (Native C Acceleration Engine)
    target2 = TEST_DIR / "fastdelete_c"
    res2 = benchmark_method(
        "fastdelete (C Engine)",
        [sys.executable, "-m", "fastdelete.cli", str(target2), "--yes", "-q"],
        target2,
    )
    results.append(res2)

    # 3. fastdelete (Pure Python Workers = 4)
    target3 = TEST_DIR / "fastdelete_py_w4"
    res3 = benchmark_method(
        "fastdelete (Python 4 workers)",
        [sys.executable, "-c", f"from fastdelete.deleter import FastDeleter; d = FastDeleter(r'{target3}', workers=4, use_c_engine=False); d.run()"],
        target3,
    )
    results.append(res3)

    # Clean up
    if TEST_DIR.exists():
        shutil.rmtree(str(TEST_DIR), ignore_errors=True)

    print("\n" + "=" * 80)
    print(f"{'Engine / Method':<32} | {'Items Deleted':<14} | {'Time (s)':<10} | {'Throughput':<16} | {'Status'}")
    print("-" * 80)
    for r in results:
        status = "PASSED (0 left)" if r["success"] else "FAILED"
        print(f"{r['label']:<32} | {r['items']:>14,d} | {r['elapsed']:>10.4f} | {r['rate']:>13,.0f} it/s | {status}")
    print("=" * 80)


if __name__ == "__main__":
    main()
