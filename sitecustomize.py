"""Enable SQLAlchemy's pure-Python fallback when locked-down Windows blocks Cython.

In some enterprise-managed environments a DLL-based Cython runtime is blocked by policy,
which makes SQLAlchemy's compiled modules fail to import. Prefer the bundled pure-Python
``*_cy.py`` modules and downgrade ``cython`` import failures to ``ModuleNotFoundError`` so
SQLAlchemy falls back cleanly to the non-compiled path.
"""

from __future__ import annotations

import builtins
import importlib.abc
import importlib.machinery
import importlib.util
import sys
from pathlib import Path

_original_import = builtins.__import__


def _patched_import(name, globals=None, locals=None, fromlist=(), level=0):
    try:
        return _original_import(name, globals, locals, fromlist, level)
    except ImportError as exc:
        if name == "cython" or name.startswith("cython."):
            raise ModuleNotFoundError(str(exc)) from exc
        raise


class _SQLAlchemyPurePythonFinder(importlib.abc.MetaPathFinder):
    """Prefer the pure-Python SQLAlchemy ``*_cy.py`` modules over their blocked .pyd files."""

    def find_spec(self, fullname, path=None, target=None):
        if not fullname.startswith("sqlalchemy."):
            return None
        stem = fullname.rsplit(".", 1)[-1]
        if not stem.endswith("_cy"):
            return None

        package_root = None
        for entry in sys.path:
            if not entry:
                continue
            candidate = Path(entry) / "sqlalchemy"
            if candidate.is_dir():
                package_root = candidate
                break
        if package_root is None:
            return None

        module_path = package_root.joinpath(*fullname.split(".")[1:])
        if module_path.with_suffix(".py").exists():
            return importlib.util.spec_from_file_location(
                fullname,
                module_path.with_suffix(".py"),
                loader=importlib.machinery.SourceFileLoader(fullname, str(module_path.with_suffix(".py"))),
            )
        return None


builtins.__import__ = _patched_import
for finder in sys.meta_path:
    if type(finder).__name__ == "_SQLAlchemyPurePythonFinder":
        break
else:
    sys.meta_path.insert(0, _SQLAlchemyPurePythonFinder())
