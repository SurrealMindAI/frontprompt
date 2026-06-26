"""ShowSession assertion-authoring bridge handler tests — replay sub-plan 04.

Covers:
  1. AssertionAddedToRecordingRequested → state_manager.add_assertion_to_timeline(...) + snapshot broadcast
  2. AssertionDeletedRequested → state_manager.delete_assertion(recording_id, assertion_id) + snapshot broadcast
  3. AssertionUpdatedRequested → state_manager.update_assertion(recording_id, assertion_id, patch) + snapshot broadcast
  4. Unknown recording_id in any handler → no-op (idempotent)
  5. ShowSession.handler_count() returns 25 (22 existing + 3 assertion handlers)

All handler tests use a real StateManager (InMemory persistence) for integration-level confidence.
"""

from __future__ import annotations

import pytest

from frontprompt.state import StateManager


# ---------------------------------------------------------------------------
# Test 5 — handler_count updated to 28 (COL-4: +3 voice-over settings handlers)
# ---------------------------------------------------------------------------


def test_handler_count_is_28() -> None:
    """ShowSession.handler_count() must return 28 after adding voice-over settings handlers.

    COL-4: 22 existing + 3 assertion + 3 voice-over settings = 28.
    The 3 voice-over settings handlers are SetMicDeviceRequested,
    SetTranscriptionBackendRequested, TriggerModelDownloadRequested.
    """
    from frontprompt.show_session import ShowSession

    s = ShowSession(url="https://example.com")
    assert s.handler_count() == 28, (
        f"Expected 28 handlers (22 existing + 3 assertion + 3 voice-over settings), got {s.handler_count()}. "
        "Update handler_count() and its comment when adding/removing bridge message handlers."
    )


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _make_session(session_id: str = "test-assertion-dispatch") -> tuple:
    """Return (ShowSession, StateManager) with InMemory persistence."""
    from frontprompt.show_session import ShowSession

    sm = StateManager(session_id=session_id)
    s = ShowSession(url="https://example.com", state_manager=sm)
    return s, sm


def _make_assertion_payload(
    assertion_id: str = "test-assertion-uuid",
    assertion_type: str = "selector_exists",
    target: str = "button#submit",
    target_kind: str = "selector",
    expected: str | None = None,
    comparator: str = "none",
    description: str = "Submit button exists",
) -> dict:
    """Build a valid AssertionEntry payload dict (no seq, no timestamp_ms, no kind)."""
    return {
        "assertion_id": assertion_id,
        "assertion_type": assertion_type,
        "target": target,
        "target_kind": target_kind,
        "expected": expected,
        "comparator": comparator,
        "description": description,
    }


# ---------------------------------------------------------------------------
# Test 1 — AssertionAddedToRecordingRequested handler
# ---------------------------------------------------------------------------


@pytest.mark.anyio
async def test_assertion_added_handler_appends_assertion() -> None:
    """_on_assertion_added calls add_assertion_to_timeline and the assertion appears in the recording."""
    from frontprompt.bridge.messages import AssertionAddedToRecordingRequested

    session, sm = _make_session()
    await sm.start_recording(name="Test Recording", description="")
    metas = sm.list_recordings_meta()
    recording_id = metas[0].recording_id

    payload = _make_assertion_payload(assertion_id="assert-uuid-1")
    msg = AssertionAddedToRecordingRequested(
        recording_id=recording_id,
        assertion=payload,
        insert_after_seq=None,
    )
    await session._on_assertion_added(msg)

    recording = sm.get_recording(recording_id)
    assert recording is not None
    assert len(recording.entries) == 1
    assert recording.entries[0].kind == "assertion"
    assert recording.entries[0].assertion_id == "assert-uuid-1"  # type: ignore[attr-defined]
    assert recording.entries[0].target == "button#submit"  # type: ignore[attr-defined]
    assert recording.entries[0].seq == 0


@pytest.mark.anyio
async def test_assertion_added_handler_broadcasts_snapshot() -> None:
    """_on_assertion_added triggers a snapshot broadcast via StateManager listener."""
    from frontprompt.bridge.messages import AssertionAddedToRecordingRequested

    session, sm = _make_session()
    await sm.start_recording(name="Test Recording", description="")
    metas = sm.list_recordings_meta()
    recording_id = metas[0].recording_id

    # Listener receives broadcast from start_recording call above — reset count now.
    broadcasts: list[object] = []
    sm.add_snapshot_listener(lambda snap: broadcasts.append(snap))

    payload = _make_assertion_payload()
    msg = AssertionAddedToRecordingRequested(
        recording_id=recording_id,
        assertion=payload,
        insert_after_seq=None,
    )
    await session._on_assertion_added(msg)

    assert len(broadcasts) == 1, (
        f"Expected exactly 1 snapshot broadcast from add_assertion_to_timeline, got {len(broadcasts)}"
    )


