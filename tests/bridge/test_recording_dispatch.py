"""ShowSession recording bridge handler tests — sub-plan 04.

Covers:
  1. RecordingStartRequested → state_manager.start_recording(name, description) + snapshot broadcast
  2. RecordingStopRequested → state_manager.stop_recording(recording_id) + snapshot broadcast
  3. RecordingRenameRequested → state_manager.rename_recording(...) + snapshot broadcast
  4. RecordingSelectedRequested(recording_id=None) → state_manager.select_recording(None)
  5. RecordingSelectedRequested(recording_id="some-id") → state_manager.select_recording("some-id")
  6. RecordedEventCapturedRequested → state_manager.append_timeline_entry(recording_id, entry) — NO snapshot broadcast
  7. handler_count() returns 22 (was 17, + 5 recording handlers)

All handler tests use a real StateManager (InMemory persistence) for integration-level confidence.
"""

from __future__ import annotations

import pytest

from frontprompt.state import StateManager
from frontprompt.state.state import PageEventEntry


# ---------------------------------------------------------------------------
# Test 7 — handler_count updated to 22
# ---------------------------------------------------------------------------


def test_handler_count_is_22() -> None:
    """ShowSession.handler_count() must return 22 after adding 5 recording handlers."""
    from frontprompt.show_session import ShowSession

    s = ShowSession(url="https://example.com")
    assert s.handler_count() == 22, (
        f"Expected 22 handlers (17 existing + 5 recording), got {s.handler_count()}. "
        "Update handler_count() and its comment when adding/removing bridge message handlers."
    )


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _make_session(session_id: str = "test-dispatch") -> tuple:
    """Return (ShowSession, StateManager) with InMemory persistence."""
    from frontprompt.show_session import ShowSession

    sm = StateManager(session_id=session_id)
    s = ShowSession(url="https://example.com", state_manager=sm)
    return s, sm


def _make_page_event_entry(**kwargs: object) -> PageEventEntry:
    defaults = {
        "kind": "page_event",
        "seq": 0,
        "timestamp_ms": 1_700_000_000_000,
        "event_type": "click",
        "target": "button#submit.cta",
        "target_path": ["html", "body", "main", "button"],
        "default_prevented": False,
        "key": None,
    }
    defaults.update(kwargs)  # type: ignore[arg-type]
    return PageEventEntry(**defaults)  # type: ignore[arg-type]


# ---------------------------------------------------------------------------
# Test 1 — RecordingStartRequested handler
# ---------------------------------------------------------------------------


@pytest.mark.anyio
async def test_recording_start_handler_creates_recording() -> None:
    """_on_recording_start calls state_manager.start_recording and creates an active recording."""
    from frontprompt.bridge.messages import RecordingStartRequested

    session, sm = _make_session()

    msg = RecordingStartRequested(name="Login Flow", description="Tests auth")
    await session._on_recording_start(msg)

    assert sm._recordings_state.active_recording_id is not None, (
        "After start_recording, active_recording_id should be set"
    )
    recordings = sm._recordings_state.recordings
    assert len(recordings) == 1
    assert recordings[0].name == "Login Flow"
    assert recordings[0].description == "Tests auth"
    assert recordings[0].status == "active"


@pytest.mark.anyio
async def test_recording_start_handler_uses_defaults() -> None:
    """_on_recording_start with default fields produces default name/description."""
    from frontprompt.bridge.messages import RecordingStartRequested

    session, sm = _make_session()
    await session._on_recording_start(RecordingStartRequested())

    recordings = sm._recordings_state.recordings
    assert len(recordings) == 1
    assert recordings[0].name == "New Recording"
    assert recordings[0].description == ""


# ---------------------------------------------------------------------------
# Test 2 — RecordingStopRequested handler
# ---------------------------------------------------------------------------


@pytest.mark.anyio
async def test_recording_stop_handler_stops_recording() -> None:
    """_on_recording_stop calls state_manager.stop_recording and clears active_recording_id."""
    from frontprompt.bridge.messages import RecordingStartRequested, RecordingStopRequested

    session, sm = _make_session()
    await session._on_recording_start(RecordingStartRequested())

    recording_id = sm._recordings_state.active_recording_id
    assert recording_id is not None

    await session._on_recording_stop(RecordingStopRequested(recording_id=recording_id))

    assert sm._recordings_state.active_recording_id is None
    assert sm._recordings_state.recordings[0].status == "stopped"


@pytest.mark.anyio
async def test_recording_stop_unknown_id_is_noop() -> None:
    """_on_recording_stop with unknown recording_id is a no-op (no exception)."""
    from frontprompt.bridge.messages import RecordingStopRequested

    session, sm = _make_session()
    # No exception raised for unknown id
    await session._on_recording_stop(RecordingStopRequested(recording_id="unknown-id"))
    assert sm._recordings_state.active_recording_id is None


# ---------------------------------------------------------------------------
# Test 3 — RecordingRenameRequested handler
# ---------------------------------------------------------------------------


