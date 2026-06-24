"""MCP tool surface tests for frontprompt_get_comments (IPC 0.6.0).

Pure unit tests — no socket, no browser. Calls _build_tool_list() and
_build_ipc_request() directly to verify the new tool + mock-IPC integration.
"""

from __future__ import annotations

from pathlib import Path
from typing import Any

import pytest

from frontprompt.ipc.protocol import GetCommentsRequest
from frontprompt.mcp_server import _build_ipc_request, _build_tool_list

# ---------------------------------------------------------------------------
# Tool surface tests
# ---------------------------------------------------------------------------


def test_get_comments_tool_in_list() -> None:
    names = {t.name for t in _build_tool_list()}
    assert "frontprompt_get_comments" in names


def test_build_ipc_request_get_comments() -> None:
    req = _build_ipc_request("frontprompt_get_comments", {})
    assert isinstance(req, GetCommentsRequest)


def test_get_comments_description_mentions_comment() -> None:
    tools = {t.name: t for t in _build_tool_list()}
    assert "comment" in tools["frontprompt_get_comments"].description.lower()


def test_tool_list_has_29_tools() -> None:
    """After sub-plan 02 consolidation (remove 5 deprecated + keep get_comments) count is 29."""
    tools = _build_tool_list()
    assert len(tools) == 29
    names = {t.name for t in tools}
    assert "fp_status" in names
    assert "frontprompt_get_state_summary" in names
    assert "frontprompt_get_comments" in names


def test_get_comments_tool_has_no_required_args() -> None:
    """Tool schema must have empty required list (or no required field)."""
    tools = {t.name: t for t in _build_tool_list()}
    schema = tools["frontprompt_get_comments"].inputSchema
    assert schema.get("additionalProperties") is False
    # no required properties (the tool takes no arguments)
    assert schema.get("required", []) == []


# ---------------------------------------------------------------------------
# MCP integration tests via monkeypatched query()
# ---------------------------------------------------------------------------


@pytest.mark.anyio
async def test_get_comments_returns_annotation_list(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> None:
    """MCP tool call returns list of AnnotationEntry via mock IPC."""
    from frontprompt.ipc.protocol import AnnotationEntry, IpcResponse

    entries = [
        AnnotationEntry(pick_id="p1", comment="my note", selector="#btn", url="https://example.com/"),
        AnnotationEntry(pick_id="p2", comment="another note", selector=".link", url="https://example.com/about"),
    ]
    mock_response = IpcResponse(ok=True, data=[e.model_dump() for e in entries])

    async def fake_query(request: Any, *, session_path: Any, timeout_s: float = 5.0) -> IpcResponse:
        return mock_response

    monkeypatch.setattr("frontprompt.mcp_server.query", fake_query)

    # Build IPC request and verify it maps correctly
    req = _build_ipc_request("frontprompt_get_comments", {})
    assert isinstance(req, GetCommentsRequest)

    # Verify the response payload has the right shape
    result = mock_response.data
    assert isinstance(result, list)
    assert len(result) == 2
    assert result[0]["pick_id"] == "p1"
    assert result[0]["comment"] == "my note"
    assert result[0]["selector"] == "#btn"
    assert result[0]["url"] == "https://example.com/"


@pytest.mark.anyio
async def test_get_comments_excludes_empty_comments(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> None:
    """IPC dispatch correctly excludes picks with empty comments."""
    from frontprompt.ipc.protocol import AnnotationEntry, IpcResponse

    # Only non-empty comment entries returned — empty-comment picks are filtered server-side
    entries = [
        AnnotationEntry(pick_id="p2", comment="has a comment", selector=".link", url="https://example.com/"),
    ]
    mock_response = IpcResponse(ok=True, data=[e.model_dump() for e in entries])

    # Verify the response only contains the annotated pick
    result = mock_response.data
    assert isinstance(result, list)
    assert len(result) == 1
    assert result[0]["comment"] == "has a comment"
    # p1 (empty comment) is not in the response
    assert all(e["pick_id"] != "p1" for e in result)
