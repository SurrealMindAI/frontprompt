"""IPC socket-server dispatch tests for replay write-side requests (sub-plan 04).

Covers the 6 new write-side IPC routes added in socket_server._dispatch:
  - StartRecordingRequest → state_manager.start_recording + response with recording_id/name/started_at_ms
  - StopRecordingRequest (known) → state_manager.stop_recording + ok=True
  - StopRecordingRequest (unknown) → ok=False, error "recording not found: <id>"
  - AddAssertionRequest → state_manager.add_assertion_to_timeline + response with assertion_id/seq
  - RunReplayRequest (known, dry_run=False, no live browser) → ok=False "replay_unavailable" (COL-6 guard)
  - RunReplayRequest (known, dry_run=True) → replay runs in dry_run mode, full ReplayReport returned
  - RunReplayRequest (unknown) → ok=False "recording not found: <id>"
  - GetReplayReportRequest (known) → full ReplayReport JSON
  - GetReplayReportRequest (unknown) → ok=False "replay report not found: <id>"
  - ListReplayReportsRequest (recording_id=None) → list of all reports
  - ListReplayReportsRequest (recording_id=<id>) → filtered list
"""

from __future__ import annotations

import stat as _stat
from pathlib import Path

import anyio
import pytest

from frontprompt.ipc import query, run_socket_server
from frontprompt.ipc.protocol import (
    AddAssertionRequest,
    GetReplayReportRequest,
    ListReplayReportsRequest,
    RunReplayRequest,
    StartRecordingRequest,
    StopRecordingRequest,
)
from frontprompt.state import StateManager
from tests.ipc.fakes import FakePageAnalyzer, FakePageController


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


async def _wait_for_socket(path: Path, attempts: int = 50, delay: float = 0.02) -> None:
    for _ in range(attempts):
        try:
            mode = path.stat().st_mode
            if _stat.S_ISSOCK(mode):
                return
        except OSError:
            pass
        await anyio.sleep(delay)
    raise RuntimeError(f"unix-socket {path} not created within {attempts * delay}s")


def _make_assertion_payload(
    assertion_id: str = "test-assert-uuid",
) -> dict:
    return {
        "assertion_id": assertion_id,
        "assertion_type": "selector_exists",
        "target": "button#submit",
        "target_kind": "selector",
        "expected": None,
        "comparator": "none",
        "description": "Submit button exists",
    }


# ---------------------------------------------------------------------------
# StartRecordingRequest
# ---------------------------------------------------------------------------


@pytest.mark.anyio
async def test_start_recording_dispatch_creates_recording(socket_path: Path) -> None:
    """StartRecordingRequest → state_manager.start_recording called; response has recording_id/name/started_at_ms."""
    sm = StateManager(session_id="test-session")
    fake_controller = FakePageController()
    fake_analyzer = FakePageAnalyzer()

    async with anyio.create_task_group() as tg:
        tg.start_soon(run_socket_server, sm, socket_path, fake_controller, None, fake_analyzer)
        await _wait_for_socket(socket_path)

        response = await query(socket_path, StartRecordingRequest(name="Login Flow", description="Tests auth"))
        assert response.ok is True
        data = response.data
        assert isinstance(data, dict)
        assert "recording_id" in data
        assert data["name"] == "Login Flow"
        assert "started_at_ms" in data
        assert isinstance(data["started_at_ms"], int)

        # Verify recording was created in state manager
        metas = sm.list_recordings_meta()
        assert len(metas) == 1
        assert metas[0].name == "Login Flow"
        assert metas[0].status == "active"

        tg.cancel_scope.cancel()


@pytest.mark.anyio
async def test_start_recording_dispatch_default_name(socket_path: Path) -> None:
    """StartRecordingRequest with defaults creates recording with default name."""
    sm = StateManager(session_id="test-session")
    fake_controller = FakePageController()
    fake_analyzer = FakePageAnalyzer()

    async with anyio.create_task_group() as tg:
        tg.start_soon(run_socket_server, sm, socket_path, fake_controller, None, fake_analyzer)
        await _wait_for_socket(socket_path)

        response = await query(socket_path, StartRecordingRequest())
        assert response.ok is True
        assert response.data["name"] == "New Recording"

        tg.cancel_scope.cancel()


# ---------------------------------------------------------------------------
# StopRecordingRequest
# ---------------------------------------------------------------------------


