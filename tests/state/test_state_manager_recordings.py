"""StateManager — Recording-domain mutation tests (sub-plan 01, Section 5).

TDD: alle Tests hier sollten RED sein bis die Mutations implementiert sind.
Deckt: start_recording, stop_recording, rename_recording, select_recording,
append_timeline_entry (non-broadcast), auto-link (add_pick/add_region/add_relation
+ add_pick_from_programmatic_source), snapshot COL-2, seq ownership Q1.
"""

from __future__ import annotations

import time

import pytest

from frontprompt.state import StateManager
from frontprompt.state.state import (
    ElementFingerprint,
    ElementRect,
    PageEventEntry,
    Pick,
    PickElement,
    Region,
    Relation,
)

# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _make_pick(pick_id: str = "p-001") -> Pick:
    return Pick(
        pick_id=pick_id,
        url="https://example.com/",
        timestamp_ms=1_700_000_000_000,
        element=PickElement(
            selector=f"#{pick_id}",
            fingerprint=ElementFingerprint(tag="div"),
            text_snippet="text",
            rect=ElementRect(x=0.0, y=0.0, width=100.0, height=40.0),
        ),
    )


def _make_region(region_id: str = "r-001") -> Region:
    return Region(
        region_id=region_id,
        rect=ElementRect(x=0.0, y=0.0, width=200.0, height=100.0),
        timestamp_ms=1_700_000_000_000,
    )


def _make_relation(source_id: str = "p-001", target_id: str = "p-002") -> Relation:
    return Relation(
        relation_id="rel-001",
        source_id=source_id,
        source_kind="pick",
        target_id=target_id,
        target_kind="pick",
        kind="relates_to",
        timestamp_ms=1_700_000_000_000,
    )


def _make_page_event(seq: int = 0, timestamp_ms: int = 1000) -> PageEventEntry:
    return PageEventEntry(
        kind="page_event",
        seq=seq,
        timestamp_ms=timestamp_ms,
        event_type="click",
        target="button#submit",
        target_path=["html", "body", "button"],
        default_prevented=False,
        key=None,
    )


# ---------------------------------------------------------------------------
# start_recording
# ---------------------------------------------------------------------------


@pytest.mark.anyio
async def test_start_recording_creates_recording_and_sets_active() -> None:
    """start_recording erstellt Recording, setzt active_recording_id, broadcastet Snapshot."""
    sm = StateManager(session_id="test-session")
    snap = await sm.start_recording(name="My Test Recording", description="desc")

    assert snap.recordings_state.active_recording_id is not None
    assert len(snap.recordings_state.recordings) == 1
    assert snap.recordings_state.recordings[0].name == "My Test Recording"
    assert snap.recordings_state.recordings[0].description == "desc"
    assert snap.recordings_state.recordings[0].status == "active"


@pytest.mark.anyio
async def test_start_recording_calls_upsert_on_persistence() -> None:
    """start_recording persistiert Recording via persistence.upsert_recording."""
    from frontprompt.state.persistence.in_memory import InMemoryPersistence

    persistence = InMemoryPersistence()
    sm = StateManager(session_id="test-session", persistence=persistence)

    await sm.start_recording(name="Persisted Recording")

    recordings = persistence.load_recordings()
    assert len(recordings) == 1
    assert recordings[0].name == "Persisted Recording"


@pytest.mark.anyio
async def test_start_recording_while_active_stops_previous() -> None:
    """start_recording während Aufnahme aktiv: beendet vorherige Aufnahme zuerst."""
    sm = StateManager(session_id="test-session")

    snap1 = await sm.start_recording(name="First")
    first_id = snap1.recordings_state.active_recording_id
    assert first_id is not None

    snap2 = await sm.start_recording(name="Second")
    second_id = snap2.recordings_state.active_recording_id

    # Second recording is now active
    assert second_id is not None
    assert second_id != first_id
    assert snap2.recordings_state.active_recording_id == second_id

    # First recording should be stopped
    first_meta = next(r for r in snap2.recordings_state.recordings if r.recording_id == first_id)
    assert first_meta.status == "stopped"


@pytest.mark.anyio
async def test_start_recording_clears_active_detail_recording_id() -> None:
    """start_recording löscht active_detail_recording_id (reviewer Q2 — kein stale detail)."""
    sm = StateManager(session_id="test-session")

    # Start a first recording and select it as detail
    snap1 = await sm.start_recording(name="First")
    first_id = snap1.recordings_state.active_recording_id
    assert first_id is not None
    await sm.stop_recording(first_id)
    await sm.select_recording(first_id)

    # Now start a new recording — should clear active_detail_recording_id
    snap2 = await sm.start_recording(name="Second")
    assert snap2.recordings_state.active_detail_recording_id is None
    assert snap2.recordings_state.detail_recording is None


