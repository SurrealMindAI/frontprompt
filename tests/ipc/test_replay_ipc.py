"""IPC protocol tests for replay write-side requests (sub-plan 02 — replay-bundle).

Covers the 6 new ReplayIpcWriteRequests from contracts.md:
  - StartRecordingRequest
  - StopRecordingRequest
  - RunReplayRequest
  - GetReplayReportRequest
  - ListReplayReportsRequest
  - AddAssertionRequest

IPC schema version bump 0.7.0 → 0.8.0 verified here.
IpcRequest discriminated union routing + regression guard.
"""

from __future__ import annotations

import pytest
from pydantic import TypeAdapter, ValidationError

from frontprompt.ipc.protocol import IpcRequest


# ---------------------------------------------------------------------------
# Schema version bump
# ---------------------------------------------------------------------------


def test_ipc_schema_version_bumped_to_0_8_0() -> None:
    """IPC_SCHEMA_VERSION is 0.8.0 after sub-plan 02 replay-bundle."""
    from frontprompt.ipc.protocol import IPC_SCHEMA_VERSION

    assert IPC_SCHEMA_VERSION == "0.8.0"


# ---------------------------------------------------------------------------
# StartRecordingRequest
# ---------------------------------------------------------------------------


def test_start_recording_request_default_fields() -> None:
    """StartRecordingRequest round-trip with default name and description."""
    from frontprompt.ipc.protocol import StartRecordingRequest

    req = StartRecordingRequest()
    assert req.kind == "start_recording"
    assert req.name == "New Recording"
    assert req.description == ""


def test_start_recording_request_custom_fields() -> None:
    """StartRecordingRequest with custom name and description."""
    from frontprompt.ipc.protocol import StartRecordingRequest

    req = StartRecordingRequest(name="Login Flow", description="Tests auth")
    assert req.name == "Login Flow"
    assert req.description == "Tests auth"


def test_start_recording_routes_via_ipc_union() -> None:
    """IpcRequest discriminated union routes start_recording correctly."""
    from frontprompt.ipc.protocol import StartRecordingRequest

    adapter: TypeAdapter[IpcRequest] = TypeAdapter(IpcRequest)
    parsed = adapter.validate_python({"kind": "start_recording"})
    assert isinstance(parsed, StartRecordingRequest)


# ---------------------------------------------------------------------------
# StopRecordingRequest
# ---------------------------------------------------------------------------


def test_stop_recording_request_requires_recording_id() -> None:
    """StopRecordingRequest requires a non-empty recording_id."""
    from frontprompt.ipc.protocol import StopRecordingRequest

    req = StopRecordingRequest(recording_id="rec-uuid-1")
    assert req.kind == "stop_recording"
    assert req.recording_id == "rec-uuid-1"
    # empty string should fail
    with pytest.raises(ValidationError):
        StopRecordingRequest(recording_id="")


def test_stop_recording_routes_via_ipc_union() -> None:
    """IpcRequest union routes stop_recording correctly."""
    from frontprompt.ipc.protocol import StopRecordingRequest

    adapter: TypeAdapter[IpcRequest] = TypeAdapter(IpcRequest)
    parsed = adapter.validate_python({"kind": "stop_recording", "recording_id": "rec-1"})
    assert isinstance(parsed, StopRecordingRequest)
    assert parsed.recording_id == "rec-1"


# ---------------------------------------------------------------------------
# RunReplayRequest
# ---------------------------------------------------------------------------


def test_run_replay_request_defaults() -> None:
    """RunReplayRequest with recording_id, empty parameters, real_time=False, dry_run=False."""
    from frontprompt.ipc.protocol import RunReplayRequest

    req = RunReplayRequest(recording_id="rec-1", parameters={}, real_time=False, dry_run=False)
    assert req.kind == "run_replay"
    assert req.recording_id == "rec-1"
    assert req.parameters == {}
    assert req.real_time is False
    assert req.dry_run is False


def test_run_replay_request_with_parameters() -> None:
    """RunReplayRequest with non-empty parameters dict."""
    from frontprompt.ipc.protocol import RunReplayRequest

    req = RunReplayRequest(
        recording_id="rec-1",
        parameters={"login_url": "https://example.com/login", "username": "testuser"},
        real_time=True,
        dry_run=False,
    )
    assert req.parameters == {"login_url": "https://example.com/login", "username": "testuser"}
    assert req.real_time is True


def test_run_replay_routes_via_ipc_union() -> None:
    """IpcRequest union routes run_replay correctly."""
    from frontprompt.ipc.protocol import RunReplayRequest

    adapter: TypeAdapter[IpcRequest] = TypeAdapter(IpcRequest)
    parsed = adapter.validate_python({"kind": "run_replay", "recording_id": "rec-1"})
    assert isinstance(parsed, RunReplayRequest)


def test_run_replay_request_requires_recording_id() -> None:
    """RunReplayRequest requires a non-empty recording_id."""
    from frontprompt.ipc.protocol import RunReplayRequest

    with pytest.raises(ValidationError):
        RunReplayRequest(recording_id="")


# ---------------------------------------------------------------------------
# GetReplayReportRequest
# ---------------------------------------------------------------------------


def test_get_replay_report_request_requires_replay_id() -> None:
    """GetReplayReportRequest requires a non-empty replay_id."""
    from frontprompt.ipc.protocol import GetReplayReportRequest

    req = GetReplayReportRequest(replay_id="rpl-uuid-1")
    assert req.kind == "get_replay_report"
    assert req.replay_id == "rpl-uuid-1"
    with pytest.raises(ValidationError):
        GetReplayReportRequest(replay_id="")