@pytest.mark.anyio
async def test_stop_recording_dispatch_known_id(socket_path: Path) -> None:
    """StopRecordingRequest (known_id) → state_manager.stop_recording called; response ok=True."""
    sm = StateManager(session_id="test-session")
    await sm.start_recording(name="Active Rec", description="")
    metas = sm.list_recordings_meta()
    recording_id = metas[0].recording_id

    fake_controller = FakePageController()
    fake_analyzer = FakePageAnalyzer()

    async with anyio.create_task_group() as tg:
        tg.start_soon(run_socket_server, sm, socket_path, fake_controller, None, fake_analyzer)
        await _wait_for_socket(socket_path)

        response = await query(socket_path, StopRecordingRequest(recording_id=recording_id))
        assert response.ok is True

        # Verify stopped in state
        updated_metas = sm.list_recordings_meta()
        assert updated_metas[0].status == "stopped"

        tg.cancel_scope.cancel()


@pytest.mark.anyio
async def test_stop_recording_dispatch_unknown_id(socket_path: Path) -> None:
    """StopRecordingRequest (unknown_id) → ok=False, error contains recording id."""
    sm = StateManager(session_id="test-session")
    fake_controller = FakePageController()
    fake_analyzer = FakePageAnalyzer()

    async with anyio.create_task_group() as tg:
        tg.start_soon(run_socket_server, sm, socket_path, fake_controller, None, fake_analyzer)
        await _wait_for_socket(socket_path)

        response = await query(socket_path, StopRecordingRequest(recording_id="nonexistent-id"))
        assert response.ok is False
        assert response.error is not None
        assert "nonexistent-id" in response.error
        assert "recording not found" in response.error

        tg.cancel_scope.cancel()


# ---------------------------------------------------------------------------
# AddAssertionRequest
# ---------------------------------------------------------------------------


@pytest.mark.anyio
async def test_add_assertion_dispatch_known_recording(socket_path: Path) -> None:
    """AddAssertionRequest (known recording) → adds assertion, response has assertion_id + seq."""
    sm = StateManager(session_id="test-session")
    await sm.start_recording(name="Test Rec", description="")
    metas = sm.list_recordings_meta()
    recording_id = metas[0].recording_id

    fake_controller = FakePageController()
    fake_analyzer = FakePageAnalyzer()

    async with anyio.create_task_group() as tg:
        tg.start_soon(run_socket_server, sm, socket_path, fake_controller, None, fake_analyzer)
        await _wait_for_socket(socket_path)

        response = await query(
            socket_path,
            AddAssertionRequest(
                recording_id=recording_id,
                assertion_type="selector_exists",
                target="button#submit",
                target_kind="selector",
                expected=None,
                comparator="none",
                description="Submit button exists",
                insert_after_seq=None,
            ),
        )
        assert response.ok is True
        data = response.data
        assert isinstance(data, dict)
        assert "assertion_id" in data
        assert "seq" in data
        assert data["seq"] == 0  # first entry

        # Verify assertion in state
        recording = sm.get_recording(recording_id)
        assert recording is not None
        assert len(recording.entries) == 1
        assert recording.entries[0].kind == "assertion"

        tg.cancel_scope.cancel()


@pytest.mark.anyio
async def test_add_assertion_dispatch_unknown_recording(socket_path: Path) -> None:
    """AddAssertionRequest (unknown recording) → ok=False, error contains recording id."""
    sm = StateManager(session_id="test-session")
    fake_controller = FakePageController()
    fake_analyzer = FakePageAnalyzer()

    async with anyio.create_task_group() as tg:
        tg.start_soon(run_socket_server, sm, socket_path, fake_controller, None, fake_analyzer)
        await _wait_for_socket(socket_path)

        response = await query(
            socket_path,
            AddAssertionRequest(
                recording_id="nonexistent-rec",
                assertion_type="selector_exists",
                target="h1",
                target_kind="selector",
                expected=None,
                comparator="none",
                description="",
                insert_after_seq=None,
            ),
        )
        assert response.ok is False
        assert response.error is not None
        assert "nonexistent-rec" in response.error

        tg.cancel_scope.cancel()


# ---------------------------------------------------------------------------
# RunReplayRequest — COL-6 NullPageController guard
# ---------------------------------------------------------------------------