# ---------------------------------------------------------------------------
# stop_recording
# ---------------------------------------------------------------------------


@pytest.mark.anyio
async def test_stop_recording_sets_status_stopped() -> None:
    """stop_recording setzt status=stopped + ended_at_ms, löscht active_recording_id."""
    sm = StateManager(session_id="test-session")
    snap = await sm.start_recording(name="To Stop")
    recording_id = snap.recordings_state.active_recording_id
    assert recording_id is not None

    stopped_snap = await sm.stop_recording(recording_id)

    assert stopped_snap.recordings_state.active_recording_id is None
    stopped_meta = next(r for r in stopped_snap.recordings_state.recordings if r.recording_id == recording_id)
    assert stopped_meta.status == "stopped"
    assert stopped_meta.ended_at_ms is not None


@pytest.mark.anyio
async def test_entry_count_reflects_appended_entries_after_stop() -> None:
    """BUG 1 regression: RecordingMeta.entry_count must reflect the true number of
    appended timeline entries at the next real broadcast (e.g. stop_recording),
    not the stale 0 captured when the recording was first created.

    The non-broadcasting append_timeline_entry path (PIT-105) mutates only
    _full_recordings; the lightweight meta must be re-derived on broadcast.
    """
    sm = StateManager(session_id="test-session")
    snap = await sm.start_recording(name="With Entries")
    recording_id = snap.recordings_state.active_recording_id
    assert recording_id is not None

    # Append N entries via the non-broadcasting path (no snapshot per append).
    n = 4
    for i in range(n):
        await sm.append_timeline_entry(recording_id, _make_page_event(seq=0, timestamp_ms=1000 + i))

    # Next real broadcast (stop) must carry the correct entry_count.
    stopped_snap = await sm.stop_recording(recording_id)
    stopped_meta = next(
        r for r in stopped_snap.recordings_state.recordings if r.recording_id == recording_id
    )
    assert stopped_meta.entry_count == n

    # And the lightweight read API agrees.
    meta = next(r for r in sm.list_recordings_meta() if r.recording_id == recording_id)
    assert meta.entry_count == n


@pytest.mark.anyio
async def test_stop_recording_unknown_id_is_noop() -> None:
    """stop_recording mit unbekannter ID: no-op + warning log (kein Crash)."""
    sm = StateManager(session_id="test-session")
    # Should not raise
    snap = await sm.stop_recording("nonexistent-recording-id")
    # State unchanged
    assert snap.recordings_state.active_recording_id is None
    assert snap.recordings_state.recordings == []


@pytest.mark.anyio
async def test_stop_recording_calls_persistence() -> None:
    """stop_recording ruft persistence.mark_recording_stopped auf."""
    from frontprompt.state.persistence.in_memory import InMemoryPersistence

    persistence = InMemoryPersistence()
    sm = StateManager(session_id="test-session", persistence=persistence)

    snap = await sm.start_recording(name="Stop me")
    recording_id = snap.recordings_state.active_recording_id
    assert recording_id is not None

    await sm.stop_recording(recording_id)

    recordings = persistence.load_recordings()
    assert len(recordings) == 1
    assert recordings[0].status == "stopped"


# ---------------------------------------------------------------------------
# rename_recording
# ---------------------------------------------------------------------------


@pytest.mark.anyio
async def test_rename_recording() -> None:
    """rename_recording aktualisiert name + description, broadcastet Snapshot."""
    sm = StateManager(session_id="test-session")
    snap = await sm.start_recording(name="Old Name", description="old desc")
    recording_id = snap.recordings_state.active_recording_id
    assert recording_id is not None

    renamed_snap = await sm.rename_recording(recording_id, name="New Name", description="new desc")

    renamed_meta = next(
        r for r in renamed_snap.recordings_state.recordings if r.recording_id == recording_id
    )
    assert renamed_meta.name == "New Name"
    assert renamed_meta.description == "new desc"


# ---------------------------------------------------------------------------
# select_recording
# ---------------------------------------------------------------------------


@pytest.mark.anyio
async def test_select_recording_sets_detail() -> None:
    """select_recording setzt active_detail_recording_id + lädt full Recording."""
    sm = StateManager(session_id="test-session")
    snap = await sm.start_recording(name="For Detail")
    recording_id = snap.recordings_state.active_recording_id
    assert recording_id is not None
    await sm.stop_recording(recording_id)

    detail_snap = await sm.select_recording(recording_id)

    assert detail_snap.recordings_state.active_detail_recording_id == recording_id
    assert detail_snap.recordings_state.detail_recording is not None
    assert detail_snap.recordings_state.detail_recording.recording_id == recording_id


