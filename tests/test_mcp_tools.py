"""mcp_server.serve_mcp_stdio — per-tool dispatch tests with mock IPC.

Per the per-daemon browser-session isolation model, each MCP-Tool routes to the existing Unix-Socket IPC of the daemon's
owned browser-session. These tests patch ``frontprompt.mcp_server.query`` with a
fake that captures the IpcRequest and returns a canned IpcResponse — no real
``frontprompt show`` subprocess, no Playwright.
"""

from __future__ import annotations

import json
from pathlib import Path

import anyio
import pytest
from anyio.streams.memory import MemoryObjectReceiveStream, MemoryObjectSendStream
from mcp import ClientSession
from mcp.shared.message import SessionMessage

from frontprompt.ipc import IpcConnectError
from frontprompt.ipc.protocol import (
    GetPickRequest,
    GetPicksRequest,
    GetSnapshotRequest,
    GetStateSummaryRequest,
    IpcResponse,
    NavigateRequest,
    PingRequest,
)
from frontprompt.ipc.session import SessionMetadata


def _fake_session_info(tmp_path: Path) -> SessionMetadata:
    return SessionMetadata(
        session_id="20260523T143045-cafebabe",
        pid=12345,
        url="https://example.com",
        started_at_iso="2026-05-23T14:30:45+00:00",
        socket_path=str(tmp_path / "show.sock"),
    )


def _make_stream_pair() -> tuple[
    MemoryObjectReceiveStream[SessionMessage | Exception],
    MemoryObjectSendStream[SessionMessage],
    MemoryObjectReceiveStream[SessionMessage | Exception],
    MemoryObjectSendStream[SessionMessage],
]:
    client_send, server_read = anyio.create_memory_object_stream(16)  # type: ignore[assignment]
    server_send, client_read = anyio.create_memory_object_stream(16)  # type: ignore[assignment]
    return server_read, client_send, client_read, server_send  # type: ignore[return-value]


