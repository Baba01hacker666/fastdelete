"""
Preset cleanup profiles for developer environments and project workspaces.
Quickly clean build artifacts, caches, and temporary files across repositories.
"""

from __future__ import annotations

import os
from dataclasses import dataclass, field
from pathlib import Path
from typing import Dict, List, Tuple, Union

from fastdelete.deleter import DeletionStats, FastDeleter
from fastdelete.errors import FastDeleteError


@dataclass
class Preset:
    """Definition of a workspace cleaning preset."""
    name: str
    description: str
    dir_names: List[str] = field(default_factory=list)
    file_patterns: List[str] = field(default_factory=list)
    dir_patterns: List[str] = field(default_factory=list)


PRESETS: Dict[str, Preset] = {
    "python": Preset(
        name="python",
        description="Python caches, compiled bytecode, test artifacts, and build directories",
        dir_names=[
            "__pycache__",
            ".pytest_cache",
            ".mypy_cache",
            ".ruff_cache",
            ".tox",
            ".nox",
            "htmlcov",
            ".hypothesis",
            "dist",
            "build",
        ],
        file_patterns=[
            "*.pyc",
            "*.pyo",
            "*.pyd",
            ".coverage",
            ".coverage.*",
            "coverage.xml",
            "*.egg-info",
        ],
        dir_patterns=[
            "*.egg-info",
            "*.dist-info",
        ],
    ),
    "node": Preset(
        name="node",
        description="Node.js dependencies, build outputs, framework caches, and log files",
        dir_names=[
            "node_modules",
            ".next",
            ".nuxt",
            ".turbo",
            ".svelte-kit",
            ".parcel-cache",
            ".docusaurus",
            ".astro",
            ".cache",
            "dist",
            "build",
            ".yarn/cache",
        ],
        file_patterns=[
            "npm-debug.log*",
            "yarn-debug.log*",
            "yarn-error.log*",
            "pnpm-debug.log*",
            "lerna-debug.log*",
            "*.tsbuildinfo",
        ],
    ),
    "rust": Preset(
        name="rust",
        description="Rust Cargo target directories and build artifacts",
        dir_names=[
            "target",
        ],
        file_patterns=[
            "*.rlib",
            "*.rmeta",
        ],
    ),
    "c": Preset(
        name="c",
        description="C and C++ compiled object files, shared libraries, and CMake builds",
        dir_names=[
            "build",
            "cmake-build-debug",
            "cmake-build-release",
            ".cmake",
            "CMakeFiles",
        ],
        file_patterns=[
            "*.o",
            "*.obj",
            "*.so",
            "*.so.*",
            "*.dylib",
            "*.dll",
            "*.a",
            "*.lib",
            "*.exe",
            "CMakeCache.txt",
        ],
    ),
    "java": Preset(
        name="java",
        description="Java and JVM build directories, Gradle/Maven caches, and class files",
        dir_names=[
            ".gradle",
            "build",
            "target",
            "out",
            ".m2/repository",
        ],
        file_patterns=[
            "*.class",
            "*.jar",
            "*.war",
            "*.ear",
        ],
    ),
    "go": Preset(
        name="go",
        description="Go binaries and cover profiles",
        file_patterns=[
            "*.test",
            "*.out",
            "cover.out",
        ],
    ),
    "temp": Preset(
        name="temp",
        description="OS temporary files, editor backups, and system junk",
        dir_names=[
            ".tmp",
        ],
        file_patterns=[
            "*.tmp",
            "*.temp",
            "*.bak",
            "*~",
            ".DS_Store",
            "Thumbs.db",
            "core",
            "core.*",
            "*.swp",
            "*.swo",
        ],
    ),
    "logs": Preset(
        name="logs",
        description="Application log files and crash reports",
        file_patterns=[
            "*.log",
            "*.log.*",
            "*.log.gz",
            "crash.dump",
            "*.stackdump",
        ],
    ),
}

# Alias mappings
PRESET_ALIASES = {
    "py": "python",
    "js": "node",
    "javascript": "node",
    "npm": "node",
    "cargo": "rust",
    "cpp": "c",
    "cxx": "c",
    "jvm": "java",
    "gradle": "java",
    "maven": "java",
    "golang": "go",
    "tmp": "temp",
    "junk": "temp",
    "log": "logs",
}


