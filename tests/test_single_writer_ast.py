"""AST-Compliance-Test — single-writer invariant (kein Lock-Ownership-Bypass)
und structured concurrency (anyio, kein asyncio.create_task()).

Scannt src/frontprompt/bc/**/aggregates/*.py statisch.
Schlägt fehl wenn:
  - ein Aggregate-File threading.Lock, threading.RLock, asyncio.Lock
    oder asyncio.RLock importiert (single-writer: Lock-Import = Pattern-Bruch)
  - ein Aggregate-File asyncio.create_task(...) direkt aufruft
    (structured concurrency: task_group.start_soon() stattdessen)
"""

from __future__ import annotations

import ast
from pathlib import Path

# Pfad relativ zu diesem Test-File: tests/ → project-root → src/
_SRC_ROOT = Path(__file__).parent.parent / "src" / "frontprompt" / "bc"

_FORBIDDEN_LOCK_ATTRS = frozenset({"Lock", "RLock"})
_FORBIDDEN_LOCK_MODULES = frozenset({"threading", "asyncio"})


def _collect_aggregate_files() -> list[Path]:
    """Alle *.py-Dateien unterhalb bc/**/aggregates/ sammeln."""
    found = [p for p in _SRC_ROOT.rglob("aggregates/*.py") if p.name != "__init__.py"]
    return found


def test_no_lock_imports_in_aggregates() -> None:
    """single-writer: kein threading.Lock / asyncio.Lock in Aggregate-Files."""
    files = _collect_aggregate_files()
    assert files, f"keine Aggregate-Files unter {_SRC_ROOT} gefunden — Aggregate noch nicht implementiert?"

    violations: list[str] = []

    for path in files:
        tree = ast.parse(path.read_text(encoding="utf-8"), filename=str(path))
        for node in ast.walk(tree):
            # from threading import Lock / from asyncio import RLock
            if isinstance(node, ast.ImportFrom):
                module = node.module or ""
                base = module.split(".")[0]
                if base in _FORBIDDEN_LOCK_MODULES:
                    imported_names = {alias.name for alias in node.names}
                    bad = imported_names & _FORBIDDEN_LOCK_ATTRS
                    if bad:
                        violations.append(f"{path.name}: imports {bad} from '{module}'")
            # import threading; import asyncio (direct module import, then .Lock)
            elif isinstance(node, ast.Import):
                for alias in node.names:
                    if alias.name in _FORBIDDEN_LOCK_MODULES:
                        # Warnung: direktes `import threading` — wir erlauben das nur wenn
                        # kein .Lock-Attribut-Zugriff folgt. Der zweite Check (create_task)
                        # deckt den asyncio-Fall ab; threading.Lock-Nutzung ohne from-Import
                        # ist im Aggregate-Context trotzdem ein Verstoß.
                        violations.append(
                            f"{path.name}: imports module '{alias.name}' directly — "
                            "use anyio structured concurrency instead of locks"
                        )

    assert not violations, "single-writer Lock-Import-Violation:\n" + "\n".join(violations)


def test_no_asyncio_create_task_in_aggregates() -> None:
    """structured concurrency: kein asyncio.create_task() in Aggregate-Files.

    Aggregate-Code darf kein asyncio.create_task() aufrufen.
    Structured concurrency via anyio task_group.start_soon() ist der korrekte Weg.
    """
    files = _collect_aggregate_files()
    assert files, f"keine Aggregate-Files unter {_SRC_ROOT} gefunden — Aggregate noch nicht implementiert?"

    violations: list[str] = []

    for path in files:
        tree = ast.parse(path.read_text(encoding="utf-8"), filename=str(path))
        for node in ast.walk(tree):
            # asyncio.create_task(...) — Call-Knoten mit Attribut-Zugriff
            if isinstance(node, ast.Call):
                func = node.func
                if (
                    isinstance(func, ast.Attribute)
                    and func.attr == "create_task"
                    and isinstance(func.value, ast.Name)
                    and func.value.id == "asyncio"
                ):
                    violations.append(
                        f"{path.name}: asyncio.create_task() call — use task_group.start_soon() instead (structured concurrency)"
                    )

    assert not violations, "structured-concurrency asyncio.create_task()-Violation:\n" + "\n".join(violations)