@pytest.mark.anyio
async def test_select_recording_none_clears_detail() -> None:
    """select_recording(None) löscht active_detail_recording_id + detail_recording."""
    sm = StateManager(session_id="test-session")
    snap = await sm.start_recording(name="For Detail")
    recording_id = snap.recordings_state.active_recording_id
    assert recording_id is not None

    await sm.select_recording(recording_id)
    cleared_snap = await sm.select_recording(None)

    assert cleared_snap.recordings_state.active_detail_recording_id is None
    assert cleared_snap.recordings_state.detail_recording is None


# ---------------------------------------------------------------------------
# append_timeline_entry (COL-5 non-broadcast + Q1 seq ownership)
# ---------------------------------------------------------------------------


@pytest.mark.anyio
async def test_append_timeline_entry_does_not_broadcast(monkeypatch: pytest.MonkeyPatch) -> None:
    """append_timeline_entry darf KEINEN Snapshot-Broadcast auslösen (COL-5)."""
    sm = StateManager(session_id="test-session")
    snap = await sm.start_recording(name="Silent Append")
    recording_id = snap.recordings_state.active_recording_id
    assert recording_id is not None

    broadcast_count = 0

    def counting_listener(s: object) -> None:
        nonlocal broadcast_count
        broadcast_count += 1

    sm.add_snapshot_listener(counting_listener)
    broadcast_count = 0  # reset after listener setup

    entry = _make_page_event(seq=99, timestamp_ms=0)  # seq+timestamp will be overwritten by Python
    await sm.append_timeline_entry(recording_id, entry)

    # No broadcast should have happened
    assert broadcast_count == 0, f"Expected 0 broadcasts, got {broadcast_count}"


@pytest.mark.anyio
async def test_append_timeline_entry_stamps_seq_python_side() -> None:
    """append_timeline_entry stempelt seq = len(entries) atomisch (Q1 — Python owns seq)."""
    sm = StateManager(session_id="test-session")
    snap = await sm.start_recording(name="Seq Test")
    recording_id = snap.recordings_state.active_recording_id
    assert recording_id is not None

    # Append 3 entries with wrong seq values — Python must overwrite them
    for fake_seq in [99, 0, 50]:
        entry = _make_page_event(seq=fake_seq, timestamp_ms=1000)
        await sm.append_timeline_entry(recording_id, entry)

    # Verify the recording has the correct seqs via get_recording
    recording = sm.get_recording(recording_id)
    assert recording is not None
    assert len(recording.entries) == 3
    assert [e.seq for e in recording.entries] == [0, 1, 2]


@pytest.mark.anyio
async def test_append_timeline_entry_monotonic_across_all_kinds() -> None:
    """append_timeline_entry hat einen monotonen Zähler über ALLE Entry-Arten."""
    from frontprompt.state.state import NavigationEntry, PickRefEntry

    sm = StateManager(session_id="test-session")
    snap = await sm.start_recording(name="Multi-Kind Seq")
    recording_id = snap.recordings_state.active_recording_id
    assert recording_id is not None

    click = _make_page_event()
    nav = NavigationEntry(kind="navigation", seq=99, timestamp_ms=2000, from_url="https://a.com", to_url="https://b.com")
    pick_ref = PickRefEntry(kind="pick_ref", seq=99, timestamp_ms=3000, pick_id="pick-001")

    await sm.append_timeline_entry(recording_id, click)
    await sm.append_timeline_entry(recording_id, nav)
    await sm.append_timeline_entry(recording_id, pick_ref)

    recording = sm.get_recording(recording_id)
    assert recording is not None
    seqs = [e.seq for e in recording.entries]
    assert seqs == [0, 1, 2], f"Expected [0, 1, 2], got {seqs}"


# ---------------------------------------------------------------------------
# COL-2 — snapshot includes live recordings_state
# ---------------------------------------------------------------------------


@pytest.mark.anyio
async def test_snapshot_includes_live_recordings_state_col2() -> None:
    """StateSnapshot.recordings_state enthält laufende Aufnahme (COL-2 fix)."""
    sm = StateManager(session_id="test-session")
    snap = await sm.start_recording(name="Visible in Snapshot")

    # snapshot() must surface the live recordings_state
    live_snap = sm.snapshot()
    assert live_snap.recordings_state.active_recording_id is not None
    assert len(live_snap.recordings_state.recordings) == 1
    assert live_snap.recordings_state.recordings[0].name == "Visible in Snapshot"


# ---------------------------------------------------------------------------
# Auto-link: add_pick → PickRefEntry in timeline (COL-6)
# ---------------------------------------------------------------------------


