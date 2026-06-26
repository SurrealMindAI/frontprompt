"""Wire-message tests für die Recording-feature Envelopes (sub-plan 02).

Discriminated-union routing via ``kind``-field. Roundtrip per envelope-class.
Tests exercise the 5 new RecordingBridgeMessages per contracts.md.
"""

from __future__ import annotations

import pytest
from pydantic import TypeAdapter, ValidationError

from frontprompt.state.state import PageEventEntry

_OUTBOUND_ADAPTER: TypeAdapter[object] | None = None


def _outbound() -> TypeAdapter[object]:
    global _OUTBOUND_ADAPTER
    if _OUTBOUND_ADAPTER is None:
        from frontprompt.bridge.messages import OutboundMessage

        _OUTBOUND_ADAPTER = TypeAdapter(OutboundMessage)
    return _OUTBOUND_ADAPTER


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
# Schema version bump
# ---------------------------------------------------------------------------


def test_schema_version_bumped_to_0_10_0() -> None:
    """Schema 0.10.0 — + Voice-Over-Feature (voice-over sub-plan 02); 0.9.0 + Replay-Assertion-Authoring."""
    from frontprompt.bridge.messages import SCHEMA_VERSION

    assert SCHEMA_VERSION == "0.10.0"


# ---------------------------------------------------------------------------
# RecordingStartRequested
# ---------------------------------------------------------------------------


def test_recording_start_requested_defaults() -> None:
    """Default name='New Recording' and description='' are valid and roundtrip."""
    from frontprompt.bridge.messages import RecordingStartRequested

    msg = RecordingStartRequested()
    assert msg.kind == "recording_start_requested"
    assert msg.name == "New Recording"
    assert msg.description == ""
    assert msg.schema_version == "0.10.0"


def test_recording_start_requested_custom_fields() -> None:
    """Custom name/description are preserved."""
    from frontprompt.bridge.messages import RecordingStartRequested

    msg = RecordingStartRequested(name="Login Flow", description="Tests auth")
    assert msg.name == "Login Flow"
    assert msg.description == "Tests auth"


def test_recording_start_requested_routes_via_outbound() -> None:
    """OutboundMessage union routes kind='recording_start_requested' correctly."""
    from frontprompt.bridge.messages import RecordingStartRequested

    payload = {"kind": "recording_start_requested", "schema_version": "0.8.0"}
    msg = _outbound().validate_python(payload)
    assert isinstance(msg, RecordingStartRequested)


def test_recording_start_requested_json_roundtrip() -> None:
    from frontprompt.bridge.messages import RecordingStartRequested

    msg = RecordingStartRequested(name="Checkout", description="basket → confirm")
    dumped = _outbound().dump_json(msg).decode("utf-8")
    restored = _outbound().validate_json(dumped)
    assert isinstance(restored, RecordingStartRequested)
    assert restored.name == "Checkout"
    assert restored.description == "basket → confirm"


# ---------------------------------------------------------------------------
# RecordingStopRequested
# ---------------------------------------------------------------------------


def test_recording_stop_requested_requires_non_empty_recording_id() -> None:
    """recording_id is a required non-empty string."""
    from frontprompt.bridge.messages import RecordingStopRequested

    msg = RecordingStopRequested(recording_id="rec-uuid-1")
    assert msg.recording_id == "rec-uuid-1"


def test_recording_stop_requested_routes_via_outbound() -> None:
    from frontprompt.bridge.messages import RecordingStopRequested

    payload = {
        "kind": "recording_stop_requested",
        "schema_version": "0.8.0",
        "recording_id": "rec-uuid-1",
    }
    msg = _outbound().validate_python(payload)
    assert isinstance(msg, RecordingStopRequested)
    assert msg.recording_id == "rec-uuid-1"


def test_recording_stop_requested_missing_recording_id_fails() -> None:
    """recording_id is required — missing raises ValidationError."""
    with pytest.raises(ValidationError):
        _outbound().validate_python(
            {"kind": "recording_stop_requested", "schema_version": "0.8.0"}
        )


# ---------------------------------------------------------------------------
# RecordingRenameRequested
# ---------------------------------------------------------------------------


def test_recording_rename_requested_carries_all_fields() -> None:
    """recording_id, name, description all required and preserved."""
    from frontprompt.bridge.messages import RecordingRenameRequested

    msg = RecordingRenameRequested(
        recording_id="rec-uuid-1", name="Renamed Flow", description="New desc"
    )
    assert msg.recording_id == "rec-uuid-1"
    assert msg.name == "Renamed Flow"
    assert msg.description == "New desc"


def test_recording_rename_requested_routes_via_outbound() -> None:
    from frontprompt.bridge.messages import RecordingRenameRequested

    payload = {
        "kind": "recording_rename_requested",
        "schema_version": "0.8.0",
        "recording_id": "rec-1",
        "name": "New Name",
        "description": "",
    }
    msg = _outbound().validate_python(payload)
    assert isinstance(msg, RecordingRenameRequested)
    assert msg.name == "New Name"


# ---------------------------------------------------------------------------
# RecordingSelectedRequested
# ---------------------------------------------------------------------------