@pytest.mark.anyio
async def test_run_replay_dispatch_no_live_browser_returns_unavailable(socket_path: Path) -> None:
    """RunReplayRequest (NullPageController, dry_run=False) → ok=False 'replay_unavailable'."""
    sm = StateManager(session_id="test-session")
    await sm.start_recording(name="Test Rec", description="")
    metas = sm.list_recordings_meta()
    recording_id = metas[0].recording_id

    # NullPageController is the default (no page_controller arg) — COL-6 guard
    fake_analyzer = FakePageAnalyzer()

    async with anyio.create_task_group() as tg:
        tg.start_soon(run_socket_server, sm, socket_path, None, None, fake_analyzer)
        await _wait_for_socket(socket_path)

        response = await query(
            socket_path,
            RunReplayRequest(recording_id=recording_id, parameters={}, real_time=False, dry_run=False),
        )
        assert response.ok is False
        assert response.error is not None
        assert "replay_unavailable" in response.error
        assert "no active browser session" in response.error

        tg.cancel_scope.cancel()


@pytest.mark.anyio
async def test_run_replay_dispatch_dry_run_bypasses_null_controller_guard(socket_path: Path) -> None:
    """RunReplayRequest (NullPageController, dry_run=True) → guard bypassed, dry_run report returned."""
    sm = StateManager(session_id="test-session")
    await sm.start_recording(name="Test Rec", description="")
    metas = sm.list_recordings_meta()
    recording_id = metas[0].recording_id

    # NullPageController is the default
    fake_analyzer = FakePageAnalyzer()

    async with anyio.create_task_group() as tg:
        tg.start_soon(run_socket_server, sm, socket_path, None, None, fake_analyzer)
        await _wait_for_socket(socket_path)

        response = await query(
            socket_path,
            RunReplayRequest(recording_id=recording_id, parameters={}, real_time=False, dry_run=True),
        )
        assert response.ok is True
        data = response.data
        assert isinstance(data, dict)
        assert "replay_id" in data
        assert data["recording_id"] == recording_id
        assert "status" in data
        assert "step_results" in data

        tg.cancel_scope.cancel()


@pytest.mark.anyio
async def test_run_replay_dispatch_unknown_recording(socket_path: Path) -> None:
    """RunReplayRequest (unknown recording_id) → ok=False 'recording not found'."""
    sm = StateManager(session_id="test-session")
    fake_analyzer = FakePageAnalyzer()

    async with anyio.create_task_group() as tg:
        tg.start_soon(run_socket_server, sm, socket_path, None, None, fake_analyzer)
        await _wait_for_socket(socket_path)

        response = await query(
            socket_path,
            RunReplayRequest(recording_id="nonexistent-rec", parameters={}, dry_run=True),
        )
        assert response.ok is False
        assert response.error is not None
        assert "nonexistent-rec" in response.error
        assert "recording not found" in response.error

        tg.cancel_scope.cancel()


@pytest.mark.anyio
async def test_run_replay_dispatch_with_live_controller(socket_path: Path) -> None:
    """RunReplayRequest (FakePageController, dry_run=False) → replay runs, report returned."""
    sm = StateManager(session_id="test-session")
    await sm.start_recording(name="Test Rec", description="")
    metas = sm.list_recordings_meta()
    recording_id = metas[0].recording_id

    fake_controller = FakePageController()
    fake_analyzer = FakePageAnalyzer()

    async with anyio.create_task_group() as tg:
        tg.start_soon(run_socket_server, sm, socket_path, fake_controller, None, fake_analyzer)
        await _wait_for_socket(socket_path)

        response = await query(
            socket_path,
            RunReplayRequest(recording_id=recording_id, parameters={}, real_time=False, dry_run=False),
        )
        assert response.ok is True
        data = response.data
        assert isinstance(data, dict)
        assert "replay_id" in data
        assert data["recording_id"] == recording_id
        assert "step_results" in data

        tg.cancel_scope.cancel()


# ---------------------------------------------------------------------------
# GetReplayReportRequest
# ---------------------------------------------------------------------------


@pytest.mark.anyio
async def test_get_replay_report_dispatch_known_id(socket_path: Path) -> None:
    """GetReplayReportRequest (known replay_id) → full ReplayReport JSON."""
    sm = StateManager(session_id="test-session")
    await sm.start_recording(name="Test Rec", description="")
    metas = sm.list_recordings_meta()
    recording_id = metas[0].recording_id

    fake_controller = FakePageController()
    fake_analyzer = FakePageAnalyzer()

    async with anyio.create_task_group() as tg:
        tg.start_soon(run_socket_server, sm, socket_path, fake_controller, None, fake_analyzer)
        await _wait_for_socket(socket_path)

        # Run a replay first to create a report
        run_resp = await query(
            socket_path,
            RunReplayRequest(recording_id=recording_id, parameters={}, dry_run=True),
        )
        assert run_resp.ok is True
        replay_id = run_resp.data["replay_id"]

        # Now retrieve it
        response = await query(socket_path, GetReplayReportRequest(replay_id=replay_id))
        assert response.ok is True
        data = response.data
        assert isinstance(data, dict)
        assert data["replay_id"] == replay_id
        assert data["recording_id"] == recording_id

        tg.cancel_scope.cancel()