@pytest.mark.anyio
async def test_add_pick_auto_links_pick_ref_when_recording_active() -> None:
    """add_pick während aktiver Aufnahme erzeugt automatisch PickRefEntry im Timeline."""
    sm = StateManager(session_id="test-session")
    snap = await sm.start_recording(name="Pick Recording")
    recording_id = snap.recordings_state.active_recording_id
    assert recording_id is not None

    pick = _make_pick("p-autolink-001")
    await sm.add_pick(pick)

    recording = sm.get_recording(recording_id)
    assert recording is not None
    assert len(recording.entries) == 1
    assert recording.entries[0].kind == "pick_ref"
    assert recording.entries[0].pick_id == "p-autolink-001"  # type: ignore[union-attr]


@pytest.mark.anyio
async def test_add_pick_no_autolink_when_no_recording_active() -> None:
    """add_pick ohne aktive Aufnahme erzeugt keinen Timeline-Eintrag."""
    sm = StateManager(session_id="test-session")

    pick = _make_pick("p-no-autolink")
    await sm.add_pick(pick)

    # No recordings exist, nothing to auto-link
    assert sm.list_recordings_meta() == []


@pytest.mark.anyio
async def test_add_pick_from_programmatic_source_auto_links_col6() -> None:
    """add_pick_from_programmatic_source während aktiver Aufnahme erzeugt PickRefEntry (COL-6)."""
    sm = StateManager(session_id="test-session")
    snap = await sm.start_recording(name="Programmatic Pick Recording")
    recording_id = snap.recordings_state.active_recording_id
    assert recording_id is not None

    pick = _make_pick("p-programmatic-001")
    await sm.add_pick_from_programmatic_source(pick)

    recording = sm.get_recording(recording_id)
    assert recording is not None
    assert len(recording.entries) == 1
    assert recording.entries[0].kind == "pick_ref"
    assert recording.entries[0].pick_id == "p-programmatic-001"  # type: ignore[union-attr]


@pytest.mark.anyio
async def test_add_region_auto_links_region_ref_when_recording_active() -> None:
    """add_region während aktiver Aufnahme erzeugt automatisch RegionRefEntry im Timeline."""
    sm = StateManager(session_id="test-session")
    snap = await sm.start_recording(name="Region Recording")
    recording_id = snap.recordings_state.active_recording_id
    assert recording_id is not None

    region = _make_region("r-autolink-001")
    await sm.add_region(region)

    recording = sm.get_recording(recording_id)
    assert recording is not None
    assert len(recording.entries) == 1
    assert recording.entries[0].kind == "region_ref"
    assert recording.entries[0].region_id == "r-autolink-001"  # type: ignore[union-attr]


@pytest.mark.anyio
async def test_add_relation_auto_links_relation_ref_when_recording_active() -> None:
    """add_relation während aktiver Aufnahme erzeugt automatisch RelationRefEntry im Timeline."""
    sm = StateManager(session_id="test-session")
    snap = await sm.start_recording(name="Relation Recording")
    recording_id = snap.recordings_state.active_recording_id
    assert recording_id is not None

    # Add picks first so relation endpoints exist
    pick1 = _make_pick("p-001")
    pick2 = _make_pick("p-002")
    await sm.add_pick(pick1)
    await sm.add_pick(pick2)

    relation = _make_relation("p-001", "p-002")
    await sm.add_relation(relation)

    recording = sm.get_recording(recording_id)
    assert recording is not None
    # Should have pick_ref for p-001, pick_ref for p-002, relation_ref for rel-001
    relation_refs = [e for e in recording.entries if e.kind == "relation_ref"]
    assert len(relation_refs) == 1
    assert relation_refs[0].relation_id == "rel-001"  # type: ignore[union-attr]


# ---------------------------------------------------------------------------
# Read methods: get_recording + list_recordings_meta
# ---------------------------------------------------------------------------


@pytest.mark.anyio
async def test_get_recording_returns_full_recording() -> None:
    """get_recording(id) gibt das vollständige Recording-Objekt zurück."""
    sm = StateManager(session_id="test-session")
    snap = await sm.start_recording(name="Fetchable")
    recording_id = snap.recordings_state.active_recording_id
    assert recording_id is not None

    recording = sm.get_recording(recording_id)
    assert recording is not None
    assert recording.recording_id == recording_id
    assert recording.name == "Fetchable"


@pytest.mark.anyio
async def test_get_recording_unknown_returns_none() -> None:
    """get_recording mit unbekannter ID gibt None zurück."""
    sm = StateManager(session_id="test-session")
    assert sm.get_recording("nonexistent") is None


@pytest.mark.anyio
async def test_list_recordings_meta() -> None:
    """list_recordings_meta() gibt Liste der RecordingMeta zurück."""
    sm = StateManager(session_id="test-session")
    assert sm.list_recordings_meta() == []

    await sm.start_recording(name="A")
    metas = sm.list_recordings_meta()
    assert len(metas) == 1
    assert metas[0].name == "A"
