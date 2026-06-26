"""Wire-message tests für die Inspector/Pick-Flow Envelopes.

Discriminated-union routing via ``kind``-field. Roundtrip per envelope-class.
"""

from __future__ import annotations

import pytest
from pydantic import TypeAdapter, ValidationError

from frontprompt.bridge.messages import (
    SCHEMA_VERSION,
    HideAllPanelsRequested,
    InspectorActivateRequested,
    InspectorCanceledRequested,
    InspectorPickMadeRequested,
    OutboundMessage,
    OverlayReady,
    PanelResizeRequested,
    PanelToggleRequested,
    PickCommentUpdatedRequested,
    PickDeletedRequested,
    PickSelectedRequested,
    RegionCreatedRequested,
    RegionDeletedRequested,
    RegionSelectedRequested,
    RegionUpdatedRequested,
    RelationCreatedRequested,
    RelationDeletedRequested,
    RelationUpdatedRequested,
)
from frontprompt.state.state import (
    ElementFingerprint,
    ElementRect,
    Pick,
    PickElement,
    Region,
    Relation,
)

_OUTBOUND = TypeAdapter(OutboundMessage)


# ---------------------------------------------------------------------------
# Schema version bump
# ---------------------------------------------------------------------------


def test_schema_version_bumped_to_0_10_0() -> None:
    """Schema 0.10.0 — + Voice-Over-Feature (voice-over sub-plan 02); previously 0.9.0 + Replay-Assertion-Authoring."""
    assert SCHEMA_VERSION == "0.10.0"


# ---------------------------------------------------------------------------
# Discriminated-union routing — kind → concrete class
# ---------------------------------------------------------------------------


def _make_pick_element() -> PickElement:
    return PickElement(
        selector="#hero",
        fingerprint=ElementFingerprint(tag="div"),
        text_snippet="Hello",
        rect=ElementRect(x=0.0, y=0.0, width=10.0, height=10.0),
    )


def _make_pick(pick_id: str = "p-uuid-1") -> Pick:
    return Pick(
        pick_id=pick_id,
        url="https://example.com/",
        timestamp_ms=1_700_000_000_000,
        element=_make_pick_element(),
        comment="",
    )


def test_inspector_activate_routes_to_correct_class() -> None:
    msg = _OUTBOUND.validate_python(
        {
            "kind": "inspector_activate_requested",
            "schema_version": "0.3.0",
        }
    )
    assert isinstance(msg, InspectorActivateRequested)


def test_inspector_canceled_routes_to_correct_class() -> None:
    msg = _OUTBOUND.validate_python(
        {
            "kind": "inspector_canceled_requested",
            "schema_version": "0.3.0",
        }
    )
    assert isinstance(msg, InspectorCanceledRequested)


def test_inspector_pick_made_routes_to_correct_class() -> None:
    payload = {
        "kind": "inspector_pick_made_requested",
        "schema_version": "0.3.0",
        "pick": _make_pick().model_dump(mode="json"),
    }
    msg = _OUTBOUND.validate_python(payload)
    assert isinstance(msg, InspectorPickMadeRequested)
    assert msg.pick.pick_id == "p-uuid-1"
    assert msg.pick.element.selector == "#hero"
    assert msg.pick.url == "https://example.com/"
    assert msg.pick.comment == ""


def test_pick_selected_routes_to_correct_class() -> None:
    msg = _OUTBOUND.validate_python(
        {
            "kind": "pick_selected_requested",
            "schema_version": "0.3.0",
            "pick_id": "p-1",
        }
    )
    assert isinstance(msg, PickSelectedRequested)
    assert msg.pick_id == "p-1"


def test_pick_comment_updated_routes_to_correct_class() -> None:
    msg = _OUTBOUND.validate_python(
        {
            "kind": "pick_comment_updated_requested",
            "schema_version": "0.3.0",
            "pick_id": "p-1",
            "comment": "edited",
        }
    )
    assert isinstance(msg, PickCommentUpdatedRequested)
    assert msg.comment == "edited"


def test_pick_deleted_routes_to_correct_class() -> None:
    msg = _OUTBOUND.validate_python(
        {
            "kind": "pick_deleted_requested",
            "schema_version": "0.3.0",
            "pick_id": "p-1",
        }
    )
    assert isinstance(msg, PickDeletedRequested)


