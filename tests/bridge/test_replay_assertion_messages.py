"""Wire-message tests für die Replay-Assertion bridge envelopes (sub-plan 02).

Covers the 3 new ReplayBridgeMessages from contracts.md:
  - AssertionAddedToRecordingRequested
  - AssertionDeletedRequested
  - AssertionUpdatedRequested

Schema version bump 0.8.0 → 0.9.0 verified here.
OutboundMessage discriminated union routing + regression guard.
"""

from __future__ import annotations

import pytest
from pydantic import TypeAdapter, ValidationError

_OUTBOUND_ADAPTER: TypeAdapter[object] | None = None


def _outbound() -> TypeAdapter[object]:
    global _OUTBOUND_ADAPTER
    if _OUTBOUND_ADAPTER is None:
        from frontprompt.bridge.messages import OutboundMessage

        _OUTBOUND_ADAPTER = TypeAdapter(OutboundMessage)
    return _OUTBOUND_ADAPTER


# ---------------------------------------------------------------------------
# Schema version bump
# ---------------------------------------------------------------------------


def test_schema_version_bumped_to_0_9_0() -> None:
    """Bridge SCHEMA_VERSION is 0.9.0 after sub-plan 02."""
    from frontprompt.bridge.messages import SCHEMA_VERSION

    assert SCHEMA_VERSION == "0.9.0"


# ---------------------------------------------------------------------------
# AssertionAddedToRecordingRequested — append (insert_after_seq=None)
# ---------------------------------------------------------------------------


def test_assertion_added_append_roundtrip() -> None:
    """insert_after_seq=None means append — round-trip preserves all fields."""
    from frontprompt.bridge.messages import AssertionAddedToRecordingRequested

    msg = AssertionAddedToRecordingRequested(
        recording_id="rec-1",
        assertion={
            "assertion_id": "asr-1",
            "assertion_type": "selector_exists",
            "target": "button#submit",
            "target_kind": "selector",
            "expected": None,
            "comparator": "none",
            "description": "Submit button exists",
        },
        insert_after_seq=None,
    )
    assert msg.kind == "assertion_added_to_recording_requested"
    assert msg.recording_id == "rec-1"
    assert msg.insert_after_seq is None
    assert msg.assertion["assertion_id"] == "asr-1"


def test_assertion_added_insert_with_seq() -> None:
    """insert_after_seq=5 means insert after seq 5."""
    from frontprompt.bridge.messages import AssertionAddedToRecordingRequested

    msg = AssertionAddedToRecordingRequested(
        recording_id="rec-1",
        assertion={
            "assertion_id": "asr-2",
            "assertion_type": "text_equals",
            "target": "h1.title",
            "target_kind": "selector",
            "expected": "Welcome",
            "comparator": "equals",
            "description": "Title is Welcome",
        },
        insert_after_seq=5,
    )
    assert msg.insert_after_seq == 5
    assert msg.assertion["expected"] == "Welcome"


def test_assertion_added_routes_via_outbound() -> None:
    """OutboundMessage union routes assertion_added_to_recording_requested correctly."""
    from frontprompt.bridge.messages import AssertionAddedToRecordingRequested

    payload = {
        "kind": "assertion_added_to_recording_requested",
        "schema_version": "0.9.0",
        "recording_id": "rec-1",
        "assertion": {
            "assertion_id": "asr-1",
            "assertion_type": "selector_exists",
            "target": "button",
            "target_kind": "selector",
            "expected": None,
            "comparator": "none",
            "description": "Button exists",
        },
        "insert_after_seq": None,
    }
    msg = _outbound().validate_python(payload)
    assert isinstance(msg, AssertionAddedToRecordingRequested)
    assert msg.recording_id == "rec-1"


def test_assertion_added_json_roundtrip() -> None:
    """JSON serialize + deserialize AssertionAddedToRecordingRequested."""
    from frontprompt.bridge.messages import AssertionAddedToRecordingRequested

    msg = AssertionAddedToRecordingRequested(
        recording_id="rec-1",
        assertion={
            "assertion_id": "asr-3",
            "assertion_type": "url_equals",
            "target": "",
            "target_kind": "url",
            "expected": "https://example.com/",
            "comparator": "equals",
            "description": "URL check",
        },
        insert_after_seq=3,
    )
    dumped = _outbound().dump_json(msg).decode("utf-8")
    restored = _outbound().validate_json(dumped)
    assert isinstance(restored, AssertionAddedToRecordingRequested)
    assert restored.insert_after_seq == 3
    assert restored.assertion["assertion_type"] == "url_equals"


# ---------------------------------------------------------------------------
# AssertionDeletedRequested
# ---------------------------------------------------------------------------


def test_assertion_deleted_roundtrip() -> None:
    """AssertionDeletedRequested round-trip with valid assertion_id."""
    from frontprompt.bridge.messages import AssertionDeletedRequested

    msg = AssertionDeletedRequested(recording_id="rec-1", assertion_id="asr-42")
    assert msg.kind == "assertion_deleted_requested"
    assert msg.recording_id == "rec-1"
    assert msg.assertion_id == "asr-42"
    assert msg.schema_version == "0.9.0"


