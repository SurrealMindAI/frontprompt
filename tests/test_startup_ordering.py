"""Startup ordering regression.

Asserts via AST inspection that `wait_until_ready` is awaited BEFORE
`verify_mounted` in the _run_browser coroutine. Uses source inspection only
(no async, no Playwright, no anyio) — same approach as test_adr002_ast.py.
"""

from __future__ import annotations

import ast
from pathlib import Path

_SRC_ROOT = Path(__file__).parent.parent / "src" / "frontprompt"


def _find_startup_file() -> Path:
    """Return show_session.py if it exists (post-extraction), else cli.py."""
    candidate = _SRC_ROOT / "show_session.py"
    if candidate.exists():
        return candidate
    return _SRC_ROOT / "cli.py"


def _collect_await_calls(func_body: list[ast.stmt]) -> list[tuple[str, int]]:
    """Walk function body and return (callee_name, lineno) for every await call."""
    results: list[tuple[str, int]] = []
    for node in ast.walk(ast.Module(body=func_body, type_ignores=[])):
        if isinstance(node, ast.Await):
            call = node.value
            if isinstance(call, ast.Call):
                func = call.func
                name = None
                if isinstance(func, ast.Name):
                    name = func.id
                elif isinstance(func, ast.Attribute):
                    name = func.attr
                if name:
                    results.append((name, node.lineno))
    return results


def test_startup_source_file_exists() -> None:
    """The startup file (cli.py or show_session.py) must be parseable Python."""
    target = _find_startup_file()
    assert target.exists(), f"Expected startup file at {target}"
    tree = ast.parse(target.read_text(encoding="utf-8"))
    assert tree is not None


def test_wait_until_ready_before_verify_mounted() -> None:
    """wait_until_ready must be awaited before verify_mounted in _run_browser."""
    target = _find_startup_file()
    tree = ast.parse(target.read_text(encoding="utf-8"))

    # Find the _run_browser async function (may be nested inside other functions)
    run_browser_node: ast.AsyncFunctionDef | None = None
    for node in ast.walk(tree):
        if isinstance(node, ast.AsyncFunctionDef) and node.name == "_run_browser":
            run_browser_node = node
            break

    assert run_browser_node is not None, (
        "_run_browser coroutine not found in startup file — if it was extracted, update the search target in this test."
    )

    await_calls = _collect_await_calls(run_browser_node.body)
    call_map: dict[str, list[int]] = {}
    for name, lineno in await_calls:
        call_map.setdefault(name, []).append(lineno)

    assert "wait_until_ready" in call_map, "wait_until_ready not found as an awaited call in _run_browser"
    assert "verify_mounted" in call_map, "verify_mounted not found as an awaited call in _run_browser"

    first_wait_until_ready = min(call_map["wait_until_ready"])
    first_verify_mounted = min(call_map["verify_mounted"])

    assert first_wait_until_ready < first_verify_mounted, (
        f"Expected wait_until_ready (line {first_wait_until_ready}) "
        f"to appear before verify_mounted (line {first_verify_mounted}). "
        f"Startup race fix not applied."
    )