# ---------------------------------------------------------------------------
# Existing panel messages still route correctly (Regression)
# ---------------------------------------------------------------------------


def test_panel_toggle_still_routes() -> None:
    msg = _OUTBOUND.validate_python(
        {
            "kind": "panel_toggle_requested",
            "schema_version": "0.3.0",
            "panel_id": "left",
        }
    )
    assert isinstance(msg, PanelToggleRequested)


def test_panel_resize_still_routes() -> None:
    msg = _OUTBOUND.validate_python(
        {
            "kind": "panel_resize_requested",
            "schema_version": "0.3.0",
            "panel_id": "right",
            "new_size": 400,
        }
    )
    assert isinstance(msg, PanelResizeRequested)


def test_hide_all_still_routes() -> None:
    msg = _OUTBOUND.validate_python(
        {
            "kind": "hide_all_panels_requested",
            "schema_version": "0.3.0",
            "target_open": False,
        }
    )
    assert isinstance(msg, HideAllPanelsRequested)


def test_overlay_ready_still_routes() -> None:
    msg = _OUTBOUND.validate_python(
        {
            "kind": "overlay_ready",
            "schema_version": "0.3.0",
            "bundle_build_session": "sess-1",
        }
    )
    assert isinstance(msg, OverlayReady)


# ---------------------------------------------------------------------------
# Invalid input — rejects unknown kind
# ---------------------------------------------------------------------------


def test_unknown_kind_raises_validation_error() -> None:
    with pytest.raises(ValidationError):
        _OUTBOUND.validate_python(
            {
                "kind": "this_does_not_exist",
                "schema_version": "0.3.0",
            }
        )


def test_inspector_pick_made_rejects_missing_pick() -> None:
    """Ohne ``pick``-field: ValidationError."""
    with pytest.raises(ValidationError):
        _OUTBOUND.validate_python(
            {
                "kind": "inspector_pick_made_requested",
                "schema_version": "0.3.0",
                # pick missing
            }
        )


def test_inspector_pick_made_rejects_pick_missing_required_field() -> None:
    """Innere Pick-Validation: fehlende required fields → ValidationError."""
    pick_payload = _make_pick().model_dump(mode="json")
    del pick_payload["pick_id"]  # required field
    with pytest.raises(ValidationError):
        _OUTBOUND.validate_python(
            {
                "kind": "inspector_pick_made_requested",
                "schema_version": "0.3.0",
                "pick": pick_payload,
            }
        )


# ---------------------------------------------------------------------------
# JSON roundtrip via TypeAdapter (Bridge dump-load symmetry)
# ---------------------------------------------------------------------------


def test_inspector_pick_made_json_roundtrip() -> None:
    msg = InspectorPickMadeRequested(pick=_make_pick())
    payload_json = _OUTBOUND.dump_json(msg).decode("utf-8")
    restored = _OUTBOUND.validate_json(payload_json)
    assert isinstance(restored, InspectorPickMadeRequested)
    assert restored.pick.pick_id == "p-uuid-1"
    assert restored.pick.element.fingerprint.tag == "div"
    assert restored.pick.comment == ""


# ---------------------------------------------------------------------------
# Codegen roots
# ---------------------------------------------------------------------------


def test_codegen_roots_includes_new_envelopes() -> None:
    from frontprompt.bridge.messages import __codegen_roots__

    for name in [
        "InspectorActivateRequested",
        "InspectorCanceledRequested",
        "InspectorPickMadeRequested",
        "PickSelectedRequested",
        "PickCommentUpdatedRequested",
        "PickDeletedRequested",
        "RelationCreatedRequested",
        "RelationDeletedRequested",
        "RelationUpdatedRequested",
    ]:
        assert name in __codegen_roots__, f"{name} fehlt in __codegen_roots__"


# ---------------------------------------------------------------------------
# Relation envelopes — discriminator routing + roundtrip
# ---------------------------------------------------------------------------


