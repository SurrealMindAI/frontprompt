"""mcp_spawn.spawn_show_child — tests with mock-subprocess.

Per the per-daemon browser-session isolation model: the MCP daemon spawns `frontprompt show` as its private child and
discovers the child's session via the stdout ready-line. We exercise the helper
with a `python -c`-script that mimics show's stdout protocol — no Playwright,
no real browser, just the spawn-handshake mechanics.
"""

from __future__ import annotations

import sys
from pathlib import Path

import pytest

from frontprompt.ipc.session import SessionMetadata, format_ready_line


def _write_fake_session_json(cache_dir: Path, session_id: str, *, url: str = "about:blank") -> SessionMetadata:
    sdir = cache_dir / "sessions" / session_id
    sdir.mkdir(parents=True)
    socket_path = sdir / "show.sock"
    meta = SessionMetadata(
        session_id=session_id,
        pid=99999,
        url=url,
        started_at_iso="2026-05-23T14:30:45+00:00",
        socket_path=str(socket_path),
    )
    (sdir / "session.json").write_text(meta.model_dump_json(), encoding="utf-8")
    return meta


@pytest.mark.anyio
async def test_spawn_reads_ready_line_and_loads_metadata(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    """Mock subprocess prints ready-line + we pre-write session.json — helper returns both."""
    monkeypatch.setenv("FRONTPROMPT_CACHE_DIR", str(tmp_path))
    session_id = "20260523T143045-aaaaaaaa"
    expected_meta = _write_fake_session_json(tmp_path, session_id, url="https://example.com")

    from frontprompt import mcp_spawn

    ready_line = format_ready_line(session_id)
    mock_script = f"import sys, time\nprint({ready_line!r}, flush=True)\ntime.sleep(60)\n"
    monkeypatch.setattr(mcp_spawn, "_build_show_cmd", lambda url: [sys.executable, "-c", mock_script])

    async with mcp_spawn.spawn_show_child("about:blank") as (process, metadata):
        assert metadata.session_id == expected_meta.session_id
        assert metadata.url == expected_meta.url
        assert metadata.socket_path == expected_meta.socket_path
        assert process.returncode is None  # still running


@pytest.mark.anyio
async def test_spawn_ignores_pre_ready_log_lines(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    """Mock subprocess prints log noise first, then the ready-line — helper picks the right one."""
    monkeypatch.setenv("FRONTPROMPT_CACHE_DIR", str(tmp_path))
    session_id = "20260523T143045-bbbbbbbb"
    _write_fake_session_json(tmp_path, session_id)

    from frontprompt import mcp_spawn

    ready_line = format_ready_line(session_id)
    mock_script = (
        "import sys, time\n"
        "print('2026-05-23 14:30 [info] daemon.cli.startup', flush=True)\n"
        "print('some structlog noise here', flush=True)\n"
        f"print({ready_line!r}, flush=True)\n"
        "time.sleep(60)\n"
    )
    monkeypatch.setattr(mcp_spawn, "_build_show_cmd", lambda url: [sys.executable, "-c", mock_script])

    async with mcp_spawn.spawn_show_child("about:blank") as (_process, metadata):
        assert metadata.session_id == session_id


@pytest.mark.anyio
async def test_spawn_times_out_when_no_ready_line(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    """Mock subprocess prints unrelated output forever — helper raises ShowSpawnError."""
    from frontprompt import mcp_spawn

    monkeypatch.setattr(mcp_spawn, "READY_TIMEOUT_S", 0.5)
    mock_script = "import sys, time\nwhile True:\n    print('unrelated noise', flush=True)\n    time.sleep(0.1)\n"
    monkeypatch.setattr(mcp_spawn, "_build_show_cmd", lambda url: [sys.executable, "-c", mock_script])

    with pytest.raises(mcp_spawn.ShowSpawnError, match=r"[Tt]imeout"):
        async with mcp_spawn.spawn_show_child("about:blank"):
            pytest.fail("should not enter the body")


@pytest.mark.anyio
async def test_spawn_raises_when_child_exits_before_ready(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    """Mock subprocess exits immediately without printing ready-line — helper raises."""
    from frontprompt import mcp_spawn

    monkeypatch.setattr(mcp_spawn, "READY_TIMEOUT_S", 5.0)
    mock_script = "import sys\nprint('boot log only', flush=True)\nsys.exit(1)\n"
    monkeypatch.setattr(mcp_spawn, "_build_show_cmd", lambda url: [sys.executable, "-c", mock_script])

    with pytest.raises(mcp_spawn.ShowSpawnError, match=r"closed stdout|stderr"):
        async with mcp_spawn.spawn_show_child("about:blank"):
            pytest.fail("should not enter the body")


@pytest.mark.anyio
async def test_spawn_raises_when_session_json_missing(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    """Mock subprocess prints ready-line for a session whose session.json was never written."""
    from frontprompt import mcp_spawn

    monkeypatch.setenv("FRONTPROMPT_CACHE_DIR", str(tmp_path))
    session_id = "20260523T143045-cccccccc"  # no session.json on disk

    ready_line = format_ready_line(session_id)
    mock_script = f"import sys, time\nprint({ready_line!r}, flush=True)\ntime.sleep(60)\n"
    monkeypatch.setattr(mcp_spawn, "_build_show_cmd", lambda url: [sys.executable, "-c", mock_script])

    with pytest.raises(mcp_spawn.ShowSpawnError, match=r"session\.json"):
        async with mcp_spawn.spawn_show_child("about:blank"):
            pytest.fail("should not enter the body")
