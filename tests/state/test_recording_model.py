"""Tests für Recording-Domänen-Modelle in state.py — Section 1 TDD (sub-plan 01).

Deckt: RecordingStatus, TimelineEntry-Varianten, Recording, RecordingMeta,
RecordingsState, StateSnapshot-Erweiterung (Schema 0.8.0) + forward-compat.
"""

from __future__ import annotations

import pytest
from pydantic import ValidationError


# ---------------------------------------------------------------------------
# RecordingStatus
# ---------------------------------------------------------------------------


def test_recording_status_accepts_active() -> None:
    """RecordingStatus Literal akzeptiert 'active'."""
    from frontprompt.state.state import RecordingStatus

    # Pydantic-Literal-Validierung über TypeAdapter
    from pydantic import TypeAdapter

    ta: TypeAdapter[RecordingStatus] = TypeAdapter(RecordingStatus)
    assert ta.validate_python("active") == "active"


def test_recording_status_accepts_stopped() -> None:
    from frontprompt.state.state import RecordingStatus
    from pydantic import TypeAdapter

    ta: TypeAdapter[RecordingStatus] = TypeAdapter(RecordingStatus)
    assert ta.validate_python("stopped") == "stopped"


def test_recording_status_rejects_invalid() -> None:
    from frontprompt.state.state import RecordingStatus
    from pydantic import TypeAdapter

    ta: TypeAdapter[RecordingStatus] = TypeAdapter(RecordingStatus)
    with pytest.raises(ValidationError):
        ta.validate_python("recording")  # not a valid status


# ---------------------------------------------------------------------------
# PageEventEntry
# ---------------------------------------------------------------------------


def _make_page_event_entry(event_type: str = "click", seq: int = 0, timestamp_ms: int = 1000) -> dict:
    return {
        "kind": "page_event",
        "seq": seq,
        "timestamp_ms": timestamp_ms,
        "event_type": event_type,
        "target": "button#submit.btn",
        "target_path": ["html", "body", "main", "form", "button"],
        "default_prevented": False,
        "key": None,
    }


def test_page_event_entry_click_roundtrip() -> None:
    """PageEventEntry mit event_type='click' serialisiert/deserialisiert korrekt."""
    from frontprompt.state.state import PageEventEntry

    entry = PageEventEntry(**_make_page_event_entry("click"))
    assert entry.kind == "page_event"
    assert entry.event_type == "click"
    assert entry.seq == 0
    assert entry.timestamp_ms == 1000
    assert entry.target == "button#submit.btn"
    assert entry.default_prevented is False
    assert entry.key is None

    restored = PageEventEntry.model_validate_json(entry.model_dump_json())
    assert restored == entry


def test_page_event_entry_keydown_with_key() -> None:
    from frontprompt.state.state import PageEventEntry

    data = _make_page_event_entry("keydown")
    data["key"] = "Enter"
    entry = PageEventEntry(**data)
    assert entry.event_type == "keydown"
    assert entry.key == "Enter"

    restored = PageEventEntry.model_validate_json(entry.model_dump_json())
    assert restored.key == "Enter"


def test_page_event_entry_rejects_wheel() -> None:
    """wheel ist explizit ausgeschlossen — nur click/pointerdown/keydown erlaubt."""
    from frontprompt.state.state import PageEventEntry

    with pytest.raises(ValidationError):
        PageEventEntry(**_make_page_event_entry("wheel"))


def test_page_event_entry_rejects_scroll() -> None:
    from frontprompt.state.state import PageEventEntry

    with pytest.raises(ValidationError):
        PageEventEntry(**_make_page_event_entry("scroll"))


# ---------------------------------------------------------------------------
# PickRefEntry
# ---------------------------------------------------------------------------


def test_pick_ref_entry_roundtrip() -> None:
    """PickRefEntry round-trip mit valid uuid4 pick_id."""
    from frontprompt.state.state import PickRefEntry

    entry = PickRefEntry(
        kind="pick_ref",
        seq=1,
        timestamp_ms=2000,
        pick_id="550e8400-e29b-41d4-a716-446655440000",
    )
    assert entry.kind == "pick_ref"
    assert entry.pick_id == "550e8400-e29b-41d4-a716-446655440000"

    restored = PickRefEntry.model_validate_json(entry.model_dump_json())
    assert restored == entry


# ---------------------------------------------------------------------------
# RegionRefEntry
# ---------------------------------------------------------------------------


def test_region_ref_entry_roundtrip() -> None:
    from frontprompt.state.state import RegionRefEntry

    entry = RegionRefEntry(
        kind="region_ref",
        seq=2,
        timestamp_ms=3000,
        region_id="region-uuid-001",
    )
    assert entry.kind == "region_ref"
    restored = RegionRefEntry.model_validate_json(entry.model_dump_json())
    assert restored == entry


# ---------------------------------------------------------------------------
# RelationRefEntry
# ---------------------------------------------------------------------------


