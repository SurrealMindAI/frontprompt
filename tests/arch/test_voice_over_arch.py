"""Architecture tests for the voice-over package (sub-plan 06 section 3).

Tests:
    1. voice/audio_capture.py does NOT import asyncio (uses anyio only)
    2. voice/mic_watcher.py does NOT import asyncio
    3. voice/post_processor.py does NOT import asyncio
    4. voice/backends/mlx_whisper.py does NOT import mlx_whisper at module level (lazy import)
    5. show_session.py handler_count() matches the actual bridge.on() registration count

These are regression guards: if a developer accidentally adds an asyncio import or
forgets to update handler_count(), the test will catch it immediately.
"""

from __future__ import annotations

import ast
import importlib
import importlib.util
from pathlib import Path

import pytest

# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

_SRC_ROOT = Path(__file__).parent.parent.parent / "src" / "frontprompt"


def _source(rel: str) -> Path:
    return _SRC_ROOT / rel


def _ast_module(rel: str) -> ast.Module:
    src = _source(rel).read_text(encoding="utf-8")
    return ast.parse(src, filename=rel)


def _all_imports(tree: ast.Module) -> list[str]:
    """Return all top-level AND nested module names imported in the AST."""
    names: list[str] = []
    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            for alias in node.names:
                names.append(alias.name)
        elif isinstance(node, ast.ImportFrom):
            if node.module:
                names.append(node.module)
    return names


def _top_level_imports(tree: ast.Module) -> list[str]:
    """Return only module-level (non-function-body) imports.

    Walks only the direct children of the module node, not nested scopes.
    This correctly identifies imports that execute at module load time.
    """
    names: list[str] = []
    for node in tree.body:
        if isinstance(node, ast.Import):
            for alias in node.names:
                names.append(alias.name)
        elif isinstance(node, ast.ImportFrom):
            if node.module:
                names.append(node.module)
        # TYPE_CHECKING guards: if-blocks at module level with Import inside
        elif isinstance(node, ast.If):
            # Check if it's a TYPE_CHECKING guard — those don't execute at runtime
            test = node.test
            is_type_checking = (
                (isinstance(test, ast.Name) and test.id == "TYPE_CHECKING")
                or (
                    isinstance(test, ast.Attribute)
                    and test.attr == "TYPE_CHECKING"
                )
            )
            if not is_type_checking:
                # Non-TYPE_CHECKING if-block: imports inside DO execute at module load
                for child in ast.walk(node):
                    if isinstance(child, ast.Import):
                        for alias in child.names:
                            names.append(alias.name)
                    elif isinstance(child, ast.ImportFrom):
                        if child.module:
                            names.append(child.module)
    return names


def _count_bridge_on_calls_excluding_dead_code(rel: str) -> int:
    """Count bridge.on(...) calls in the source, excluding the dead _register_handlers method.

    show_session.py has two places with bridge.on() registrations:
    - ``_register_handlers()`` — defined but NEVER called (dead code, kept as doc reference)
    - inline inside ``_run_browser()`` nested in ``run()`` — the live execution path

    We count only the live registrations by skipping any FunctionDef named
    ``_register_handlers``.
    """
    src = _source(rel).read_text(encoding="utf-8")
    tree = ast.parse(src, filename=rel)

    class _Visitor(ast.NodeVisitor):
        def __init__(self) -> None:
            self.count = 0
            self._in_register_handlers = False

        def visit_FunctionDef(self, node: ast.FunctionDef) -> None:
            if node.name == "_register_handlers":
                # Skip this dead-code method entirely
                return
            self.generic_visit(node)

        def visit_AsyncFunctionDef(self, node: ast.AsyncFunctionDef) -> None:
            self.generic_visit(node)

        def visit_Call(self, node: ast.Call) -> None:
            if (
                isinstance(node.func, ast.Attribute)
                and node.func.attr == "on"
                and isinstance(node.func.value, ast.Name)
                and node.func.value.id == "bridge"
            ):
                self.count += 1
            self.generic_visit(node)

    visitor = _Visitor()
    visitor.visit(tree)
    return visitor.count


