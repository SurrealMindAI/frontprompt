"""MCP tool surface tests for recording read-side tools (IPC 0.7.0).

Pure unit tests — no socket, no browser. Calls _build_tool_list() and
_build_ipc_request() directly to verify the new tools + dispatch table.
"""

from __future__ import annotations

import pytest

from frontprompt.ipc.protocol import GetRecordingRequest, GetRecordingsRequest
from frontprompt.mcp_server import _build_ipc_request, _build_tool_list


# ---------------------------------------------------------------------------
# Tool list presence tests
# ---------------------------------------------------------------------------


def test_list_recordings_tool_in_list() -> None:
    names = {t.name for t in _build_tool_list()}
    assert "frontprompt_list_recordings" in names


def test_get_recording_tool_in_list() -> None:
    names = {t.name for t in _build_tool_list()}
    assert "frontprompt_get_recording" in names


def test_get_recording_tool_has_recording_id_in_schema() -> None:
    tools = {t.name: t for t in _build_tool_list()}
    schema = tools["frontprompt_get_recording"].inputSchema
    assert "recording_id" in schema.get("properties", {})
    assert "recording_id" in schema.get("required", [])


def test_get_recording_tool_has_additional_properties_false() -> None:
    tools = {t.name: t for t in _build_tool_list()}
    schema = tools["frontprompt_get_recording"].inputSchema
    assert schema.get("additionalProperties") is False


def test_list_recordings_tool_has_no_required_args() -> None:
    tools = {t.name: t for t in _build_tool_list()}
    schema = tools["frontprompt_list_recordings"].inputSchema
    assert schema.get("additionalProperties") is False
    assert schema.get("required", []) == []


def test_list_recordings_description_mentions_recording_meta() -> None:
    tools = {t.name: t for t in _build_tool_list()}
    desc = tools["frontprompt_list_recordings"].description.lower()
    assert "recordingmeta" in desc or "recording" in desc


def test_get_recording_description_mentions_entries() -> None:
    tools = {t.name: t for t in _build_tool_list()}
    desc = tools["frontprompt_get_recording"].description.lower()
    assert "entries" in desc or "timeline" in desc


# ---------------------------------------------------------------------------
# Tool count — bumped from 29 to 31
# ---------------------------------------------------------------------------


def test_tool_list_has_31_tools() -> None:
    """After adding frontprompt_list_recordings + frontprompt_get_recording, count is 31."""
    tools = _build_tool_list()
    assert len(tools) == 31


# ---------------------------------------------------------------------------
# _build_ipc_request dispatch table tests
# ---------------------------------------------------------------------------


def test_build_ipc_request_list_recordings() -> None:
    req = _build_ipc_request("frontprompt_list_recordings", {})
    assert isinstance(req, GetRecordingsRequest)


def test_build_ipc_request_get_recording() -> None:
    req = _build_ipc_request("frontprompt_get_recording", {"recording_id": "abc"})
    assert isinstance(req, GetRecordingRequest)
    assert req.recording_id == "abc"


def test_build_ipc_request_get_recording_missing_id_raises() -> None:
    with pytest.raises(ValueError):
        _build_ipc_request("frontprompt_get_recording", {})


def test_build_ipc_request_get_recording_empty_id_raises() -> None:
    with pytest.raises(ValueError):
        _build_ipc_request("frontprompt_get_recording", {"recording_id": ""})