def _make_relation(
    relation_id: str = "rel-uuid-1",
    source: str = "p-uuid-1",
    source_kind: str = "pick",
    target: str = "p-uuid-2",
    target_kind: str = "pick",
    kind: str = "relates_to",
    note: str | None = None,
) -> Relation:
    return Relation(
        relation_id=relation_id,
        source_id=source,
        source_kind=source_kind,  # type: ignore[arg-type]
        target_id=target,
        target_kind=target_kind,  # type: ignore[arg-type]
        kind=kind,  # type: ignore[arg-type]
        note=note,
        timestamp_ms=1_700_000_000_002,
    )


def test_relation_created_routes_to_correct_class() -> None:
    payload = {
        "kind": "relation_created_requested",
        "schema_version": "0.3.0",
        "relation": _make_relation(kind="triggers", note="opens modal").model_dump(mode="json"),
    }
    msg = _OUTBOUND.validate_python(payload)
    assert isinstance(msg, RelationCreatedRequested)
    assert msg.relation.relation_id == "rel-uuid-1"
    assert msg.relation.kind == "triggers"
    assert msg.relation.note == "opens modal"


def test_relation_deleted_routes_to_correct_class() -> None:
    msg = _OUTBOUND.validate_python(
        {
            "kind": "relation_deleted_requested",
            "schema_version": "0.3.0",
            "relation_id": "rel-1",
        }
    )
    assert isinstance(msg, RelationDeletedRequested)
    assert msg.relation_id == "rel-1"


def test_relation_updated_routes_to_correct_class() -> None:
    msg = _OUTBOUND.validate_python(
        {
            "kind": "relation_updated_requested",
            "schema_version": "0.3.0",
            "relation_id": "rel-1",
            "relation_kind": "part_of",
            "note": "edited",
        }
    )
    assert isinstance(msg, RelationUpdatedRequested)
    assert msg.relation_kind == "part_of"
    assert msg.note == "edited"


def test_relation_updated_accepts_null_note() -> None:
    msg = _OUTBOUND.validate_python(
        {
            "kind": "relation_updated_requested",
            "schema_version": "0.3.0",
            "relation_id": "rel-1",
            "relation_kind": "relates_to",
            "note": None,
        }
    )
    assert isinstance(msg, RelationUpdatedRequested)
    assert msg.note is None


def test_relation_created_rejects_self_loop_payload() -> None:
    """Self-loop wird auf Pydantic-model_validator-Ebene gerejected — auch im wire-payload.

    Self-loop = same endpoint-id AND same endpoint-kind. Pick "x" ↔ Region "x" wäre erlaubt
    (heterogeneous endpoints), aber Pick "x" ↔ Pick "x" verboten.
    """
    with pytest.raises(ValidationError):
        _OUTBOUND.validate_python(
            {
                "kind": "relation_created_requested",
                "schema_version": "0.4.0",
                "relation": {
                    "relation_id": "rel-x",
                    "source_id": "p-same",
                    "source_kind": "pick",
                    "target_id": "p-same",
                    "target_kind": "pick",
                    "kind": "relates_to",
                    "timestamp_ms": 0,
                },
            }
        )


def test_relation_updated_rejects_unknown_kind() -> None:
    with pytest.raises(ValidationError):
        _OUTBOUND.validate_python(
            {
                "kind": "relation_updated_requested",
                "schema_version": "0.3.0",
                "relation_id": "rel-1",
                "relation_kind": "invalid",
                "note": None,
            }
        )


def test_relation_created_json_roundtrip() -> None:
    msg = RelationCreatedRequested(relation=_make_relation())
    payload_json = _OUTBOUND.dump_json(msg).decode("utf-8")
    restored = _OUTBOUND.validate_json(payload_json)
    assert isinstance(restored, RelationCreatedRequested)
    assert restored.relation.relation_id == "rel-uuid-1"


def test_relation_created_accepts_pick_to_region_endpoints() -> None:
    """Heterogeneous Relations (Schema 0.4.0) — source=pick, target=region geht durch den wire."""
    payload = {
        "kind": "relation_created_requested",
        "schema_version": "0.4.0",
        "relation": _make_relation(
            source="p-uuid-1",
            source_kind="pick",
            target="r-uuid-1",
            target_kind="region",
            kind="part_of",
        ).model_dump(mode="json"),
    }
    msg = _OUTBOUND.validate_python(payload)
    assert isinstance(msg, RelationCreatedRequested)
    assert msg.relation.source_kind == "pick"
    assert msg.relation.target_kind == "region"