@pytest.mark.anyio
async def test_get_session_info_returns_metadata_without_ipc(
    anyio_backend: str, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """get_session_info needs no IPC — returns cached SessionMetadata as JSON text."""
    from frontprompt import mcp_server as mcp_server_mod

    async def _fail_query(*_args: object, **_kwargs: object) -> object:
        pytest.fail("ipc.query should not be called for get_session_info")

    monkeypatch.setattr(mcp_server_mod, "query", _fail_query)

    session_info = _fake_session_info(tmp_path)
    server_read, client_send, client_read, server_send = _make_stream_pair()

    async with anyio.create_task_group() as tg:
        tg.start_soon(
            mcp_server_mod.serve_mcp_stdio,
            mcp_server_mod.StaticSessionProvider(session_info),
            server_read,
            server_send,
        )

        async with ClientSession(client_read, client_send) as session:
            await session.initialize()
            result = await session.call_tool("frontprompt_get_session_info", {})
            assert not result.isError, f"unexpected error: {result.content}"
            text = result.content[0].text  # type: ignore[union-attr]
            data = json.loads(text)
            assert data["session_id"] == session_info.session_id
            assert data["url"] == session_info.url
            assert data["socket_path"] == session_info.socket_path

        tg.cancel_scope.cancel()


@pytest.mark.anyio
async def test_ping_dispatches_ping_request(
    anyio_backend: str, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """frontprompt_ping → ipc.query with PingRequest, returns the data payload."""
    from frontprompt import mcp_server as mcp_server_mod

    captured: list[tuple[Path, object]] = []

    async def _fake_query(socket_path: Path, request: object) -> IpcResponse:
        captured.append((socket_path, request))
        return IpcResponse(ok=True, data={"pong": True})

    monkeypatch.setattr(mcp_server_mod, "query", _fake_query)

    session_info = _fake_session_info(tmp_path)
    server_read, client_send, client_read, server_send = _make_stream_pair()

    async with anyio.create_task_group() as tg:
        tg.start_soon(
            mcp_server_mod.serve_mcp_stdio,
            mcp_server_mod.StaticSessionProvider(session_info),
            server_read,
            server_send,
        )

        async with ClientSession(client_read, client_send) as session:
            await session.initialize()
            result = await session.call_tool("frontprompt_ping", {})
            assert not result.isError
            payload = json.loads(result.content[0].text)  # type: ignore[union-attr]
            assert payload == {"pong": True}

        tg.cancel_scope.cancel()

    assert len(captured) == 1
    socket_path, request = captured[0]
    assert socket_path == Path(session_info.socket_path)
    assert isinstance(request, PingRequest)


@pytest.mark.anyio
async def test_get_picks_dispatches_get_picks_request(
    anyio_backend: str, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """frontprompt_get_picks → ipc.query with GetPicksRequest, returns the list payload."""
    from frontprompt import mcp_server as mcp_server_mod

    captured: list[tuple[Path, object]] = []
    fake_picks = [
        {"pick_id": "p1", "selector": "div.foo"},
        {"pick_id": "p2", "selector": "span.bar"},
    ]

    async def _fake_query(socket_path: Path, request: object) -> IpcResponse:
        captured.append((socket_path, request))
        return IpcResponse(ok=True, data=fake_picks)

    monkeypatch.setattr(mcp_server_mod, "query", _fake_query)

    session_info = _fake_session_info(tmp_path)
    server_read, client_send, client_read, server_send = _make_stream_pair()

    async with anyio.create_task_group() as tg:
        tg.start_soon(
            mcp_server_mod.serve_mcp_stdio,
            mcp_server_mod.StaticSessionProvider(session_info),
            server_read,
            server_send,
        )

        async with ClientSession(client_read, client_send) as session:
            await session.initialize()
            result = await session.call_tool("frontprompt_get_picks", {})
            assert not result.isError
            payload = json.loads(result.content[0].text)  # type: ignore[union-attr]
            assert payload == fake_picks

        tg.cancel_scope.cancel()

    assert len(captured) == 1
    assert isinstance(captured[0][1], GetPicksRequest)


@pytest.mark.anyio
async def test_get_snapshot_dispatches_get_snapshot_request(
    anyio_backend: str, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """frontprompt_get_snapshot → ipc.query with GetSnapshotRequest."""
    from frontprompt import mcp_server as mcp_server_mod

    async def _fake_query(_socket: Path, request: object) -> IpcResponse:
        assert isinstance(request, GetSnapshotRequest)
        return IpcResponse(ok=True, data={"inspector_state": {"picks": []}})

    monkeypatch.setattr(mcp_server_mod, "query", _fake_query)

    session_info = _fake_session_info(tmp_path)
    server_read, client_send, client_read, server_send = _make_stream_pair()

    async with anyio.create_task_group() as tg:
        tg.start_soon(
            mcp_server_mod.serve_mcp_stdio,
            mcp_server_mod.StaticSessionProvider(session_info),
            server_read,
            server_send,
        )

        async with ClientSession(client_read, client_send) as session:
            await session.initialize()
            result = await session.call_tool("frontprompt_get_snapshot", {})
            assert not result.isError
            payload = json.loads(result.content[0].text)  # type: ignore[union-attr]
            assert payload == {"inspector_state": {"picks": []}}

        tg.cancel_scope.cancel()


@pytest.mark.anyio
async def test_get_state_summary_dispatches_get_state_summary_request(
    anyio_backend: str, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """frontprompt_get_state_summary → ipc.query with GetStateSummaryRequest."""
    from frontprompt import mcp_server as mcp_server_mod

    captured: list[object] = []
    fake_summary = {
        "schema_version": "0.7.0",
        "current_session_id": "sess-x",
        "active_pick_id": None,
        "active_region_id": None,
        "counts": {"picks": 3, "regions": 1, "relations": 0},
        "by_origin_session": [{"session": "sess-x", "picks": 3, "regions": 1, "relations": 0}],
        "by_hostname": [{"hostname": "example.com", "picks": 3}],
        "owned_vs_foreign": {"owned": 3, "foreign": 0},
    }

    async def _fake_query(_socket: Path, request: object) -> IpcResponse:
        captured.append(request)
        return IpcResponse(ok=True, data=fake_summary)

    monkeypatch.setattr(mcp_server_mod, "query", _fake_query)

    session_info = _fake_session_info(tmp_path)
    server_read, client_send, client_read, server_send = _make_stream_pair()

    async with anyio.create_task_group() as tg:
        tg.start_soon(
            mcp_server_mod.serve_mcp_stdio,
            mcp_server_mod.StaticSessionProvider(session_info),
            server_read,
            server_send,
        )

        async with ClientSession(client_read, client_send) as session:
            await session.initialize()
            tools = await session.list_tools()
            assert "frontprompt_get_state_summary" in {t.name for t in tools.tools}

            result = await session.call_tool("frontprompt_get_state_summary", {})
            assert not result.isError
            payload = json.loads(result.content[0].text)  # type: ignore[union-attr]
            assert payload == fake_summary

        tg.cancel_scope.cancel()

    assert len(captured) == 1
    assert isinstance(captured[0], GetStateSummaryRequest)


@pytest.mark.anyio
async def test_get_pick_dispatches_get_pick_request_with_id(
    anyio_backend: str, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """frontprompt_get_pick with pick_id argument → GetPickRequest(pick_id=...)."""
    from frontprompt import mcp_server as mcp_server_mod

    async def _fake_query(_socket: Path, request: object) -> IpcResponse:
        assert isinstance(request, GetPickRequest)
        assert request.pick_id == "the-pick-id"
        return IpcResponse(ok=True, data={"pick_id": "the-pick-id", "selector": "div.x"})

    monkeypatch.setattr(mcp_server_mod, "query", _fake_query)

    session_info = _fake_session_info(tmp_path)
    server_read, client_send, client_read, server_send = _make_stream_pair()

    async with anyio.create_task_group() as tg:
        tg.start_soon(
            mcp_server_mod.serve_mcp_stdio,
            mcp_server_mod.StaticSessionProvider(session_info),
            server_read,
            server_send,
        )

        async with ClientSession(client_read, client_send) as session:
            await session.initialize()
            result = await session.call_tool("frontprompt_get_pick", {"pick_id": "the-pick-id"})
            assert not result.isError
            payload = json.loads(result.content[0].text)  # type: ignore[union-attr]
            assert payload["pick_id"] == "the-pick-id"

        tg.cancel_scope.cancel()


@pytest.mark.anyio
async def test_browser_session_ended_when_ipc_connect_fails(
    anyio_backend: str, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """IpcConnectError → tool result is marked isError with 'browser session ended' message."""
    from frontprompt import mcp_server as mcp_server_mod

    async def _fake_query(_socket: Path, _request: object) -> IpcResponse:
        raise IpcConnectError("kein frontprompt show an /tmp/dead.sock erreichbar")

    monkeypatch.setattr(mcp_server_mod, "query", _fake_query)

    session_info = _fake_session_info(tmp_path)
    server_read, client_send, client_read, server_send = _make_stream_pair()

    async with anyio.create_task_group() as tg:
        tg.start_soon(
            mcp_server_mod.serve_mcp_stdio,
            mcp_server_mod.StaticSessionProvider(session_info),
            server_read,
            server_send,
        )

        async with ClientSession(client_read, client_send) as session:
            await session.initialize()
            result = await session.call_tool("frontprompt_ping", {})
            assert result.isError, "expected isError=True when IPC connect fails"
            text = result.content[0].text  # type: ignore[union-attr]
            assert "browser session ended" in text.lower(), f"unexpected text: {text!r}"

        tg.cancel_scope.cancel()


@pytest.mark.anyio
async def test_pick_not_found_propagates_as_error(
    anyio_backend: str, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """ok=false response from IPC → tool result is marked isError with the IPC error message."""
    from frontprompt import mcp_server as mcp_server_mod

    async def _fake_query(_socket: Path, _request: object) -> IpcResponse:
        return IpcResponse(ok=False, error="pick_not_found")

    monkeypatch.setattr(mcp_server_mod, "query", _fake_query)

    session_info = _fake_session_info(tmp_path)
    server_read, client_send, client_read, server_send = _make_stream_pair()

    async with anyio.create_task_group() as tg:
        tg.start_soon(
            mcp_server_mod.serve_mcp_stdio,
            mcp_server_mod.StaticSessionProvider(session_info),
            server_read,
            server_send,
        )

        async with ClientSession(client_read, client_send) as session:
            await session.initialize()
            result = await session.call_tool("frontprompt_get_pick", {"pick_id": "ghost"})
            assert result.isError, "expected isError=True for pick_not_found"
            text = result.content[0].text  # type: ignore[union-attr]
            assert "pick_not_found" in text

        tg.cancel_scope.cancel()


@pytest.mark.anyio
async def test_navigate_dispatches_navigate_request_with_url(
    anyio_backend: str, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """frontprompt_navigate with url argument → NavigateRequest(url=...)."""
    from frontprompt import mcp_server as mcp_server_mod

    async def _fake_query(_socket: Path, request: object) -> IpcResponse:
        assert isinstance(request, NavigateRequest)
        assert request.url == "https://example.com"
        return IpcResponse(ok=True, data={"navigated_to": "https://example.com", "title": "Example Domain"})

    monkeypatch.setattr(mcp_server_mod, "query", _fake_query)

    session_info = _fake_session_info(tmp_path)
    server_read, client_send, client_read, server_send = _make_stream_pair()

    async with anyio.create_task_group() as tg:
        tg.start_soon(
            mcp_server_mod.serve_mcp_stdio,
            mcp_server_mod.StaticSessionProvider(session_info),
            server_read,
            server_send,
        )

        async with ClientSession(client_read, client_send) as session:
            await session.initialize()
            result = await session.call_tool("frontprompt_navigate", {"url": "https://example.com"})
            assert not result.isError
            payload = json.loads(result.content[0].text)  # type: ignore[union-attr]
            assert payload["navigated_to"] == "https://example.com"
            assert payload["title"] == "Example Domain"

        tg.cancel_scope.cancel()


@pytest.mark.anyio
async def test_navigate_missing_url_raises_validation_error(anyio_backend: str, tmp_path: Path) -> None:
    """Calling frontprompt_navigate without url surfaces as MCP tool error."""
    from frontprompt import mcp_server as mcp_server_mod

    session_info = _fake_session_info(tmp_path)
    server_read, client_send, client_read, server_send = _make_stream_pair()

    async with anyio.create_task_group() as tg:
        tg.start_soon(
            mcp_server_mod.serve_mcp_stdio,
            mcp_server_mod.StaticSessionProvider(session_info),
            server_read,
            server_send,
        )

        async with ClientSession(client_read, client_send) as session:
            await session.initialize()
            result = await session.call_tool("frontprompt_navigate", {})
            assert result.isError

        tg.cancel_scope.cancel()


@pytest.mark.anyio
async def test_unknown_tool_name_propagates_as_error(anyio_backend: str, tmp_path: Path) -> None:
    """An unknown tool name results in an isError result."""
    from frontprompt import mcp_server as mcp_server_mod

    session_info = _fake_session_info(tmp_path)
    server_read, client_send, client_read, server_send = _make_stream_pair()

    async with anyio.create_task_group() as tg:
        tg.start_soon(
            mcp_server_mod.serve_mcp_stdio,
            mcp_server_mod.StaticSessionProvider(session_info),
            server_read,
            server_send,
        )

        async with ClientSession(client_read, client_send) as session:
            await session.initialize()
            result = await session.call_tool("frontprompt_doesnotexist", {})
            assert result.isError

        tg.cancel_scope.cancel()