# ---------------------------------------------------------------------------
# Section 3a: asyncio absence in voice package
# ---------------------------------------------------------------------------


def test_audio_capture_no_asyncio_import() -> None:
    """voice/audio_capture.py MUST NOT import asyncio at module level (anyio only).

    sounddevice callbacks are C-thread callbacks — anyio-safe, asyncio-free.
    """
    tree = _ast_module("voice/audio_capture.py")
    top_level = _top_level_imports(tree)
    asyncio_imports = [n for n in top_level if n == "asyncio" or n.startswith("asyncio.")]
    assert not asyncio_imports, (
        f"voice/audio_capture.py must not import asyncio at module level. "
        f"Found: {asyncio_imports}. Use anyio equivalents."
    )


def test_mic_watcher_no_asyncio_import() -> None:
    """voice/mic_watcher.py MUST NOT import asyncio at module level (anyio only)."""
    tree = _ast_module("voice/mic_watcher.py")
    top_level = _top_level_imports(tree)
    asyncio_imports = [n for n in top_level if n == "asyncio" or n.startswith("asyncio.")]
    assert not asyncio_imports, (
        f"voice/mic_watcher.py must not import asyncio at module level. "
        f"Found: {asyncio_imports}. Use anyio equivalents."
    )


def test_post_processor_no_asyncio_import() -> None:
    """voice/post_processor.py MUST NOT import asyncio at module level (anyio only)."""
    tree = _ast_module("voice/post_processor.py")
    top_level = _top_level_imports(tree)
    asyncio_imports = [n for n in top_level if n == "asyncio" or n.startswith("asyncio.")]
    assert not asyncio_imports, (
        f"voice/post_processor.py must not import asyncio at module level. "
        f"Found: {asyncio_imports}. Use anyio equivalents."
    )


# ---------------------------------------------------------------------------
# Section 3b: mlx_whisper lazy import guard
# ---------------------------------------------------------------------------


def test_mlx_whisper_backend_lazy_import() -> None:
    """voice/backends/mlx_whisper.py MUST NOT import mlx_whisper at module level.

    mlx_whisper is a [voice] optional extra — importing it at module load would
    crash any frontprompt install without the [voice] extra.
    """
    tree = _ast_module("voice/backends/mlx_whisper.py")
    # Check all top-level imports (excluding TYPE_CHECKING blocks)
    top_level = _top_level_imports(tree)
    mlx_imports = [n for n in top_level if n.startswith("mlx")]
    assert not mlx_imports, (
        f"voice/backends/mlx_whisper.py must lazy-import mlx_whisper inside methods. "
        f"Found top-level mlx imports: {mlx_imports}. "
        f"Move import inside transcribe() or probe_status()."
    )


# ---------------------------------------------------------------------------
# Section 3c: handler_count() regression guard
# ---------------------------------------------------------------------------


def test_show_session_handler_count_matches_bridge_on_registrations() -> None:
    """show_session.py handler_count() must match the actual bridge.on() call count.

    This is a regression guard: if a developer adds/removes a bridge.on() call
    without updating handler_count(), this test will fail immediately.

    Counted via AST — looks for `bridge.on(...)` call expressions in show_session.py.
    """
    from frontprompt.show_session import ShowSession

    # AST count: how many live bridge.on(...) calls are in the source?
    # Excludes _register_handlers() which is dead code (never called).
    ast_count = _count_bridge_on_calls_excluding_dead_code("show_session.py")

    # handler_count() declares what the code claims to register
    session = ShowSession(url="http://example.com")
    declared_count = session.handler_count()

    assert ast_count == declared_count, (
        f"handler_count() returns {declared_count} but AST found {ast_count} "
        f"bridge.on(...) calls in show_session.py. "
        f"Update handler_count() or add/remove the matching bridge.on() registration."
    )
