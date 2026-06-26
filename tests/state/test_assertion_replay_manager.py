"""StateManager — assertion/replay mutation tests (sub-plan 01, Section 3).

TDD: Tests geschrieben ZUERST (RED), dann Implementierung (GREEN).
Deckt: add_assertion_to_timeline, delete_assertion, update_assertion,
add_parameter_to_recording, save_replay_report, get_replay_report,
list_replay_reports_meta, set_active_replay_progress.
"""

from __future__ import annotations

import pytest

from frontprompt.state import StateManager
from frontprompt.state.state import (
    AssertionEntry,
    ParameterDeclaration,
    ReplayProgress,
    ReplayReport,
    ReplayStepResult,
)


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _make_assertion_payload(
    assertion_id: str = "a-001",
    assertion_type: str = "selector_exists",
    comparator: str = "none",
    expected: str | None = None,
) -> dict:
    return {
        "assertion_id": assertion_id,
        "assertion_type": assertion_type,
        "target": "button#submit",
        "target_kind": "selector",
        "expected": expected,
        "comparator": comparator,
        "description": "Check submit button",
    }


def _make_progress(
    replay_id: str = "rep-001",
    recording_id: str = "rec-001",
    current_seq: int = 2,
    total_steps: int = 10,
) -> ReplayProgress:
    return ReplayProgress(
        replay_id=replay_id,
        recording_id=recording_id,
        current_seq=current_seq,
        total_steps=total_steps,
        passed_assertions=1,
        failed_assertions=0,
    )


def _make_report(
    replay_id: str = "rep-001",
    recording_id: str = "rec-001",
    status: str = "completed",
) -> ReplayReport:
    return ReplayReport(
        replay_id=replay_id,
        recording_id=recording_id,
        parameters={},
        status=status,  # type: ignore[arg-type]
        started_at_ms=1000,
        ended_at_ms=2000,
        step_results=[
            ReplayStepResult(
                seq=0, kind="page_event", ok=True, skipped=False,
                skipped_reason=None, error=None, assertion_passed=None,
                assertion_actual=None, duration_ms=10,
            )
        ],
        error=None,
        origin_session=None,
    )


# ---------------------------------------------------------------------------
# add_assertion_to_timeline
# ---------------------------------------------------------------------------


@pytest.mark.anyio
async def test_add_assertion_appended_at_end_when_no_insert_after_seq() -> None:
    """add_assertion_to_timeline appended at end when insert_after_seq=None."""
    sm = StateManager(session_id="sess-001")
    snap = await sm.start_recording(name="Test")
    recording_id = snap.recordings_state.active_recording_id
    assert recording_id is not None

    payload = _make_assertion_payload()
    snap2 = await sm.add_assertion_to_timeline(recording_id, payload, insert_after_seq=None)

    recording = sm.get_recording(recording_id)
    assert recording is not None
    assertion_entries = [e for e in recording.entries if e.kind == "assertion"]
    assert len(assertion_entries) == 1
    assert assertion_entries[0].assertion_id == "a-001"
    # seq should be assigned (= len(entries) before append)
    assert assertion_entries[0].seq >= 0
    # snapshot broadcast happened
    assert snap2 is not None


