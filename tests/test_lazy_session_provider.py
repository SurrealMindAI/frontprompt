"""LazyBrowserSessionProvider — verifies deferred-spawn semantics.

Per the per-daemon browser-session isolation model: the daemon must NOT spawn the
browser child at startup. Only the first MCP-tool-call should trigger the
spawn; subsequent calls reuse the cached session; ``close()`` terminates.
"""

from __future__ import annotations

import sys
from pathlib import Path

import pytest

from frontprompt.ipc.session import SessionMetadata, format_ready_line


def _write_fake_session_json(cache_dir: Path, session_id: str) -> SessionMetadata:
    sdir = cache_dir / "sessions" / session_id
    sdir.mkdir(parents=True)
    meta = SessionMetadata(
        session_id=session_id,
        pid=99999,
        url="about:blank",
        started_at_iso="2026-05-23T22:30:00+00:00",
        socket_path=str(sdir / "show.sock"),
    )
    (sdir / "session.json").write_text(meta.model_dump_json(), encoding="utf-8")
    return meta


@pytest.mark.anyio
async def test_lazy_provider_does_not_spawn_at_construction(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    """Constructing the provider must NOT invoke spawn_show_child_unmanaged."""
    from frontprompt import mcp_server, mcp_spawn

    call_count = 0

    async def _no_spawn(_start_url: str) -> object:
        nonlocal call_count
        call_count += 1
        pytest.fail("spawn_show_child_unmanaged must not be called before first get()")

    monkeypatch.setattr(mcp_spawn, "spawn_show_child_unmanaged", _no_spawn)
    monkeypatch.setattr(mcp_server, "spawn_show_child_unmanaged", _no_spawn)

    provider = mcp_server.LazyBrowserSessionProvider("about:blank")
    assert call_count == 0
    await provider.close()  # close-without-spawn must be no-op
    assert call_count == 0


@pytest.mark.anyio
async def test_lazy_provider_spawns_on_first_get_and_caches(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    """First get() spawns the child; subsequent gets return the cached metadata."""
    from frontprompt import mcp_server, mcp_spawn

    monkeypatch.setenv("FRONTPROMPT_CACHE_DIR", str(tmp_path))
    session_id = "20260523T223000-deadbeef"
    expected = _write_fake_session_json(tmp_path, session_id)

    ready_line = format_ready_line(session_id)
    mock_script = f"import sys, time\nprint({ready_line!r}, flush=True)\ntime.sleep(60)\n"
    monkeypatch.setattr(mcp_spawn, "_build_show_cmd", lambda url: [sys.executable, "-c", mock_script])

    provider = mcp_server.LazyBrowserSessionProvider("about:blank")
    try:
        meta1 = await provider.get()
        assert meta1.session_id == expected.session_id

        meta2 = await provider.get()
        assert meta2 is meta1  # cached, same object reference
    finally:
        await provider.close()


@pytest.mark.anyio
async def test_lazy_provider_close_terminates_spawned_child(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    """After close(), the cached process+session are released; next get() respawns."""
    from frontprompt import mcp_server, mcp_spawn

    monkeypatch.setenv("FRONTPROMPT_CACHE_DIR", str(tmp_path))
    session_id_1 = "20260523T223000-aaaaaaaa"
    _write_fake_session_json(tmp_path, session_id_1)

    ready_line_1 = format_ready_line(session_id_1)
    cmd_script = f"import sys, time\nprint({ready_line_1!r}, flush=True)\ntime.sleep(60)\n"
    monkeypatch.setattr(mcp_spawn, "_build_show_cmd", lambda url: [sys.executable, "-c", cmd_script])

    provider = mcp_server.LazyBrowserSessionProvider("about:blank")
    meta1 = await provider.get()
    assert provider._session_info is not None
    assert provider._process is not None

    await provider.close()
    assert provider._session_info is None
    assert provider._process is None

    # Re-spawn after close: same fake-cmd, same fake session.json reused.
    meta2 = await provider.get()
    assert meta2.session_id == meta1.session_id  # same backing data
    await provider.close()
