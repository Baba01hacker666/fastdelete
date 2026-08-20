# ⚡ Performance Benchmarks & Methodology

FastDelete was tested against standard `rm -rf` and baseline C engines across large directory trees containing over **50,000+ files**, deep nesting levels, symlinks, and unusual filenames (Unicode, emojis, spaces, tabs, dashes, quotes).

---

## 📊 Benchmark Results (50,000+ Items Dataset)

| Engine / Method | Items Processed | Time (s) | Throughput | Correctness |
|---|---|---|---|---|
| **System `rm -rf`** | 53,201 | 82.24s | ~647 items/s | PASSED (0 remaining) |
| **FastDelete (Native C Engine)** | 53,201 | 115.96s | ~459 items/s | PASSED (0 remaining) |
| **FastDelete (Python 4 Workers)** | 53,201 | 88.97s | ~598 items/s | PASSED (0 remaining) |

*Note: Benchmarked on flash-based storage under continuous POSIX syscall load.*

---

## 🔬 Benchmark Methodology

The benchmark suite (`bench/test_speed.py` and `bench/bench_generator.c`) performs the following steps:
1. **Dataset Generation**: Compiles a native multithreaded C generator that creates thousands of files, subdirectories, valid symlinks, broken symlinks, and edge-case Unicode names.
2. **Pre-Run Item Count**: Recursively counts all entries to establish an accurate baseline.
3. **Execution & Timing**: Runs each deletion method under high-precision `time.perf_counter()`.
4. **Post-Run Validation**: Confirms 0 remaining entries and checks return codes.
5. **Rate Calculation**: Measures effective items deleted per second.

---

## 🏃 Running Benchmarks Locally

You can run the benchmark suite directly with:

```bash
fastdelete bench
```
or:
```bash
python3 bench/test_speed.py
```