def test_relation_ref_entry_roundtrip() -> None:
    from frontprompt.state.state import RelationRefEntry

    entry = RelationRefEntry(
        kind="relation_ref",
        seq=3,
        timestamp_ms=4000,
        relation_id="relation-uuid-001",
    )
    assert entry.kind == "relation_ref"
    restored = RelationRefEntry.model_validate_json(entry.model_dump_json())
    assert restored == entry


# ---------------------------------------------------------------------------
# NavigationEntry
# ---------------------------------------------------------------------------


def test_navigation_entry_roundtrip() -> None:
    from frontprompt.state.state import NavigationEntry

    entry = NavigationEntry(
        kind="navigation",
        seq=4,
        timestamp_ms=5000,
        from_url="https://example.com/page1",
        to_url="https://example.com/page2",
    )
    assert entry.kind == "navigation"
    assert entry.from_url == "https://example.com/page1"
    assert entry.to_url == "https://example.com/page2"

    restored = NavigationEntry.model_validate_json(entry.model_dump_json())
    assert restored == entry


# ---------------------------------------------------------------------------
# TimelineEntry — discriminated union
# ---------------------------------------------------------------------------


def test_timeline_entry_routes_page_event() -> None:
    """TimelineEntry union discriminated by 'kind' routed to PageEventEntry."""
    from pydantic import TypeAdapter

    from frontprompt.state.state import PageEventEntry, TimelineEntry

    ta: TypeAdapter[TimelineEntry] = TypeAdapter(TimelineEntry)
    data = _make_page_event_entry("pointerdown")
    result = ta.validate_python(data)
    assert isinstance(result, PageEventEntry)
    assert result.event_type == "pointerdown"


def test_timeline_entry_routes_pick_ref() -> None:
    from pydantic import TypeAdapter

    from frontprompt.state.state import PickRefEntry, TimelineEntry

    ta: TypeAdapter[TimelineEntry] = TypeAdapter(TimelineEntry)
    result = ta.validate_python({"kind": "pick_ref", "seq": 0, "timestamp_ms": 1000, "pick_id": "p-001"})
    assert isinstance(result, PickRefEntry)


def test_timeline_entry_routes_navigation() -> None:
    from pydantic import TypeAdapter

    from frontprompt.state.state import NavigationEntry, TimelineEntry

    ta: TypeAdapter[TimelineEntry] = TypeAdapter(TimelineEntry)
    result = ta.validate_python(
        {"kind": "navigation", "seq": 5, "timestamp_ms": 6000, "from_url": "https://a.com", "to_url": "https://b.com"}
    )
    assert isinstance(result, NavigationEntry)


# ---------------------------------------------------------------------------
# Recording
# ---------------------------------------------------------------------------


def test_recording_accepts_positive_started_at_ms() -> None:
    from frontprompt.state.state import Recording

    rec = Recording(
        recording_id="rec-001",
        name="My Recording",
        status="active",
        started_at_ms=1_700_000_000_000,
    )
    assert rec.started_at_ms == 1_700_000_000_000
    assert rec.entries == []
    assert rec.ended_at_ms is None
    assert rec.description == ""
    assert rec.origin_session is None


def test_recording_roundtrip_with_entries() -> None:
    from frontprompt.state.state import NavigationEntry, PageEventEntry, Recording

    nav = NavigationEntry(kind="navigation", seq=0, timestamp_ms=1000, from_url="https://a.com", to_url="https://b.com")
    click = PageEventEntry(**_make_page_event_entry("click", seq=1, timestamp_ms=2000))

    rec = Recording(
        recording_id="rec-002",
        name="Test",
        status="active",
        started_at_ms=500,
        entries=[nav, click],
    )
    restored = Recording.model_validate_json(rec.model_dump_json())
    assert len(restored.entries) == 2
    assert restored.entries[0].kind == "navigation"
    assert restored.entries[1].kind == "page_event"


def test_recording_stopped_has_ended_at_ms() -> None:
    from frontprompt.state.state import Recording

    rec = Recording(
        recording_id="rec-003",
        name="Done",
        status="stopped",
        started_at_ms=1000,
        ended_at_ms=2000,
    )
    assert rec.status == "stopped"
    assert rec.ended_at_ms == 2000


# ---------------------------------------------------------------------------
# RecordingMeta
# ---------------------------------------------------------------------------


def test_recording_meta_entry_count_non_negative() -> None:
    from frontprompt.state.state import RecordingMeta

    meta = RecordingMeta(
        recording_id="rec-001",
        name="Test",
        status="active",
        started_at_ms=1000,
        entry_count=0,
    )
    assert meta.entry_count == 0


def test_recording_meta_rejects_negative_entry_count() -> None:
    from frontprompt.state.state import RecordingMeta

    with pytest.raises(ValidationError):
        RecordingMeta(
            recording_id="rec-001",
            name="Test",
            status="active",
            started_at_ms=1000,
            entry_count=-1,
        )


def test_recording_meta_roundtrip() -> None:
    from frontprompt.state.state import RecordingMeta

    meta = RecordingMeta(
        recording_id="rec-004",
        name="My Recording",
        description="A description",
        status="stopped",
        started_at_ms=1000,
        ended_at_ms=5000,
        entry_count=42,
    )
    restored = RecordingMeta.model_validate_json(meta.model_dump_json())
    assert restored == meta


