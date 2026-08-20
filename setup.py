"""
Optional native acceleration build for fastdelete.

The package is pure Python and fully functional without the C extension;
this setup hook builds the ``_fastdelete_c`` accelerator when a POSIX
compiler is available and silently falls back otherwise.
"""

import sys

from setuptools import Extension, setup
from setuptools.command.build_ext import build_ext


class OptionalBuildExt(build_ext):
    """Build the optional C extension, degrading gracefully to pure Python."""

    def run(self):
        try:
            super().run()
        except Exception as exc:  # no compiler, missing headers, etc.
            sys.stderr.write(
                f"fastdelete: skipping native acceleration ({exc}). "
                f"Pure-Python engine will be used.\n"
            )

    def build_extension(self, ext):
        try:
            super().build_extension(ext)
        except Exception as exc:
            sys.stderr.write(
                f"fastdelete: could not build extension '{ext.name}' ({exc}). "
                f"Pure-Python engine will be used.\n"
            )


ext_modules = []
if sys.platform != "win32":
    ext_modules.append(
        Extension(
            "fastdelete._fastdelete_c",
            sources=["fastdelete/c_engine.c"],
            extra_compile_args=["-O2"],
        )
    )

setup(
    ext_modules=ext_modules,
    cmdclass={"build_ext": OptionalBuildExt},
)