# ---------------------------------------------------------------------------
# Region envelopes — discriminator routing + roundtrip (Schema 0.4.0)
# ---------------------------------------------------------------------------


def _make_region(
    region_id: str = "reg-uuid-1",
    note: str | None = None,
    member_pick_ids: list[str] | None = None,
) -> Region:
    return Region(
        region_id=region_id,
        rect=ElementRect(x=0.0, y=0.0, width=100.0, height=80.0),
        member_pick_ids=member_pick_ids or [],
        note=note,
        timestamp_ms=1_700_000_000_003,
    )


def test_region_created_routes_to_correct_class() -> None:
    payload = {
        "kind": "region_created_requested",
        "schema_version": "0.4.0",
        "region": _make_region(note="header area", member_pick_ids=["p-1", "p-2"]).model_dump(mode="json"),
    }
    msg = _OUTBOUND.validate_python(payload)
    assert isinstance(msg, RegionCreatedRequested)
    assert msg.region.region_id == "reg-uuid-1"
    assert msg.region.note == "header area"
    assert msg.region.member_pick_ids == ["p-1", "p-2"]


def test_region_deleted_routes_to_correct_class() -> None:
    msg = _OUTBOUND.validate_python(
        {
            "kind": "region_deleted_requested",
            "schema_version": "0.4.0",
            "region_id": "reg-1",
        }
    )
    assert isinstance(msg, RegionDeletedRequested)
    assert msg.region_id == "reg-1"


def test_region_updated_routes_to_correct_class() -> None:
    msg = _OUTBOUND.validate_python(
        {
            "kind": "region_updated_requested",
            "schema_version": "0.4.0",
            "region_id": "reg-1",
            "note": "renamed",
        }
    )
    assert isinstance(msg, RegionUpdatedRequested)
    assert msg.note == "renamed"


def test_region_updated_accepts_null_note() -> None:
    msg = _OUTBOUND.validate_python(
        {
            "kind": "region_updated_requested",
            "schema_version": "0.4.0",
            "region_id": "reg-1",
            "note": None,
        }
    )
    assert isinstance(msg, RegionUpdatedRequested)
    assert msg.note is None


def test_region_selected_routes_to_correct_class() -> None:
    msg = _OUTBOUND.validate_python(
        {
            "kind": "region_selected_requested",
            "schema_version": "0.4.0",
            "region_id": "reg-1",
        }
    )
    assert isinstance(msg, RegionSelectedRequested)
    assert msg.region_id == "reg-1"


def test_region_created_json_roundtrip() -> None:
    msg = RegionCreatedRequested(region=_make_region(note="hero"))
    payload_json = _OUTBOUND.dump_json(msg).decode("utf-8")
    restored = _OUTBOUND.validate_json(payload_json)
    assert isinstance(restored, RegionCreatedRequested)
    assert restored.region.region_id == "reg-uuid-1"
    assert restored.region.note == "hero"


# ---------------------------------------------------------------------------
# StateSnapshotMessage — integrity_token field
# ---------------------------------------------------------------------------


def test_state_snapshot_message_roundtrip_with_token() -> None:
    """StateSnapshotMessage serialises and deserialises with integrity_token preserved."""
    from frontprompt.bridge.messages import StateSnapshotMessage
    from frontprompt.state import StateManager

    snap = StateManager(session_id="test-session").snapshot()
    msg = StateSnapshotMessage(snapshot=snap, integrity_token="abc123token")
    payload = msg.model_dump(mode="json")
    restored = StateSnapshotMessage.model_validate(payload)
    assert restored.integrity_token == "abc123token"


def test_state_snapshot_message_roundtrip_without_token() -> None:
    """StateSnapshotMessage without integrity_token has None (backward-compat)."""
    from frontprompt.bridge.messages import StateSnapshotMessage
    from frontprompt.state import StateManager

    snap = StateManager(session_id="test-session").snapshot()
    msg = StateSnapshotMessage(snapshot=snap)
    assert msg.integrity_token is None
    payload = msg.model_dump(mode="json")
    restored = StateSnapshotMessage.model_validate(payload)
    assert restored.integrity_token is None