# ---------------------------------------------------------------------------
# RecordingsState
# ---------------------------------------------------------------------------


def test_recordings_state_defaults_no_detail() -> None:
    """RecordingsState default: kein active recording, leere Liste, kein detail."""
    from frontprompt.state.state import RecordingsState

    state = RecordingsState()
    assert state.active_recording_id is None
    assert state.recordings == []
    assert state.active_detail_recording_id is None
    assert state.detail_recording is None


def test_recordings_state_with_detail_recording() -> None:
    """RecordingsState mit detail_recording und matching active_detail_recording_id."""
    from frontprompt.state.state import Recording, RecordingMeta, RecordingsState

    rec = Recording(
        recording_id="rec-detail-001",
        name="Detail Rec",
        status="stopped",
        started_at_ms=1000,
        ended_at_ms=2000,
    )
    meta = RecordingMeta(
        recording_id="rec-detail-001",
        name="Detail Rec",
        status="stopped",
        started_at_ms=1000,
        ended_at_ms=2000,
        entry_count=0,
    )
    state = RecordingsState(
        active_recording_id=None,
        recordings=[meta],
        active_detail_recording_id="rec-detail-001",
        detail_recording=rec,
    )
    assert state.active_detail_recording_id == "rec-detail-001"
    assert state.detail_recording is not None
    assert state.detail_recording.recording_id == "rec-detail-001"


def test_recordings_state_roundtrip() -> None:
    from frontprompt.state.state import RecordingMeta, RecordingsState

    meta = RecordingMeta(
        recording_id="rec-rt-001",
        name="RT",
        status="active",
        started_at_ms=1000,
        entry_count=5,
    )
    state = RecordingsState(active_recording_id="rec-rt-001", recordings=[meta])
    restored = RecordingsState.model_validate_json(state.model_dump_json())
    assert restored.active_recording_id == "rec-rt-001"
    assert len(restored.recordings) == 1


# ---------------------------------------------------------------------------
# StateSnapshot — 0.8.0 + forward-compat
# ---------------------------------------------------------------------------


def test_state_snapshot_schema_version_is_current() -> None:
    """StateSnapshot default schema_version muss dem aktuellen Wert entsprechen.

    History: 0.8.0 (recorder sub-plan 01) → 0.9.0 (replay sub-plan 01, AssertionEntry +
    ParameterDeclaration + RecordingsState.active_replay_progress) →
    0.10.0 (voice-over sub-plan 01, TranscriptSegmentEntry + MicrophoneState +
    SettingsState + TranscriptionState) →
    0.11.0 (model-catalog sub-plan 01, TranscriptionModelSpec +
    SettingsState.mlx_whisper_model_id + TranscriptionBackendInfo.available_models +
    TranscriptionBackendInfo.selected_model_id).
    """
    from frontprompt.state.state import PanelStateView, PanelView, StateSnapshot

    panel = PanelStateView(
        top=PanelView(open=True, size=56),
        bottom=PanelView(open=False, size=220),
        left=PanelView(open=True, size=300),
        right=PanelView(open=True, size=340),
    )
    snap = StateSnapshot(panel_state=panel)
    assert snap.schema_version == "0.11.0"


def test_state_snapshot_includes_recordings_state_field() -> None:
    """StateSnapshot hat ein 'recordings_state' Feld mit default RecordingsState."""
    from frontprompt.state.state import PanelStateView, PanelView, StateSnapshot

    panel = PanelStateView(
        top=PanelView(open=True, size=56),
        bottom=PanelView(open=False, size=220),
        left=PanelView(open=True, size=300),
        right=PanelView(open=True, size=340),
    )
    snap = StateSnapshot(panel_state=panel)
    assert hasattr(snap, "recordings_state")
    assert snap.recordings_state.active_recording_id is None
    assert snap.recordings_state.recordings == []


def test_state_snapshot_0_7_0_without_recordings_state_forward_compat() -> None:
    """Alte StateSnapshot-JSON ohne 'recordings_state' deserialisiert ohne Fehler (forward-compat)."""
    import json

    from frontprompt.state.state import StateSnapshot

    # Minimal 0.7.0 payload — no recordings_state key
    old_payload = {
        "schema_version": "0.7.0",
        "panel_state": {
            "top": {"open": True, "size": 56},
            "bottom": {"open": False, "size": 220},
            "left": {"open": True, "size": 300},
            "right": {"open": True, "size": 340},
        },
        "inspector_state": {
            "active": False,
            "picks": [],
            "active_pick_id": None,
            "regions": [],
            "active_region_id": None,
            "relations": [],
        },
    }
    snap = StateSnapshot.model_validate_json(json.dumps(old_payload))
    # recordings_state defaults to empty RecordingsState via default_factory
    assert snap.recordings_state.active_recording_id is None
    assert snap.recordings_state.recordings == []
