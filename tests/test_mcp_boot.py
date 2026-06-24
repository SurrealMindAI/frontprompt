"""MCP server boot tests — in-process via anyio MemoryObjectStreams.

Per the per-daemon browser-session isolation model, the server is bound to a concrete browser-session (SessionMetadata)
at boot. These tests inject paired in-process streams instead of real stdio,
and verify the boot sequence + list_tools surface.
"""

from __future__ import annotations

import json
from pathlib import Path

import anyio
import pytest
from anyio.streams.memory import MemoryObjectReceiveStream, MemoryObjectSendStream
from mcp import ClientSession
from mcp.shared.message import SessionMessage

from frontprompt.ipc.session import SessionMetadata


def _fake_session_info(tmp_path: Path) -> SessionMetadata:
    return SessionMetadata(
        session_id="20260523T143045-cafebabe",
        pid=12345,
        url="about:blank",
        started_at_iso="2026-05-23T14:30:45+00:00",
        socket_path=str(tmp_path / "show.sock"),
    )


def _make_server_streams() -> tuple[
    MemoryObjectSendStream[SessionMessage],
    MemoryObjectReceiveStream[SessionMessage | Exception],
    MemoryObjectSendStream[SessionMessage],
    MemoryObjectReceiveStream[SessionMessage | Exception],
]:
    """Create paired in-process MemoryObjectStreams for client↔server communication."""
    client_send, server_read = anyio.create_memory_object_stream(16)  # type: ignore[assignment]
    server_send, client_read = anyio.create_memory_object_stream(16)  # type: ignore[assignment]
    return client_send, server_read, server_send, client_read


@pytest.mark.anyio
async def test_mcp_boot_advertises_full_tool_surface(anyio_backend: str, tmp_path: Path) -> None:
    """Boot the MCP-Server bound to a fake SessionMetadata and assert tools/list surface."""
    from frontprompt.mcp_server import StaticSessionProvider, serve_mcp_stdio

    session_info = _fake_session_info(tmp_path)
    provider = StaticSessionProvider(session_info)

    client_send, server_read, server_send, client_read = _make_server_streams()

    async with anyio.create_task_group() as tg:

        async def run_server() -> None:
            await serve_mcp_stdio(
                provider,
                read_stream=server_read,  # type: ignore[arg-type]
                write_stream=server_send,  # type: ignore[arg-type]
            )

        tg.start_soon(run_server)

        async with ClientSession(client_read, client_send) as session:  # type: ignore[arg-type]
            await session.initialize()
            result = await session.list_tools()
            names = {tool.name for tool in result.tools}
            assert names == {
                "fp_status",
                "frontprompt_ping",
                "frontprompt_get_session_info",
                "frontprompt_get_state_summary",
                "frontprompt_get_comments",
                "frontprompt_get_snapshot",
                "frontprompt_get_picks",
                "frontprompt_get_pick",
                "frontprompt_navigate",
                # Scout tools v0.3.0 (surviving 6 — 5 deprecated element-readers removed in IPC 0.6.0)
                "frontprompt_pick_by_selector",
                "frontprompt_pick_by_text",
                "frontprompt_screenshot_element",
                "frontprompt_get_page_info",
                "frontprompt_screenshot_page",
                "frontprompt_scroll_to",
                # Refinement tools v0.4.0
                "frontprompt_get_page_outline",
                "frontprompt_get_page_html",
                "frontprompt_pick_from_ref",
                "frontprompt_find_one",
                "frontprompt_find_first",
                "frontprompt_find_similar",
                "frontprompt_find_by_regex",
                "frontprompt_get_element_context",
                "frontprompt_pick_path",
                "frontprompt_relocate_picks",
                "frontprompt_inspect_elements",
                "frontprompt_eval_js",
                "frontprompt_dom_patch",
                "frontprompt_pick_by_xpath",
            }, f"unexpected tool surface: {names}"

        tg.cancel_scope.cancel()


@pytest.mark.anyio
async def test_fp_status_call_returns_structured_response(anyio_backend: str, tmp_path: Path) -> None:
    """fp_status tool returns a JSON object with the required diagnostic keys."""
    from frontprompt.mcp_server import StaticSessionProvider, serve_mcp_stdio

    session_info = _fake_session_info(tmp_path)
    provider = StaticSessionProvider(session_info)

    client_send, server_read, server_send, client_read = _make_server_streams()

    async with anyio.create_task_group() as tg:

        async def run_server() -> None:
            await serve_mcp_stdio(
                provider,
                read_stream=server_read,  # type: ignore[arg-type]
                write_stream=server_send,  # type: ignore[arg-type]
            )

        tg.start_soon(run_server)

        async with ClientSession(client_read, client_send) as session:  # type: ignore[arg-type]
            await session.initialize()
            result = await session.call_tool("fp_status", {})
            assert len(result.content) >= 1
            first = result.content[0]
            assert first.type == "text"
            data = json.loads(first.text)  # type: ignore[union-attr]
            assert isinstance(data, dict)
            assert "schema_version" in data
            assert "phase" in data
            assert "capabilities_available" in data
            assert "capabilities_deferred" in data

        tg.cancel_scope.cancel()


@pytest.mark.anyio
async def test_fp_status_schema_version_matches_bridge_constant(anyio_backend: str, tmp_path: Path) -> None:
    """fp_status returns schema_version equal to SCHEMA_VERSION from bridge.messages."""
    from frontprompt.bridge.messages import SCHEMA_VERSION
    from frontprompt.mcp_server import StaticSessionProvider, serve_mcp_stdio

    session_info = _fake_session_info(tmp_path)
    provider = StaticSessionProvider(session_info)

    client_send, server_read, server_send, client_read = _make_server_streams()

    async with anyio.create_task_group() as tg:

        async def run_server() -> None:
            await serve_mcp_stdio(
                provider,
                read_stream=server_read,  # type: ignore[arg-type]
                write_stream=server_send,  # type: ignore[arg-type]
            )

        tg.start_soon(run_server)

        async with ClientSession(client_read, client_send) as session:  # type: ignore[arg-type]
            await session.initialize()
            result = await session.call_tool("fp_status", {})
            first = result.content[0]
            data = json.loads(first.text)  # type: ignore[union-attr]
            assert data["schema_version"] == SCHEMA_VERSION

        tg.cancel_scope.cancel()


def test_diagnostics_registry_accepts_custom_provider() -> None:
    """DiagnosticsRegistry.register() + collect_all() includes the custom provider's data."""
    from frontprompt.mcp_server import _DIAGNOSTICS

    class _CustomProvider:
        def collect(self) -> dict[str, object]:
            return {"custom_key": "custom_value"}

    # Register a fresh instance and verify collect_all includes it
    _DIAGNOSTICS.register(_CustomProvider())
    result = _DIAGNOSTICS.collect_all()
    assert result["custom_key"] == "custom_value"