@pytest.mark.anyio
async def test_add_assertion_after_seq_inserts_and_renumbers() -> None:
    """add_assertion_to_timeline with insert_after_seq inserts and renumbers later entries."""
    from frontprompt.state.state import NavigationEntry, PageEventEntry

    sm = StateManager(session_id="sess-001")
    snap = await sm.start_recording(name="Seq Test")
    recording_id = snap.recordings_state.active_recording_id
    assert recording_id is not None

    # Add 3 navigation entries manually via append_timeline_entry
    for i in range(3):
        nav = NavigationEntry(
            kind="navigation",
            seq=0,  # will be overwritten
            timestamp_ms=1000 + i,
            from_url=f"https://a.com/{i}",
            to_url=f"https://a.com/{i + 1}",
        )
        await sm.append_timeline_entry(recording_id, nav)

    recording = sm.get_recording(recording_id)
    assert recording is not None
    assert len(recording.entries) == 3  # seqs 0, 1, 2

    # Insert assertion after seq=1 (between seq 1 and seq 2)
    payload = _make_assertion_payload(assertion_id="a-mid")
    await sm.add_assertion_to_timeline(recording_id, payload, insert_after_seq=1)

    recording = sm.get_recording(recording_id)
    assert recording is not None
    assert len(recording.entries) == 4
    # Find the assertion
    assertion = next((e for e in recording.entries if e.kind == "assertion"), None)
    assert assertion is not None
    # It should be at position index=2 (after old seq=1 at index=1)
    assert assertion.seq == 2
    # Former seq=2 should now be seq=3
    last_entry = recording.entries[-1]
    assert last_entry.seq == 3


@pytest.mark.anyio
async def test_add_assertion_unknown_recording_is_noop() -> None:
    """add_assertion_to_timeline with unknown recording_id: no-op, no exception."""
    sm = StateManager(session_id="sess-001")
    payload = _make_assertion_payload()
    # Should not raise
    result = await sm.add_assertion_to_timeline("unknown-rec-id", payload, insert_after_seq=None)
    assert result is not None  # snapshot still returned (may be default snapshot)


# ---------------------------------------------------------------------------
# delete_assertion
# ---------------------------------------------------------------------------


@pytest.mark.anyio
async def test_delete_assertion_removes_entry_and_renumbers() -> None:
    """delete_assertion removes assertion, renumbers seqs, broadcasts snapshot."""
    sm = StateManager(session_id="sess-001")
    snap = await sm.start_recording(name="Delete Test")
    recording_id = snap.recordings_state.active_recording_id
    assert recording_id is not None

    payload_1 = _make_assertion_payload(assertion_id="a-del-1")
    payload_2 = _make_assertion_payload(assertion_id="a-del-2")
    await sm.add_assertion_to_timeline(recording_id, payload_1, insert_after_seq=None)
    await sm.add_assertion_to_timeline(recording_id, payload_2, insert_after_seq=None)

    recording = sm.get_recording(recording_id)
    assert recording is not None
    assert len(recording.entries) == 2

    snap2 = await sm.delete_assertion(recording_id, "a-del-1")
    recording = sm.get_recording(recording_id)
    assert recording is not None
    assert len(recording.entries) == 1
    remaining = recording.entries[0]
    assert remaining.kind == "assertion"
    assert remaining.assertion_id == "a-del-2"  # type: ignore[attr-defined]
    assert remaining.seq == 0  # renumbered
    assert snap2 is not None


# ---------------------------------------------------------------------------
# update_assertion
# ---------------------------------------------------------------------------


@pytest.mark.anyio
async def test_update_assertion_patches_fields_and_broadcasts() -> None:
    """update_assertion applies partial update and broadcasts snapshot."""
    sm = StateManager(session_id="sess-001")
    snap = await sm.start_recording(name="Update Test")
    recording_id = snap.recordings_state.active_recording_id
    assert recording_id is not None

    payload = _make_assertion_payload(assertion_id="a-upd")
    await sm.add_assertion_to_timeline(recording_id, payload, insert_after_seq=None)

    patch = {"description": "Updated description", "expected": "New expected value"}
    snap2 = await sm.update_assertion(recording_id, "a-upd", patch)

    recording = sm.get_recording(recording_id)
    assert recording is not None
    assertion = next((e for e in recording.entries if e.kind == "assertion"), None)
    assert assertion is not None
    assert assertion.description == "Updated description"  # type: ignore[attr-defined]
    assert assertion.expected == "New expected value"  # type: ignore[attr-defined]
    assert snap2 is not None


# ---------------------------------------------------------------------------
# add_parameter_to_recording
# ---------------------------------------------------------------------------


