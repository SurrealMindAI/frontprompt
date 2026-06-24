"""Tests for per-session on-disk structured logging (frontprompt.logging).

Verifies that ``configure_logging`` installs a JSON-lines file sink alongside
the existing stderr console sink, that the file lands at the documented path
(session-dir when a session_id is available, pid-fallback otherwise), and that
a representative log event is actually written as structured JSON.
"""

from __future__ import annotations

import json
import os
import shutil
import tempfile
from collections.abc import Iterator
from pathlib import Path

import pytest
import structlog

from frontprompt import logging as fp_logging
from frontprompt.ipc.paths import logs_root, session_dir, session_log_path


@pytest.fixture
def socket_path() -> Iterator[Path]:
    """Short tmp socket path under /tmp (AF_UNIX 104-byte limit on macOS)."""
    d = Path(tempfile.mkdtemp(prefix="fp-log-", dir="/tmp"))
    try:
        yield d / "s.sock"
    finally:
        shutil.rmtree(d, ignore_errors=True)


@pytest.fixture
def isolated_cache(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> Path:
    """Redirect the frontprompt cache-root into a tmp dir for log-file isolation."""
    monkeypatch.setenv("FRONTPROMPT_CACHE_DIR", str(tmp_path))
    return tmp_path


@pytest.fixture(autouse=True)
def _reset_logging() -> object:
    """Reset structlog + stdlib logging handlers installed by configure_logging.

    Without this, the file handler from one test leaks into the next.
    """
    yield
    fp_logging.reset_logging()


def test_session_log_path_under_session_dir(isolated_cache: Path) -> None:
    """A session_id resolves the log to ``<session-dir>/<role>.log``."""
    path = session_log_path("20260602T101010-deadbeef", "daemon")
    assert path == session_dir("20260602T101010-deadbeef") / "daemon.log"


def test_configure_logging_writes_json_to_session_file(isolated_cache: Path) -> None:
    """A configured session-scoped logger writes a JSON line to the session file."""
    session_id = "20260602T101010-deadbeef"
    fp_logging.configure_logging(role="daemon", session_id=session_id)

    log = structlog.get_logger("frontprompt.test")
    log.info("page_info.start", pick_id="abc")

    log_file = session_log_path(session_id, "daemon")
    assert log_file.exists(), f"expected log file at {log_file}"

    lines = [ln for ln in log_file.read_text(encoding="utf-8").splitlines() if ln.strip()]
    assert lines, "expected at least one structured log line"
    record = json.loads(lines[-1])
    assert record["event"] == "page_info.start"
    assert record["pick_id"] == "abc"
    assert "level" in record
    assert "timestamp" in record


def test_configure_logging_pid_fallback_when_no_session(isolated_cache: Path) -> None:
    """Without a session_id, the sink falls back to ``logs/<pid>-<role>.log``."""
    fp_logging.configure_logging(role="show", session_id=None)

    log = structlog.get_logger("frontprompt.test")
    log.info("show.boot")

    expected = logs_root() / f"{os.getpid()}-show.log"
    assert expected.exists(), f"expected fallback log file at {expected}"
    record = json.loads(expected.read_text(encoding="utf-8").splitlines()[-1])
    assert record["event"] == "show.boot"


def test_configure_logging_keeps_stderr(isolated_cache: Path, capfd: pytest.CaptureFixture[str]) -> None:
    """The stderr console sink is preserved alongside the file sink."""
    fp_logging.configure_logging(role="daemon", session_id="20260602T101010-deadbeef")
    log = structlog.get_logger("frontprompt.test")
    log.info("daemon.cli.startup")

    captured = capfd.readouterr()
    assert "daemon.cli.startup" in (captured.err + captured.out)


@pytest.mark.anyio
async def test_ipc_dispatch_trace_lands_in_session_log(isolated_cache: Path, socket_path: Path) -> None:
    """A real IPC dispatch writes ``ipc.dispatch.start``/``.done`` to the session log.

    This is the representative end-to-end assertion: with logging configured to a
    session file, a round-trip through the socket-server's _handle_connection
    leaves a structured entry/exit pair on disk — the diagnosability property the
    feature exists for.
    """
    import anyio

    from frontprompt.ipc import PingRequest, query, run_socket_server
    from frontprompt.state import StateManager
    from tests.ipc.fakes import FakePageController

    session_id = "20260602T120000-cafef00d"
    log_file = fp_logging.configure_logging(role="show", session_id=session_id)

    sm = StateManager(session_id=session_id)
    fake = FakePageController()

    async with anyio.create_task_group() as tg:
        tg.start_soon(run_socket_server, sm, socket_path, fake)
        for _ in range(50):
            if socket_path.exists():
                break
            await anyio.sleep(0.02)
        response = await query(socket_path, PingRequest())
        assert response.ok is True
        tg.cancel_scope.cancel()

    contents = log_file.read_text(encoding="utf-8")
    events = [json.loads(ln)["event"] for ln in contents.splitlines() if ln.strip()]
    assert "ipc.dispatch.start" in events
    assert "ipc.dispatch.done" in events
