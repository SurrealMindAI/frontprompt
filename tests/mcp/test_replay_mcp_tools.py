"""MCP tool surface tests for replay write-side tools (IPC 0.8.0, sub-plan 05).

Pure unit tests — no socket, no browser. Calls _build_tool_list() and
_build_ipc_request() directly to verify the new tools + dispatch table.

Five new tools added:
  frontprompt_start_recording
  frontprompt_stop_recording
  frontprompt_run_replay
  frontprompt_get_replay_report
  frontprompt_add_assertion
"""

from __future__ import annotations

import pytest

from frontprompt.ipc.protocol import (
    AddAssertionRequest,
    GetReplayReportRequest,
    RunReplayRequest,
    StartRecordingRequest,
    StopRecordingRequest,
)
from frontprompt.mcp_server import _build_ipc_request, _build_tool_list


# ---------------------------------------------------------------------------
# Tool list presence tests
# ---------------------------------------------------------------------------


def test_start_recording_tool_in_list() -> None:
    names = {t.name for t in _build_tool_list()}
    assert "frontprompt_start_recording" in names


def test_stop_recording_tool_in_list() -> None:
    names = {t.name for t in _build_tool_list()}
    assert "frontprompt_stop_recording" in names


def test_stop_recording_has_required_recording_id() -> None:
    tools = {t.name: t for t in _build_tool_list()}
    schema = tools["frontprompt_stop_recording"].inputSchema
    assert "recording_id" in schema.get("properties", {})
    assert "recording_id" in schema.get("required", [])


def test_run_replay_tool_in_list() -> None:
    names = {t.name for t in _build_tool_list()}
    assert "frontprompt_run_replay" in names


def test_run_replay_has_recording_id_field() -> None:
    tools = {t.name: t for t in _build_tool_list()}
    schema = tools["frontprompt_run_replay"].inputSchema
    assert "recording_id" in schema.get("properties", {})
    assert "recording_id" in schema.get("required", [])


def test_run_replay_has_parameters_field() -> None:
    tools = {t.name: t for t in _build_tool_list()}
    schema = tools["frontprompt_run_replay"].inputSchema
    assert "parameters" in schema.get("properties", {})


def test_run_replay_has_real_time_field() -> None:
    tools = {t.name: t for t in _build_tool_list()}
    schema = tools["frontprompt_run_replay"].inputSchema
    assert "real_time" in schema.get("properties", {})


def test_run_replay_has_dry_run_field() -> None:
    tools = {t.name: t for t in _build_tool_list()}
    schema = tools["frontprompt_run_replay"].inputSchema
    assert "dry_run" in schema.get("properties", {})


def test_get_replay_report_tool_in_list() -> None:
    names = {t.name for t in _build_tool_list()}
    assert "frontprompt_get_replay_report" in names


def test_get_replay_report_has_required_replay_id() -> None:
    tools = {t.name: t for t in _build_tool_list()}
    schema = tools["frontprompt_get_replay_report"].inputSchema
    assert "replay_id" in schema.get("properties", {})
    assert "replay_id" in schema.get("required", [])


def test_add_assertion_tool_in_list() -> None:
    names = {t.name for t in _build_tool_list()}
    assert "frontprompt_add_assertion" in names


def test_add_assertion_has_required_fields() -> None:
    tools = {t.name: t for t in _build_tool_list()}
    schema = tools["frontprompt_add_assertion"].inputSchema
    required = schema.get("required", [])
    for field in ("recording_id", "assertion_type", "target", "target_kind", "comparator"):
        assert field in schema.get("properties", {}), f"missing property: {field}"
        assert field in required, f"missing required: {field}"


# ---------------------------------------------------------------------------
# Tool count — bumped from 31 to 36
# ---------------------------------------------------------------------------


def test_tool_list_has_36_tools() -> None:
    """After adding 5 replay write-side tools, count rises from 31 to 36."""
    tools = _build_tool_list()
    assert len(tools) == 36


# ---------------------------------------------------------------------------
# _build_ipc_request dispatch table tests
# ---------------------------------------------------------------------------


def test_build_ipc_request_start_recording_minimal() -> None:
    req = _build_ipc_request("frontprompt_start_recording", {"name": "My Recording"})
    assert isinstance(req, StartRecordingRequest)
    assert req.name == "My Recording"


def test_build_ipc_request_start_recording_defaults() -> None:
    req = _build_ipc_request("frontprompt_start_recording", {})
    assert isinstance(req, StartRecordingRequest)
    assert req.name == "New Recording"


def test_build_ipc_request_stop_recording() -> None:
    req = _build_ipc_request("frontprompt_stop_recording", {"recording_id": "abc"})
    assert isinstance(req, StopRecordingRequest)
    assert req.recording_id == "abc"


def test_build_ipc_request_stop_recording_missing_id_raises() -> None:
    with pytest.raises(ValueError):
        _build_ipc_request("frontprompt_stop_recording", {})


def test_build_ipc_request_stop_recording_empty_id_raises() -> None:
    with pytest.raises(ValueError):
        _build_ipc_request("frontprompt_stop_recording", {"recording_id": ""})


def test_build_ipc_request_run_replay_minimal() -> None:
    req = _build_ipc_request("frontprompt_run_replay", {"recording_id": "x", "parameters": {}})
    assert isinstance(req, RunReplayRequest)
    assert req.recording_id == "x"
    assert req.parameters == {}
    assert req.dry_run is False
    assert req.real_time is False


def test_build_ipc_request_run_replay_with_dry_run() -> None:
    req = _build_ipc_request(
        "frontprompt_run_replay",
        {"recording_id": "x", "parameters": {"key": "val"}, "dry_run": True},
    )
    assert isinstance(req, RunReplayRequest)
    assert req.parameters == {"key": "val"}
    assert req.dry_run is True


def test_build_ipc_request_run_replay_missing_recording_id_raises() -> None:
    with pytest.raises(ValueError):
        _build_ipc_request("frontprompt_run_replay", {"parameters": {}})


def test_build_ipc_request_get_replay_report() -> None:
    req = _build_ipc_request("frontprompt_get_replay_report", {"replay_id": "r1"})
    assert isinstance(req, GetReplayReportRequest)
    assert req.replay_id == "r1"


def test_build_ipc_request_get_replay_report_missing_id_raises() -> None:
    with pytest.raises(ValueError):
        _build_ipc_request("frontprompt_get_replay_report", {})


def test_build_ipc_request_add_assertion_minimal() -> None:
    req = _build_ipc_request(
        "frontprompt_add_assertion",
        {
            "recording_id": "x",
            "assertion_type": "selector_exists",
            "target": "h1",
            "target_kind": "selector",
            "expected": None,
            "comparator": "none",
            "description": "H1 exists",
        },
    )
    assert isinstance(req, AddAssertionRequest)
    assert req.recording_id == "x"
    assert req.assertion_type == "selector_exists"
    assert req.target == "h1"
    assert req.target_kind == "selector"
    assert req.expected is None
    assert req.comparator == "none"
    assert req.description == "H1 exists"


def test_build_ipc_request_add_assertion_missing_required_raises() -> None:
    with pytest.raises((ValueError, KeyError)):
        _build_ipc_request(
            "frontprompt_add_assertion",
            {
                "assertion_type": "selector_exists",
                # recording_id missing
            },
        )
