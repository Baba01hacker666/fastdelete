# 🧹 Workspace Cleaner Presets Guide

`fastdelete clean` provides built-in cleaning profiles tailored for modern development stacks to reclaim gigabytes of disk space wasted on build outputs and caches.

---

## 📋 Available Presets

### 1. `python` (Aliases: `py`)
Cleans compiled bytecode, test caches, coverage data, and package builds:
- **Folders**: `__pycache__`, `.pytest_cache`, `.mypy_cache`, `.ruff_cache`, `.tox`, `.nox`, `.coverage`, `htmlcov`, `.hypothesis`, `dist`, `build`, `*.egg-info`, `*.dist-info`
- **Files**: `*.pyc`, `*.pyo`, `*.pyd`, `.coverage.*`, `coverage.xml`

### 2. `node` (Aliases: `js`, `javascript`, `npm`)
Cleans Node.js dependencies, framework caches, build artifacts, and debug logs:
- **Folders**: `node_modules`, `.next`, `.nuxt`, `.turbo`, `.svelte-kit`, `.parcel-cache`, `.docusaurus`, `.astro`, `.cache`, `dist`, `build`, `.yarn/cache`
- **Files**: `npm-debug.log*`, `yarn-debug.log*`, `yarn-error.log*`, `pnpm-debug.log*`, `lerna-debug.log*`, `*.tsbuildinfo`

### 3. `rust` (Aliases: `cargo`)
Cleans Cargo target directories and build artifacts:
- **Folders**: `target`
- **Files**: `*.rlib`, `*.rmeta`

### 4. `c` (Aliases: `cpp`, `cxx`)
Cleans C and C++ compiled object files, shared libraries, and CMake builds:
- **Folders**: `build`, `cmake-build-debug`, `cmake-build-release`, `.cmake`, `CMakeFiles`
- **Files**: `*.o`, `*.obj`, `*.so`, `*.dylib`, `*.dll`, `*.a`, `*.lib`, `*.exe`, `CMakeCache.txt`

### 5. `java` (Aliases: `jvm`, `gradle`, `maven`)
Cleans JVM build directories, class files, and Gradle/Maven caches:
- **Folders**: `.gradle`, `build`, `target`, `out`, `.m2/repository`
- **Files**: `*.class`, `*.jar`, `*.war`, `*.ear`

### 6. `temp` (Aliases: `tmp`, `junk`)
Cleans operating system temp files, swap files, and editor backups:
- **Folders**: `.DS_Store`, `Thumbs.db`, `.tmp`
- **Files**: `*.tmp`, `*.temp`, `*.bak`, `*~`, `.DS_Store`, `Thumbs.db`, `core`, `*.swp`, `*.swo`

### 7. `logs` (Aliases: `log`)
Cleans application logs and crash dumps:
- **Files**: `*.log`, `*.log.*`, `*.log.gz`, `crash.dump`, `*.stackdump`

### 8. `all-dev`
Composite preset combining all developer presets into a single operation.

---

## 💻 CLI Usage

```bash
# Clean Python project
fastdelete clean python

# Clean Node.js repository in a specific directory
fastdelete clean node /path/to/web-app

# Dry-run preview
fastdelete clean all-dev --dry-run

# Output results as JSON
fastdelete clean rust --json
```