@pytest.mark.anyio
async def test_assertion_added_handler_inserts_after_seq() -> None:
    """_on_assertion_added with insert_after_seq inserts at the correct position."""
    from frontprompt.bridge.messages import AssertionAddedToRecordingRequested
    from frontprompt.state.state import PageEventEntry

    session, sm = _make_session()
    await sm.start_recording(name="Test Recording", description="")
    metas = sm.list_recordings_meta()
    recording_id = metas[0].recording_id

    # Append a page event first (seq=0)
    event_entry = PageEventEntry(
        kind="page_event",
        seq=0,
        timestamp_ms=1_700_000_000_000,
        event_type="click",
        target="button",
        target_path=["html", "body", "button"],
        default_prevented=False,
        key=None,
    )
    await sm.append_timeline_entry(recording_id, event_entry)

    # Insert assertion after seq=0
    payload = _make_assertion_payload(assertion_id="assert-inserted")
    msg = AssertionAddedToRecordingRequested(
        recording_id=recording_id,
        assertion=payload,
        insert_after_seq=0,
    )
    await session._on_assertion_added(msg)

    recording = sm.get_recording(recording_id)
    assert recording is not None
    assert len(recording.entries) == 2
    # The assertion was inserted at index 1 (after seq 0)
    assert recording.entries[1].kind == "assertion"
    assert recording.entries[1].assertion_id == "assert-inserted"  # type: ignore[attr-defined]


@pytest.mark.anyio
async def test_assertion_added_unknown_recording_is_noop() -> None:
    """_on_assertion_added with unknown recording_id is a no-op (no exception)."""
    from frontprompt.bridge.messages import AssertionAddedToRecordingRequested

    session, sm = _make_session()
    payload = _make_assertion_payload()
    msg = AssertionAddedToRecordingRequested(
        recording_id="unknown-recording-id",
        assertion=payload,
        insert_after_seq=None,
    )
    # Must not raise
    await session._on_assertion_added(msg)
    assert sm._recordings_state.recordings == []


# ---------------------------------------------------------------------------
# Test 2 — AssertionDeletedRequested handler
# ---------------------------------------------------------------------------


@pytest.mark.anyio
async def test_assertion_deleted_handler_removes_assertion() -> None:
    """_on_assertion_deleted calls delete_assertion and the assertion is removed."""
    from frontprompt.bridge.messages import AssertionAddedToRecordingRequested, AssertionDeletedRequested

    session, sm = _make_session()
    await sm.start_recording(name="Test Recording", description="")
    metas = sm.list_recordings_meta()
    recording_id = metas[0].recording_id

    # Add an assertion first
    payload = _make_assertion_payload(assertion_id="assert-to-delete")
    add_msg = AssertionAddedToRecordingRequested(
        recording_id=recording_id,
        assertion=payload,
        insert_after_seq=None,
    )
    await session._on_assertion_added(add_msg)

    recording = sm.get_recording(recording_id)
    assert recording is not None
    assert len(recording.entries) == 1

    # Delete it
    del_msg = AssertionDeletedRequested(
        recording_id=recording_id,
        assertion_id="assert-to-delete",
    )
    await session._on_assertion_deleted(del_msg)

    recording = sm.get_recording(recording_id)
    assert recording is not None
    assert len(recording.entries) == 0


@pytest.mark.anyio
async def test_assertion_deleted_handler_broadcasts_snapshot() -> None:
    """_on_assertion_deleted triggers a snapshot broadcast via StateManager listener."""
    from frontprompt.bridge.messages import AssertionAddedToRecordingRequested, AssertionDeletedRequested

    session, sm = _make_session()
    await sm.start_recording(name="Test Recording", description="")
    metas = sm.list_recordings_meta()
    recording_id = metas[0].recording_id

    payload = _make_assertion_payload(assertion_id="assert-to-delete")
    add_msg = AssertionAddedToRecordingRequested(
        recording_id=recording_id,
        assertion=payload,
        insert_after_seq=None,
    )
    await session._on_assertion_added(add_msg)

    # Attach listener after setup
    broadcasts: list[object] = []
    sm.add_snapshot_listener(lambda snap: broadcasts.append(snap))

    del_msg = AssertionDeletedRequested(
        recording_id=recording_id,
        assertion_id="assert-to-delete",
    )
    await session._on_assertion_deleted(del_msg)

    assert len(broadcasts) == 1, (
        f"Expected exactly 1 snapshot broadcast from delete_assertion, got {len(broadcasts)}"
    )


@pytest.mark.anyio
async def test_assertion_deleted_unknown_recording_is_noop() -> None:
    """_on_assertion_deleted with unknown recording_id is a no-op (no exception)."""
    from frontprompt.bridge.messages import AssertionDeletedRequested

    session, sm = _make_session()
    msg = AssertionDeletedRequested(
        recording_id="unknown-recording-id",
        assertion_id="some-assertion-id",
    )
    await session._on_assertion_deleted(msg)
    # No exception, no state change
    assert sm._recordings_state.recordings == []


