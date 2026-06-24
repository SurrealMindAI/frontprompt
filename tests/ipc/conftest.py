"""Shared fixtures for frontprompt IPC tests.

Scout-mode refactor: extracted short_socket_dir from test_server_client.py
so it can be reused by test_socket_server_v0_3_0.py (and future IPC tests).
"""

from __future__ import annotations

import shutil
import tempfile
from collections.abc import Iterator
from pathlib import Path

import pytest


@pytest.fixture
def short_socket_dir() -> Iterator[Path]:
    """Erzeuge tmp-dir in ``/tmp/`` (kurz genug für AF_UNIX-104-byte-limit auf macOS)."""
    d = Path(tempfile.mkdtemp(prefix="fp-test-", dir="/tmp"))
    try:
        yield d
    finally:
        shutil.rmtree(d, ignore_errors=True)


@pytest.fixture
def socket_path(short_socket_dir: Path) -> Path:
    return short_socket_dir / "s.sock"