def test_assertion_deleted_routes_via_outbound() -> None:
    """OutboundMessage union routes assertion_deleted_requested correctly."""
    from frontprompt.bridge.messages import AssertionDeletedRequested

    payload = {
        "kind": "assertion_deleted_requested",
        "schema_version": "0.9.0",
        "recording_id": "rec-1",
        "assertion_id": "asr-42",
    }
    msg = _outbound().validate_python(payload)
    assert isinstance(msg, AssertionDeletedRequested)
    assert msg.assertion_id == "asr-42"


def test_assertion_deleted_missing_assertion_id_fails() -> None:
    """assertion_id is required — missing raises ValidationError."""
    with pytest.raises(ValidationError):
        _outbound().validate_python(
            {
                "kind": "assertion_deleted_requested",
                "schema_version": "0.9.0",
                "recording_id": "rec-1",
            }
        )


# ---------------------------------------------------------------------------
# AssertionUpdatedRequested
# ---------------------------------------------------------------------------


def test_assertion_updated_all_fields_none_is_valid() -> None:
    """All patch fields None is a valid no-op patch."""
    from frontprompt.bridge.messages import AssertionUpdatedRequested

    msg = AssertionUpdatedRequested(
        recording_id="rec-1",
        assertion_id="asr-1",
        assertion_type=None,
        target=None,
        expected=None,
        description=None,
    )
    assert msg.kind == "assertion_updated_requested"
    assert msg.assertion_type is None
    assert msg.target is None
    assert msg.expected is None
    assert msg.description is None


def test_assertion_updated_partial_patch_expected_only() -> None:
    """Partial patch with only expected set — other fields remain None."""
    from frontprompt.bridge.messages import AssertionUpdatedRequested

    msg = AssertionUpdatedRequested(
        recording_id="rec-1",
        assertion_id="asr-1",
        assertion_type=None,
        target=None,
        expected="New Expected Value",
        description=None,
    )
    assert msg.expected == "New Expected Value"
    assert msg.assertion_type is None
    assert msg.target is None
    assert msg.description is None


def test_assertion_updated_routes_via_outbound() -> None:
    """OutboundMessage union routes assertion_updated_requested correctly."""
    from frontprompt.bridge.messages import AssertionUpdatedRequested

    payload = {
        "kind": "assertion_updated_requested",
        "schema_version": "0.9.0",
        "recording_id": "rec-1",
        "assertion_id": "asr-1",
        "assertion_type": "text_contains",
        "target": "p.content",
        "expected": "Hello",
        "description": "Updated description",
    }
    msg = _outbound().validate_python(payload)
    assert isinstance(msg, AssertionUpdatedRequested)
    assert msg.assertion_type == "text_contains"
    assert msg.target == "p.content"
    assert msg.expected == "Hello"
    assert msg.description == "Updated description"


def test_assertion_updated_json_roundtrip() -> None:
    """JSON serialize + deserialize AssertionUpdatedRequested."""
    from frontprompt.bridge.messages import AssertionUpdatedRequested

    msg = AssertionUpdatedRequested(
        recording_id="rec-1",
        assertion_id="asr-5",
        assertion_type="visible",
        target="div#modal",
        expected=None,
        description=None,
    )
    dumped = _outbound().dump_json(msg).decode("utf-8")
    restored = _outbound().validate_json(dumped)
    assert isinstance(restored, AssertionUpdatedRequested)
    assert restored.assertion_type == "visible"
    assert restored.target == "div#modal"


# ---------------------------------------------------------------------------
# Codegen roots — 3 new classes must be in __codegen_roots__
# ---------------------------------------------------------------------------


def test_replay_assertion_message_classes_in_codegen_roots() -> None:
    """All 3 new replay assertion bridge message classes are in __codegen_roots__."""
    from frontprompt.bridge.messages import __codegen_roots__

    expected = [
        "AssertionAddedToRecordingRequested",
        "AssertionDeletedRequested",
        "AssertionUpdatedRequested",
    ]
    for name in expected:
        assert name in __codegen_roots__, f"{name} missing in __codegen_roots__"


# ---------------------------------------------------------------------------
# Regression — existing outbound variants still resolve correctly
# ---------------------------------------------------------------------------


def test_existing_outbound_variants_still_route() -> None:
    """Regression guard: existing kinds are unaffected by the new union entries."""
    from frontprompt.bridge.messages import (
        RecordingStartRequested,
        RecordingStopRequested,
        RecordedEventCapturedRequested,
    )

    cases = [
        (
            {"kind": "recording_start_requested", "schema_version": "0.8.0"},
            RecordingStartRequested,
        ),
        (
            {
                "kind": "recording_stop_requested",
                "schema_version": "0.8.0",
                "recording_id": "rec-1",
            },
            RecordingStopRequested,
        ),
    ]
    for payload, expected_cls in cases:
        msg = _outbound().validate_python(payload)
        assert isinstance(msg, expected_cls), f"Expected {expected_cls.__name__}, got {type(msg).__name__}"
