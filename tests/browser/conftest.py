"""Shared browser-test fixtures for tests/browser/.

Provides:
- ``playground_server`` (session-scoped) — stdlib ``http.server.HTTPServer``
  on a random local port, rooted **exclusively** at
  ``tests/browser/playgrounds/`` (Python-free asset folder).
  atlas convention: the server NEVER roots at a directory containing Python
  source — only the dedicated asset folder. Yields the base URL
  ``http://127.0.0.1:<port>``.
- ``playground_url`` (session-scoped) — callable ``(name: str) -> str`` that
  expands ``name`` → ``http://127.0.0.1:<port>/<name>.html``.
"""

from __future__ import annotations

import threading
from collections.abc import Callable, Iterator
from http.server import BaseHTTPRequestHandler, HTTPServer, SimpleHTTPRequestHandler
from pathlib import Path

import pytest

_PLAYGROUNDS_DIR: Path = Path(__file__).parent / "playgrounds"


def _make_handler(directory: Path) -> type[BaseHTTPRequestHandler]:
    """Return a ``SimpleHTTPRequestHandler`` subclass rooted at *directory*.

    Inherits the stdlib's built-in MIME detection and conditional-GET support.
    Access logs are suppressed to keep test output clean.
    """

    class _PlaygroundHandler(SimpleHTTPRequestHandler):
        def __init__(self, *args: object, **kwargs: object) -> None:
            super().__init__(*args, directory=str(directory), **kwargs)

        def log_message(self, fmt: str, *args: object) -> None:  # type: ignore[override]
            # Suppress per-request access logs during test runs.
            pass

    return _PlaygroundHandler


@pytest.fixture(scope="session")
def playground_server() -> Iterator[str]:
    """Start a local HTTP server rooted at ``tests/browser/playgrounds/``.

    The server binds to ``127.0.0.1:0`` (OS-assigned random port) and runs on
    a daemon thread so it is torn down automatically when the process exits.
    Explicitly calls ``server.shutdown()`` at teardown to release the port
    promptly.

    Yields the base URL ``http://127.0.0.1:<port>``.

    Atlas convention (no-python-via-http): the server is rooted at the
    *asset* folder only (HTML/CSS/JS), never at the ``tests/`` root or any
    directory that contains Python source.
    """
    handler_cls = _make_handler(_PLAYGROUNDS_DIR)
    server = HTTPServer(("127.0.0.1", 0), handler_cls)
    port = server.server_address[1]
    thread = threading.Thread(target=server.serve_forever, daemon=True, name="playground-http")
    thread.start()
    yield f"http://127.0.0.1:{port}"
    server.shutdown()


@pytest.fixture(scope="session")
def playground_url(playground_server: str) -> Callable[[str], str]:
    """Return a callable that resolves a playground name to its full URL.

    Usage::

        def test_something(playground_url: Callable[[str], str]) -> None:
            url = playground_url("scout-elements")
            # → "http://127.0.0.1:<port>/scout-elements.html"

    The ``.html`` extension is appended automatically.
    """

    def _resolve(name: str) -> str:
        return f"{playground_server}/{name}.html"

    return _resolve
