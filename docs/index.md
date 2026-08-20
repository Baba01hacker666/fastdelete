# 📚 FastDelete Documentation

Welcome to the comprehensive documentation for **FastDelete** — the high-performance, safety-focused filesystem toolkit for fast directory deletion, developer workspace cleaning, secure data shredding, safe trash bin management, and disk inspection.

---

## 🧭 Navigation & Guides

- **[CLI Reference](cli.md)**: Full command-line usage, subcommands (`clean`, `shred`, `trash`, `du`, `dupes`, `bench`), flags, and shell examples.
- **[Python Developer API](api.md)**: Synchronous and asyncio non-blocking programmatic API (`fastdelete.delete()`, `fastdelete.delete_async()`), classes, and serialization.
- **[Architecture & Safety](architecture.md)**: How FastDelete works internally — $O(\text{depth})$ stack traversal, native POSIX C acceleration, symlink protection, and safety blacklists.
- **[Secure Shredder Guide](shredder.md)**: Cryptographic wiping standards (DoD 5220.22-M 3-pass/7-pass, Gutmann 35-pass, pseudo-random), filename obfuscation, and hardware flushing.
- **[Workspace Cleaner Presets](presets.md)**: Built-in cleaning presets for Python, Node.js, Rust, C/C++, Java, temporary files, logs, and custom rules.
- **[Trash Bin & Recovery](trash.md)**: FreeDesktop.org Trash specification compliance, `.trashinfo` metadata format, restoration, and emptying.
- **[Benchmarks & Performance](benchmarks.md)**: Real-world filesystem performance measurements and comparison tables against `rm -rf`.