# ---------------------------------------------------------------------------
# Test 3 — AssertionUpdatedRequested handler
# ---------------------------------------------------------------------------


@pytest.mark.anyio
async def test_assertion_updated_handler_patches_fields() -> None:
    """_on_assertion_updated calls update_assertion and patched fields are updated."""
    from frontprompt.bridge.messages import AssertionAddedToRecordingRequested, AssertionUpdatedRequested

    session, sm = _make_session()
    await sm.start_recording(name="Test Recording", description="")
    metas = sm.list_recordings_meta()
    recording_id = metas[0].recording_id

    # Add an assertion first
    payload = _make_assertion_payload(
        assertion_id="assert-to-update",
        assertion_type="selector_exists",
        description="Old description",
    )
    add_msg = AssertionAddedToRecordingRequested(
        recording_id=recording_id,
        assertion=payload,
        insert_after_seq=None,
    )
    await session._on_assertion_added(add_msg)

    # Update description
    upd_msg = AssertionUpdatedRequested(
        recording_id=recording_id,
        assertion_id="assert-to-update",
        assertion_type=None,
        target=None,
        expected=None,
        description="New description",
    )
    await session._on_assertion_updated(upd_msg)

    recording = sm.get_recording(recording_id)
    assert recording is not None
    assert recording.entries[0].description == "New description"  # type: ignore[attr-defined]
    # Untouched fields remain
    assert recording.entries[0].assertion_type == "selector_exists"  # type: ignore[attr-defined]


@pytest.mark.anyio
async def test_assertion_updated_handler_broadcasts_snapshot() -> None:
    """_on_assertion_updated triggers a snapshot broadcast via StateManager listener."""
    from frontprompt.bridge.messages import AssertionAddedToRecordingRequested, AssertionUpdatedRequested

    session, sm = _make_session()
    await sm.start_recording(name="Test Recording", description="")
    metas = sm.list_recordings_meta()
    recording_id = metas[0].recording_id

    payload = _make_assertion_payload(assertion_id="assert-to-update")
    add_msg = AssertionAddedToRecordingRequested(
        recording_id=recording_id,
        assertion=payload,
        insert_after_seq=None,
    )
    await session._on_assertion_added(add_msg)

    broadcasts: list[object] = []
    sm.add_snapshot_listener(lambda snap: broadcasts.append(snap))

    upd_msg = AssertionUpdatedRequested(
        recording_id=recording_id,
        assertion_id="assert-to-update",
        assertion_type=None,
        target=None,
        expected=None,
        description="Updated",
    )
    await session._on_assertion_updated(upd_msg)

    assert len(broadcasts) == 1, (
        f"Expected exactly 1 snapshot broadcast from update_assertion, got {len(broadcasts)}"
    )


@pytest.mark.anyio
async def test_assertion_updated_handler_none_fields_not_patched() -> None:
    """_on_assertion_updated with all-None patch fields is a no-op on values."""
    from frontprompt.bridge.messages import AssertionAddedToRecordingRequested, AssertionUpdatedRequested

    session, sm = _make_session()
    await sm.start_recording(name="Test Recording", description="")
    metas = sm.list_recordings_meta()
    recording_id = metas[0].recording_id

    payload = _make_assertion_payload(
        assertion_id="assert-noop-update",
        target="h1",
        description="Original",
    )
    add_msg = AssertionAddedToRecordingRequested(
        recording_id=recording_id,
        assertion=payload,
        insert_after_seq=None,
    )
    await session._on_assertion_added(add_msg)

    upd_msg = AssertionUpdatedRequested(
        recording_id=recording_id,
        assertion_id="assert-noop-update",
        assertion_type=None,
        target=None,
        expected=None,
        description=None,  # No-op: all None
    )
    await session._on_assertion_updated(upd_msg)

    recording = sm.get_recording(recording_id)
    assert recording is not None
    assert recording.entries[0].target == "h1"  # type: ignore[attr-defined]
    assert recording.entries[0].description == "Original"  # type: ignore[attr-defined]


@pytest.mark.anyio
async def test_assertion_updated_unknown_recording_is_noop() -> None:
    """_on_assertion_updated with unknown recording_id is a no-op (no exception)."""
    from frontprompt.bridge.messages import AssertionUpdatedRequested

    session, sm = _make_session()
    msg = AssertionUpdatedRequested(
        recording_id="unknown-recording-id",
        assertion_id="some-assertion-id",
        assertion_type=None,
        target=None,
        expected=None,
        description=None,
    )
    await session._on_assertion_updated(msg)
    assert sm._recordings_state.recordings == []