def test_get_replay_report_routes_via_ipc_union() -> None:
    """IpcRequest union routes get_replay_report correctly."""
    from frontprompt.ipc.protocol import GetReplayReportRequest

    adapter: TypeAdapter[IpcRequest] = TypeAdapter(IpcRequest)
    parsed = adapter.validate_python({"kind": "get_replay_report", "replay_id": "rpl-1"})
    assert isinstance(parsed, GetReplayReportRequest)
    assert parsed.replay_id == "rpl-1"


# ---------------------------------------------------------------------------
# ListReplayReportsRequest
# ---------------------------------------------------------------------------


def test_list_replay_reports_request_with_recording_id_none() -> None:
    """ListReplayReportsRequest with recording_id=None (all sessions)."""
    from frontprompt.ipc.protocol import ListReplayReportsRequest

    req = ListReplayReportsRequest(recording_id=None)
    assert req.kind == "list_replay_reports"
    assert req.recording_id is None


def test_list_replay_reports_request_with_recording_id() -> None:
    """ListReplayReportsRequest with a specific recording_id."""
    from frontprompt.ipc.protocol import ListReplayReportsRequest

    req = ListReplayReportsRequest(recording_id="rec-1")
    assert req.recording_id == "rec-1"


def test_list_replay_reports_routes_via_ipc_union() -> None:
    """IpcRequest union routes list_replay_reports correctly."""
    from frontprompt.ipc.protocol import ListReplayReportsRequest

    adapter: TypeAdapter[IpcRequest] = TypeAdapter(IpcRequest)
    parsed = adapter.validate_python({"kind": "list_replay_reports"})
    assert isinstance(parsed, ListReplayReportsRequest)
    assert parsed.recording_id is None


# ---------------------------------------------------------------------------
# AddAssertionRequest
# ---------------------------------------------------------------------------


def test_add_assertion_request_all_required_fields() -> None:
    """AddAssertionRequest with all required fields."""
    from frontprompt.ipc.protocol import AddAssertionRequest

    req = AddAssertionRequest(
        recording_id="rec-1",
        assertion_type="selector_exists",
        target="button#submit",
        target_kind="selector",
        expected=None,
        comparator="none",
        description="Submit button exists",
        insert_after_seq=None,
    )
    assert req.kind == "add_assertion"
    assert req.recording_id == "rec-1"
    assert req.assertion_type == "selector_exists"
    assert req.target == "button#submit"
    assert req.target_kind == "selector"
    assert req.expected is None
    assert req.comparator == "none"
    assert req.description == "Submit button exists"
    assert req.insert_after_seq is None


def test_add_assertion_request_routes_via_ipc_union() -> None:
    """IpcRequest union routes add_assertion correctly."""
    from frontprompt.ipc.protocol import AddAssertionRequest

    adapter: TypeAdapter[IpcRequest] = TypeAdapter(IpcRequest)
    parsed = adapter.validate_python({
        "kind": "add_assertion",
        "recording_id": "rec-1",
        "assertion_type": "text_equals",
        "target": "h1",
        "target_kind": "selector",
        "expected": "Hello",
        "comparator": "equals",
        "description": "Title check",
        "insert_after_seq": None,
    })
    assert isinstance(parsed, AddAssertionRequest)
    assert parsed.assertion_type == "text_equals"


# ---------------------------------------------------------------------------
# ReplayReportMeta
# ---------------------------------------------------------------------------


def test_replay_report_meta_fields() -> None:
    """ReplayReportMeta has all expected lightweight summary fields."""
    from frontprompt.ipc.protocol import ReplayReportMeta

    meta = ReplayReportMeta(
        replay_id="rpl-1",
        recording_id="rec-1",
        status="completed",
        started_at_ms=1_700_000_000_000,
        ended_at_ms=1_700_000_060_000,
        step_count=10,
        passed_assertions=3,
        failed_assertions=0,
    )
    assert meta.replay_id == "rpl-1"
    assert meta.status == "completed"
    assert meta.step_count == 10
    assert meta.passed_assertions == 3
    assert meta.failed_assertions == 0
    assert meta.ended_at_ms == 1_700_000_060_000


def test_replay_report_meta_ended_at_ms_optional() -> None:
    """ReplayReportMeta.ended_at_ms is optional (None for aborted replays)."""
    from frontprompt.ipc.protocol import ReplayReportMeta

    meta = ReplayReportMeta(
        replay_id="rpl-1",
        recording_id="rec-1",
        status="aborted",
        started_at_ms=1_700_000_000_000,
        ended_at_ms=None,
        step_count=3,
        passed_assertions=1,
        failed_assertions=1,
    )
    assert meta.ended_at_ms is None
    assert meta.status == "aborted"


# ---------------------------------------------------------------------------
# IpcRequest union — regression guard
# ---------------------------------------------------------------------------


def test_existing_ipc_variants_still_route() -> None:
    """Regression guard: existing IpcRequest kinds are unaffected by the new additions."""
    from frontprompt.ipc.protocol import (
        GetRecordingRequest,
        GetRecordingsRequest,
        PingRequest,
    )

    adapter: TypeAdapter[IpcRequest] = TypeAdapter(IpcRequest)
    cases = [
        ({"kind": "ping"}, PingRequest),
        ({"kind": "get_recordings"}, GetRecordingsRequest),
        ({"kind": "get_recording", "recording_id": "r1"}, GetRecordingRequest),
    ]
    for payload, expected_cls in cases:
        parsed = adapter.validate_python(payload)
        assert isinstance(parsed, expected_cls), f"Expected {expected_cls.__name__}, got {type(parsed).__name__}"