@pytest.mark.anyio
async def test_add_parameter_appends_to_recording() -> None:
    """add_parameter_to_recording adds parameter to recording."""
    sm = StateManager(session_id="sess-001")
    snap = await sm.start_recording(name="Param Test")
    recording_id = snap.recordings_state.active_recording_id
    assert recording_id is not None

    await sm.stop_recording(recording_id)

    param = ParameterDeclaration(name="base_url", param_type="url", description="Base URL")
    await sm.add_parameter_to_recording(recording_id, param)

    recording = sm.get_recording(recording_id)
    assert recording is not None
    assert len(recording.parameters) == 1
    assert recording.parameters[0].name == "base_url"


@pytest.mark.anyio
async def test_add_parameter_duplicate_name_raises_value_error() -> None:
    """add_parameter_to_recording with duplicate name raises ValueError."""
    sm = StateManager(session_id="sess-001")
    snap = await sm.start_recording(name="Param Dup Test")
    recording_id = snap.recordings_state.active_recording_id
    assert recording_id is not None

    param = ParameterDeclaration(name="login_url", param_type="url", description="Login URL")
    await sm.add_parameter_to_recording(recording_id, param)

    param_dup = ParameterDeclaration(name="login_url", param_type="string", description="Duplicate")
    with pytest.raises(ValueError, match="login_url"):
        await sm.add_parameter_to_recording(recording_id, param_dup)


# ---------------------------------------------------------------------------
# save_replay_report / get_replay_report / list_replay_reports_meta
# ---------------------------------------------------------------------------


@pytest.mark.anyio
async def test_save_replay_report_delegates_to_persistence() -> None:
    """save_replay_report delegates to persistence; no snapshot broadcast (agents poll via IPC)."""
    sm = StateManager(session_id="sess-001")
    report = _make_report()

    # save_replay_report should not raise and delegates to persistence
    await sm.save_replay_report(report)

    # Verify retrievable via get_replay_report
    retrieved = await sm.get_replay_report("rep-001")
    assert retrieved is not None
    assert retrieved.replay_id == "rep-001"
    assert retrieved.status == "completed"


@pytest.mark.anyio
async def test_get_replay_report_unknown_returns_none() -> None:
    """get_replay_report for unknown id returns None."""
    sm = StateManager(session_id="sess-001")
    result = await sm.get_replay_report("does-not-exist")
    assert result is None


@pytest.mark.anyio
async def test_list_replay_reports_meta_delegates_to_persistence() -> None:
    """list_replay_reports_meta delegates to persistence."""
    sm = StateManager(session_id="sess-001")
    report1 = _make_report(replay_id="rep-L1", recording_id="rec-A")
    report2 = _make_report(replay_id="rep-L2", recording_id="rec-A")
    await sm.save_replay_report(report1)
    await sm.save_replay_report(report2)

    metas = await sm.list_replay_reports_meta(recording_id="rec-A")
    assert len(metas) == 2
    assert all(m.recording_id == "rec-A" for m in metas)


# ---------------------------------------------------------------------------
# set_active_replay_progress
# ---------------------------------------------------------------------------


@pytest.mark.anyio
async def test_set_active_replay_progress_updates_state_and_broadcasts() -> None:
    """set_active_replay_progress updates RecordingsState and broadcasts snapshot."""
    sm = StateManager(session_id="sess-001")
    progress = _make_progress()
    snap = await sm.set_active_replay_progress(progress)

    assert snap.recordings_state.active_replay_progress is not None
    assert snap.recordings_state.active_replay_progress.replay_id == "rep-001"
    assert snap.recordings_state.active_replay_progress.current_seq == 2


@pytest.mark.anyio
async def test_set_active_replay_progress_none_clears_state() -> None:
    """set_active_replay_progress(None) clears active_replay_progress."""
    sm = StateManager(session_id="sess-001")
    progress = _make_progress()
    await sm.set_active_replay_progress(progress)

    snap = await sm.set_active_replay_progress(None)
    assert snap.recordings_state.active_replay_progress is None