def test_recording_selected_requested_with_id() -> None:
    """recording_id may be a string (select a recording for detail view)."""
    from frontprompt.bridge.messages import RecordingSelectedRequested

    msg = RecordingSelectedRequested(recording_id="rec-uuid-1")
    assert msg.recording_id == "rec-uuid-1"


def test_recording_selected_requested_with_none_deselect() -> None:
    """recording_id=None is valid — means deselect detail."""
    from frontprompt.bridge.messages import RecordingSelectedRequested

    msg = RecordingSelectedRequested(recording_id=None)
    assert msg.recording_id is None


def test_recording_selected_requested_routes_via_outbound() -> None:
    from frontprompt.bridge.messages import RecordingSelectedRequested

    # With an id
    msg = _outbound().validate_python(
        {
            "kind": "recording_selected_requested",
            "schema_version": "0.8.0",
            "recording_id": "rec-1",
        }
    )
    assert isinstance(msg, RecordingSelectedRequested)
    assert msg.recording_id == "rec-1"

    # With null (deselect)
    msg2 = _outbound().validate_python(
        {
            "kind": "recording_selected_requested",
            "schema_version": "0.8.0",
            "recording_id": None,
        }
    )
    assert isinstance(msg2, RecordingSelectedRequested)
    assert msg2.recording_id is None


# ---------------------------------------------------------------------------
# RecordedEventCapturedRequested
# ---------------------------------------------------------------------------


def test_recorded_event_captured_requested_roundtrip() -> None:
    """entry carries PageEventEntry payload without seq (Python stamps seq)."""
    from frontprompt.bridge.messages import RecordedEventCapturedRequested

    entry = _make_page_event_entry(event_type="click", target="div#app", key=None)
    msg = RecordedEventCapturedRequested(recording_id="rec-uuid-1", entry=entry)
    assert msg.recording_id == "rec-uuid-1"
    assert msg.entry.kind == "page_event"
    assert msg.entry.event_type == "click"
    assert msg.entry.target == "div#app"


def test_recorded_event_captured_requested_routes_via_outbound() -> None:
    from frontprompt.bridge.messages import RecordedEventCapturedRequested

    entry = _make_page_event_entry()
    payload = {
        "kind": "recorded_event_captured_requested",
        "schema_version": "0.8.0",
        "recording_id": "rec-uuid-1",
        "entry": entry.model_dump(mode="json"),
    }
    msg = _outbound().validate_python(payload)
    assert isinstance(msg, RecordedEventCapturedRequested)
    assert msg.entry.event_type == "click"


def test_recorded_event_captured_requested_json_roundtrip() -> None:
    from frontprompt.bridge.messages import RecordedEventCapturedRequested

    entry = _make_page_event_entry(event_type="keydown", key="Enter")
    msg = RecordedEventCapturedRequested(recording_id="rec-uuid-1", entry=entry)
    dumped = _outbound().dump_json(msg).decode("utf-8")
    restored = _outbound().validate_json(dumped)
    assert isinstance(restored, RecordedEventCapturedRequested)
    assert restored.entry.key == "Enter"
    assert restored.entry.event_type == "keydown"


def test_recorded_event_captured_missing_recording_id_fails() -> None:
    with pytest.raises(ValidationError):
        _outbound().validate_python(
            {
                "kind": "recorded_event_captured_requested",
                "schema_version": "0.8.0",
                "entry": _make_page_event_entry().model_dump(mode="json"),
            }
        )


# ---------------------------------------------------------------------------
# Codegen roots — all 5 new classes must be in __codegen_roots__
# ---------------------------------------------------------------------------


def test_recording_message_classes_in_codegen_roots() -> None:
    """All 5 new recording bridge message classes are in __codegen_roots__."""
    from frontprompt.bridge.messages import __codegen_roots__

    expected = [
        "RecordingStartRequested",
        "RecordingStopRequested",
        "RecordingRenameRequested",
        "RecordingSelectedRequested",
        "RecordedEventCapturedRequested",
    ]
    for name in expected:
        assert name in __codegen_roots__, f"{name} missing in __codegen_roots__"


# ---------------------------------------------------------------------------
# Regression — existing outbound variants still resolve correctly
# ---------------------------------------------------------------------------


def test_existing_outbound_variants_still_route() -> None:
    """Regression guard: existing kinds are unaffected by the new union entries."""
    from frontprompt.bridge.messages import (
        InspectorActivateRequested,
        OverlayReady,
        PanelToggleRequested,
        RegionCreatedRequested,
        RelationCreatedRequested,
    )

    cases = [
        ({"kind": "inspector_activate_requested", "schema_version": "0.7.0"}, InspectorActivateRequested),
        (
            {"kind": "overlay_ready", "schema_version": "0.7.0", "bundle_build_session": "s-1"},
            OverlayReady,
        ),
        (
            {"kind": "panel_toggle_requested", "schema_version": "0.7.0", "panel_id": "left"},
            PanelToggleRequested,
        ),
    ]
    for payload, expected_cls in cases:
        msg = _outbound().validate_python(payload)
        assert isinstance(msg, expected_cls), f"Expected {expected_cls.__name__}, got {type(msg).__name__}"