@pytest.mark.anyio
async def test_get_replay_report_dispatch_unknown_id(socket_path: Path) -> None:
    """GetReplayReportRequest (unknown replay_id) → ok=False 'replay report not found'."""
    sm = StateManager(session_id="test-session")
    fake_controller = FakePageController()
    fake_analyzer = FakePageAnalyzer()

    async with anyio.create_task_group() as tg:
        tg.start_soon(run_socket_server, sm, socket_path, fake_controller, None, fake_analyzer)
        await _wait_for_socket(socket_path)

        response = await query(socket_path, GetReplayReportRequest(replay_id="nonexistent-replay-id"))
        assert response.ok is False
        assert response.error is not None
        assert "nonexistent-replay-id" in response.error
        assert "replay report not found" in response.error

        tg.cancel_scope.cancel()


# ---------------------------------------------------------------------------
# ListReplayReportsRequest
# ---------------------------------------------------------------------------


@pytest.mark.anyio
async def test_list_replay_reports_dispatch_all(socket_path: Path) -> None:
    """ListReplayReportsRequest (recording_id=None) → all reports for this session."""
    sm = StateManager(session_id="test-session")
    await sm.start_recording(name="Test Rec", description="")
    metas = sm.list_recordings_meta()
    recording_id = metas[0].recording_id

    fake_controller = FakePageController()
    fake_analyzer = FakePageAnalyzer()

    async with anyio.create_task_group() as tg:
        tg.start_soon(run_socket_server, sm, socket_path, fake_controller, None, fake_analyzer)
        await _wait_for_socket(socket_path)

        # Run a replay to generate a report
        await query(socket_path, RunReplayRequest(recording_id=recording_id, parameters={}, dry_run=True))

        # List all reports
        response = await query(socket_path, ListReplayReportsRequest(recording_id=None))
        assert response.ok is True
        data = response.data
        assert isinstance(data, list)
        assert len(data) == 1
        assert data[0]["recording_id"] == recording_id

        tg.cancel_scope.cancel()


@pytest.mark.anyio
async def test_list_replay_reports_dispatch_filtered_by_recording(socket_path: Path) -> None:
    """ListReplayReportsRequest (recording_id=<id>) → only reports for that recording."""
    sm = StateManager(session_id="test-session")
    await sm.start_recording(name="Rec A", description="")
    metas = sm.list_recordings_meta()
    recording_id_a = metas[0].recording_id

    fake_controller = FakePageController()
    fake_analyzer = FakePageAnalyzer()

    async with anyio.create_task_group() as tg:
        tg.start_soon(run_socket_server, sm, socket_path, fake_controller, None, fake_analyzer)
        await _wait_for_socket(socket_path)

        # Run a replay for recording_id_a
        await query(socket_path, RunReplayRequest(recording_id=recording_id_a, parameters={}, dry_run=True))

        # Filter by recording_id_a
        response = await query(socket_path, ListReplayReportsRequest(recording_id=recording_id_a))
        assert response.ok is True
        data = response.data
        assert isinstance(data, list)
        assert all(r["recording_id"] == recording_id_a for r in data)

        # Filter by non-existent recording
        response_empty = await query(socket_path, ListReplayReportsRequest(recording_id="other-recording"))
        assert response_empty.ok is True
        assert response_empty.data == []

        tg.cancel_scope.cancel()


@pytest.mark.anyio
async def test_list_replay_reports_dispatch_empty_state(socket_path: Path) -> None:
    """ListReplayReportsRequest with no reports → empty list."""
    sm = StateManager(session_id="test-session")
    fake_controller = FakePageController()
    fake_analyzer = FakePageAnalyzer()

    async with anyio.create_task_group() as tg:
        tg.start_soon(run_socket_server, sm, socket_path, fake_controller, None, fake_analyzer)
        await _wait_for_socket(socket_path)

        response = await query(socket_path, ListReplayReportsRequest(recording_id=None))
        assert response.ok is True
        assert response.data == []

        tg.cancel_scope.cancel()