@pytest.mark.anyio
async def test_recording_rename_handler_updates_metadata() -> None:
    """_on_recording_rename calls state_manager.rename_recording and updates name/description."""
    from frontprompt.bridge.messages import RecordingRenameRequested, RecordingStartRequested

    session, sm = _make_session()
    await session._on_recording_start(RecordingStartRequested(name="Old Name", description="Old Desc"))

    recording_id = sm._recordings_state.recordings[0].recording_id
    await session._on_recording_rename(
        RecordingRenameRequested(recording_id=recording_id, name="New Name", description="New Desc")
    )

    meta = sm._recordings_state.recordings[0]
    assert meta.name == "New Name"
    assert meta.description == "New Desc"


# ---------------------------------------------------------------------------
# Test 4/5 — RecordingSelectedRequested handler
# ---------------------------------------------------------------------------


@pytest.mark.anyio
async def test_recording_selected_handler_with_none_clears_detail() -> None:
    """_on_recording_selected(recording_id=None) calls select_recording(None) — deselects."""
    from frontprompt.bridge.messages import RecordingSelectedRequested

    session, sm = _make_session()
    # Deselect is a no-op when nothing is selected — should not raise
    await session._on_recording_selected(RecordingSelectedRequested(recording_id=None))
    assert sm._recordings_state.active_detail_recording_id is None


@pytest.mark.anyio
async def test_recording_selected_handler_with_id_sets_detail() -> None:
    """_on_recording_selected(recording_id=<id>) calls select_recording(<id>)."""
    from frontprompt.bridge.messages import RecordingSelectedRequested, RecordingStartRequested

    session, sm = _make_session()
    # Create a recording to select
    await session._on_recording_start(RecordingStartRequested())
    recording_id = sm._recordings_state.recordings[0].recording_id

    await session._on_recording_selected(RecordingSelectedRequested(recording_id=recording_id))
    assert sm._recordings_state.active_detail_recording_id == recording_id


@pytest.mark.anyio
async def test_recording_selected_unknown_id_is_noop() -> None:
    """_on_recording_selected with unknown recording_id is a no-op (no exception)."""
    from frontprompt.bridge.messages import RecordingSelectedRequested

    session, sm = _make_session()
    await session._on_recording_selected(RecordingSelectedRequested(recording_id="unknown"))
    # No exception; active_detail remains None
    assert sm._recordings_state.active_detail_recording_id is None


# ---------------------------------------------------------------------------
# Test 6 — RecordedEventCapturedRequested handler (no snapshot broadcast)
# ---------------------------------------------------------------------------


@pytest.mark.anyio
async def test_recorded_event_captured_handler_appends_entry() -> None:
    """_on_recorded_event_captured calls append_timeline_entry and the entry is appended."""
    from frontprompt.bridge.messages import RecordedEventCapturedRequested, RecordingStartRequested

    session, sm = _make_session()
    await session._on_recording_start(RecordingStartRequested())
    recording_id = sm._recordings_state.recordings[0].recording_id

    entry = _make_page_event_entry(event_type="click", target="button#go")
    await session._on_recorded_event_captured(
        RecordedEventCapturedRequested(recording_id=recording_id, entry=entry)
    )

    full_recording = sm._full_recordings.get(recording_id)
    assert full_recording is not None
    assert len(full_recording.entries) == 1
    assert full_recording.entries[0].kind == "page_event"
    assert full_recording.entries[0].target == "button#go"
    # seq is stamped Python-side
    assert full_recording.entries[0].seq == 0


@pytest.mark.anyio
async def test_recorded_event_captured_handler_does_not_broadcast_snapshot() -> None:
    """_on_recorded_event_captured does NOT trigger a snapshot broadcast (COL-5 / PIT-105)."""
    from frontprompt.bridge.messages import RecordedEventCapturedRequested, RecordingStartRequested

    session, sm = _make_session()
    await session._on_recording_start(RecordingStartRequested())
    recording_id = sm._recordings_state.recordings[0].recording_id

    # Attach a snapshot listener — it should NOT be called for event captures
    snapshot_broadcasts: list[object] = []
    sm.add_snapshot_listener(lambda snap: snapshot_broadcasts.append(snap))

    entry = _make_page_event_entry(event_type="keydown", key="Enter")
    await session._on_recorded_event_captured(
        RecordedEventCapturedRequested(recording_id=recording_id, entry=entry)
    )

    assert len(snapshot_broadcasts) == 0, (
        "append_timeline_entry must NOT trigger snapshot broadcast (non-broadcasting path, COL-5)"
    )


@pytest.mark.anyio
async def test_recorded_event_captured_unknown_recording_is_noop() -> None:
    """_on_recorded_event_captured with unknown recording_id is a no-op (no exception)."""
    from frontprompt.bridge.messages import RecordedEventCapturedRequested

    session, sm = _make_session()
    entry = _make_page_event_entry()
    await session._on_recorded_event_captured(
        RecordedEventCapturedRequested(recording_id="unknown", entry=entry)
    )
    # No exception raised