def get_preset(name: str) -> Preset:
    """Retrieve a Preset by name or alias."""
    norm_name = name.strip().lower()
    canonical = PRESET_ALIASES.get(norm_name, norm_name)
    if canonical == "all-dev":
        # Composite preset
        all_dirs = set()
        all_files = set()
        all_dir_pats = set()
        for p in PRESETS.values():
            all_dirs.update(p.dir_names)
            all_files.update(p.file_patterns)
            all_dir_pats.update(p.dir_patterns)
        return Preset(
            name="all-dev",
            description="All developer caches, build outputs, and junk files",
            dir_names=list(all_dirs),
            file_patterns=list(all_files),
            dir_patterns=list(all_dir_pats),
        )

    if canonical not in PRESETS:
        available = list(PRESETS.keys()) + ["all-dev"]
        raise FastDeleteError(
            f"Unknown preset '{name}'. Available presets: {', '.join(sorted(available))}"
        )
    return PRESETS[canonical]


def list_presets() -> List[Preset]:
    """Return all available preset definitions."""
    result = list(PRESETS.values())
    result.append(get_preset("all-dev"))
    return result


def find_preset_targets(
    root_path: Union[str, Path],
    preset: Preset,
) -> Tuple[List[str], List[str]]:
    """
    Scan root_path for directories and files matching the given preset.
    Returns (matching_dirs, matching_files).
    """
    root = Path(root_path).resolve()
    if not root.exists():
        return [], []

    matching_dirs: List[str] = []
    matching_files: List[str] = []

    dir_names_set = set(preset.dir_names)

    import fnmatch

    for dirpath, dirnames, filenames in os.walk(str(root), topdown=True):
        # Match directories
        to_remove_from_walk = []
        for d in list(dirnames):
            matched = False
            if d in dir_names_set:
                matched = True
            else:
                for pat in preset.dir_patterns:
                    if fnmatch.fnmatch(d, pat):
                        matched = True
                        break

            if matched:
                full_dir = os.path.join(dirpath, d)
                matching_dirs.append(full_dir)
                to_remove_from_walk.append(d)

        # Do not recurse into directories that will be deleted
        for d in to_remove_from_walk:
            dirnames.remove(d)

        # Match files
        for f in filenames:
            for pat in preset.file_patterns:
                if fnmatch.fnmatch(f, pat):
                    matching_files.append(os.path.join(dirpath, f))
                    break

    return matching_dirs, matching_files


def run_preset_clean(
    preset_name: str,
    root_path: Union[str, Path] = ".",
    dry_run: bool = False,
    force: bool = False,
    workers: int = 1,
    quiet: bool = False,
    verbose: bool = False,
) -> DeletionStats:
    """
    Execute cleanup for a given preset in root_path.
    Returns cumulative DeletionStats.
    """
    preset = get_preset(preset_name)
    dirs, files = find_preset_targets(root_path, preset)

    combined_stats = DeletionStats()

    # Delete matching files
    for f in files:
        deleter = FastDeleter(
            target_path=f,
            dry_run=dry_run,
            force=force,
            workers=1,
            use_c_engine=True,
        )
        st = deleter.run()
        combined_stats.files_discovered += st.files_discovered
        combined_stats.files_deleted += st.files_deleted
        combined_stats.bytes_deleted += st.bytes_deleted
        combined_stats.failed += st.failed
        combined_stats.skipped += st.skipped

    # Delete matching directories
    for d in dirs:
        deleter = FastDeleter(
            target_path=d,
            dry_run=dry_run,
            force=force,
            workers=workers,
            use_c_engine=True,
        )
        st = deleter.run()
        combined_stats.files_discovered += st.files_discovered
        combined_stats.files_deleted += st.files_deleted
        combined_stats.directories_deleted += st.directories_deleted
        combined_stats.bytes_deleted += st.bytes_deleted
        combined_stats.failed += st.failed
        combined_stats.skipped += st.skipped

    return combined_stats
