"""Arch test: scrapling isolation.

Only src/frontprompt/analysis/_impl/scrapling_bridge.py and
src/frontprompt/scrapling/ (the existing Wave-A navigation substrate) may
import scrapling.*. Every other Python file in src/frontprompt/ that does so
is an isolation violation.

Rationale: scrapling has bus-factor=1 (D4Vinci 97% commits). If the library
stalls, only one file needs to change.

See the Scrapling-Bridge Isolation design note.
"""

from __future__ import annotations

import ast
import glob
from pathlib import Path

import pytest

SRC_ROOT = Path(__file__).resolve().parents[2] / "src" / "frontprompt"

# Files that are explicitly allowed to import scrapling.*.
# Paths are relative to SRC_ROOT.
SCRAPLING_IMPORT_ALLOWLIST: frozenset[str] = frozenset(
    {
        # New bridge — the only analysis-layer file that may import scrapling
        "analysis/_impl/scrapling_bridge.py",
        # Existing Wave-A navigation substrate — ScraplingAdapter, fetchers, etc.
        # This entire sub-package legitimately depends on scrapling.
        "scrapling/adapter.py",
        "scrapling/substrate_router.py",
        "scrapling/user_data_dir.py",
    }
)


def _has_scrapling_import(source: str) -> bool:
    """Return True if source AST contains any `import scrapling.*` or
    `from scrapling ...` statement."""
    try:
        tree = ast.parse(source)
    except SyntaxError:
        return False
    for node in ast.walk(tree):
        if isinstance(node, ast.ImportFrom) and node.module:
            if node.module.startswith("scrapling"):
                return True
        if isinstance(node, ast.Import):
            for alias in node.names:
                if alias.name.startswith("scrapling"):
                    return True
    return False


def test_only_allowlisted_files_import_scrapling() -> None:
    """AST scan: no file outside the allowlist may import scrapling.*"""
    violations: list[str] = []
    for py_path_str in glob.glob(str(SRC_ROOT / "**" / "*.py"), recursive=True):
        py_path = Path(py_path_str)
        if "__pycache__" in py_path.parts:
            continue
        rel = py_path.relative_to(SRC_ROOT).as_posix()
        if rel in SCRAPLING_IMPORT_ALLOWLIST:
            continue
        source = py_path.read_text(encoding="utf-8")
        if _has_scrapling_import(source):
            violations.append(rel)

    if violations:
        formatted = "\n  ".join(violations)
        pytest.fail(
            "\n"
            "═" * 72 + "\n"
            "ARCH VIOLATION: scrapling isolation\n"
            "═" * 72 + "\n\n"
            "Only the following files may import scrapling.*:\n"
            f"  {chr(10).join(sorted(SCRAPLING_IMPORT_ALLOWLIST))}\n\n"
            f"Violating files:\n  {formatted}\n\n"
            "Add the bridge API to analysis/_impl/scrapling_bridge.py and\n"
            "call it from there instead.\n"
            "See the Scrapling-Bridge Isolation design note."
        )


def test_allowlist_entries_all_exist() -> None:
    """Every entry in SCRAPLING_IMPORT_ALLOWLIST must resolve to an existing file.

    Catches stale allowlist entries after file renames.
    """
    missing = [rel for rel in SCRAPLING_IMPORT_ALLOWLIST if not (SRC_ROOT / rel).is_file()]
    assert not missing, (
        "SCRAPLING_IMPORT_ALLOWLIST contains entries that do not exist:\n"
        + "\n".join(missing)
        + "\nUpdate the allowlist in tests/arch/test_scrapling_isolation.py."
    )


def test_new_analysis_files_exist() -> None:
    """Smoke test: all expected new files from sub-plans 01+02 are present."""
    expected = [
        "analysis/__init__.py",
        "analysis/analyzer.py",
        "analysis/snapshot.py",
        "analysis/types.py",
        "analysis/outline.py",
        "analysis/finders.py",
        "analysis/context.py",
        "analysis/relocator.py",
        "analysis/inspect.py",
        "analysis/_impl/__init__.py",
        "analysis/_impl/scrapling_bridge.py",
    ]
    missing = [f for f in expected if not (SRC_ROOT / f).is_file()]
    assert not missing, f"Expected analysis files not found: {missing}"


def test_scrapling_bridge_is_the_only_file_with_scrapling_import_statements() -> None:
    """Redundant sanity check: only analysis/_impl/scrapling_bridge.py should have
    actual scrapling import statements in the analysis sub-package.

    Uses the same AST-based detection as test_only_allowlisted_files_import_scrapling
    but scoped to the analysis/ sub-package for a more targeted diagnostic.
    """
    violations: list[str] = []
    analysis_root = SRC_ROOT / "analysis"
    for py_file in analysis_root.rglob("*.py"):
        if "__pycache__" in py_file.parts:
            continue
        source = py_file.read_text(encoding="utf-8")
        if _has_scrapling_import(source):
            rel = py_file.relative_to(SRC_ROOT).as_posix()
            if rel != "analysis/_impl/scrapling_bridge.py":
                violations.append(rel)
    assert not violations, (
        f"Only analysis/_impl/scrapling_bridge.py may import scrapling in the analysis package. "
        f"Violations: {violations}"
    )
