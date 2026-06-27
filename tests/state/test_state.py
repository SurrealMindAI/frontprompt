"""Tests für state.py Pydantic-Modelle — schema-shape + roundtrip.

Focus auf die Inspector-State-Erweiterung (Schema 0.2.0). Existing PanelStateView
hat aktuell keine direkten Tests — Scout-Notiz: separate Aufgabe.
"""

from __future__ import annotations

import pytest
from pydantic import ValidationError

from frontprompt.state.state import (
    PICK_COMMENT_MAX_LENGTH,
    REGION_NOTE_MAX_LENGTH,
    RELATION_KINDS,
    ElementFingerprint,
    ElementRect,
    InspectorState,
    PanelStateView,
    PanelView,
    Pick,
    PickElement,
    Region,
    Relation,
    StateSnapshot,
)

# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------


def _make_rect() -> ElementRect:
    return ElementRect(x=10.5, y=20.0, width=200.0, height=80.5)


def _make_fingerprint() -> ElementFingerprint:
    return ElementFingerprint(
        tag="div",
        attributes={"id": "hero-cta", "class": "btn primary"},
        text="Click me",
        path=["html", "body", "main", "section", "div"],
        parent_name="section",
        parent_attribs={"class": "hero"},
        parent_text="Welcome ...",
        siblings=["h1", "p"],  # excludes self
        children=["span"],
    )


def _make_pick_element() -> PickElement:
    return PickElement(
        selector="#hero-cta",
        fingerprint=_make_fingerprint(),
        text_snippet="Click me",
        rect=_make_rect(),
    )


def _make_pick(pick_id: str = "pick-001") -> Pick:
    return Pick(
        pick_id=pick_id,
        url="https://example.com/",
        timestamp_ms=1_700_000_000_000,
        element=_make_pick_element(),
        comment="initial note",
    )


# ---------------------------------------------------------------------------
# ElementRect
# ---------------------------------------------------------------------------


def test_element_rect_accepts_floats() -> None:
    """Sub-pixel-werte (z.B. von transform: scale()) müssen lossless round-trippen."""
    rect = ElementRect(x=0.5, y=1.25, width=100.75, height=42.125)
    assert rect.x == 0.5
    assert rect.height == 42.125


def test_element_rect_roundtrips_json() -> None:
    rect = _make_rect()
    serialized = rect.model_dump_json()
    restored = ElementRect.model_validate_json(serialized)
    assert restored == rect


# ---------------------------------------------------------------------------
# ElementFingerprint
# ---------------------------------------------------------------------------


def test_fingerprint_minimal_with_defaults() -> None:
    """tag ist required, alle anderen Felder haben sinnvolle defaults für orphan-elements."""
    fp = ElementFingerprint(tag="span")
    assert fp.tag == "span"
    assert fp.attributes == {}
    assert fp.text == ""
    assert fp.path == []
    assert fp.parent_name is None
    assert fp.parent_attribs == {}
    assert fp.siblings == []
    assert fp.children == []


def test_fingerprint_full_roundtrips_json() -> None:
    fp = _make_fingerprint()
    restored = ElementFingerprint.model_validate_json(fp.model_dump_json())
    assert restored == fp


def test_fingerprint_rejects_missing_tag() -> None:
    with pytest.raises(ValidationError):
        ElementFingerprint(attributes={"id": "x"})  # type: ignore[call-arg]


def test_fingerprint_path_preserves_order() -> None:
    """Tag-sequence muss DOM-order behalten — wichtig für scrapling-relocate scoring."""
    fp = ElementFingerprint(tag="b", path=["html", "body", "div", "p", "b"])
    assert fp.path == ["html", "body", "div", "p", "b"]


# ---------------------------------------------------------------------------
# PickElement
# ---------------------------------------------------------------------------


def test_pick_element_requires_selector_fingerprint_rect() -> None:
    rect = _make_rect()
    fp = _make_fingerprint()
    el = PickElement(selector="#x", fingerprint=fp, text_snippet="t", rect=rect)
    assert el.selector == "#x"
    assert el.text_snippet == "t"
    assert el.fingerprint.tag == "div"


def test_pick_element_text_snippet_defaults_empty() -> None:
    """text_snippet ist optional — UI kann via fingerprint.text fallen."""
    el = PickElement(selector="div", fingerprint=_make_fingerprint(), rect=_make_rect())
    assert el.text_snippet == ""


# ---------------------------------------------------------------------------
# Pick
# ---------------------------------------------------------------------------


def test_pick_round_trips() -> None:
    pick = _make_pick()
    restored = Pick.model_validate_json(pick.model_dump_json())
    assert restored == pick


def test_pick_comment_defaults_empty() -> None:
    pick = Pick(
        pick_id="p1",
        url="https://x/",
        timestamp_ms=0,
        element=_make_pick_element(),
    )
    assert pick.comment == ""


# ---------------------------------------------------------------------------
# InspectorState
# ---------------------------------------------------------------------------


def test_inspector_state_defaults() -> None:
    """Default-init: inactive, empty list, no active pick."""
    state = InspectorState()
    assert state.active is False
    assert state.picks == []
    assert state.active_pick_id is None


def test_inspector_state_appends_picks() -> None:
    state = InspectorState(
        active=True,
        picks=[_make_pick("p1"), _make_pick("p2")],
        active_pick_id="p2",
    )
    assert len(state.picks) == 2
    assert state.active_pick_id == "p2"
    assert state.picks[0].pick_id == "p1"


def test_inspector_state_roundtrips_with_picks() -> None:
    state = InspectorState(
        active=False,
        picks=[_make_pick("p1")],
        active_pick_id="p1",
    )
    restored = InspectorState.model_validate_json(state.model_dump_json())
    assert restored == state


# ---------------------------------------------------------------------------
# StateSnapshot — version bump + new field
# ---------------------------------------------------------------------------


def test_state_snapshot_default_schema_version_is_0_9_0() -> None:
    # Schema bumped 0.9.0 → 0.10.0 in voice-over sub-plan 01
    # (TranscriptSegmentEntry + MicrophoneState + SettingsState + TranscriptionState).
    # Schema bumped 0.10.0 → 0.11.0 in model-catalog sub-plan 01
    # (TranscriptionModelSpec + SettingsState.mlx_whisper_model_id +
    #  TranscriptionBackendInfo.available_models + .selected_model_id).
    snap = StateSnapshot(panel_state=_panel_state())
    assert snap.schema_version == "0.11.0"


def test_state_snapshot_inspector_state_default_factory() -> None:
    """Wenn nicht explizit gesetzt, inspector_state ist eine fresh empty InspectorState."""
    snap = StateSnapshot(panel_state=_panel_state())
    assert snap.inspector_state.active is False
    assert snap.inspector_state.picks == []


def test_state_snapshot_full_roundtrip_with_inspector() -> None:
    snap = StateSnapshot(
        panel_state=_panel_state(),
        inspector_state=InspectorState(
            active=True,
            picks=[_make_pick("p1")],
            active_pick_id="p1",
        ),
    )
    restored = StateSnapshot.model_validate_json(snap.model_dump_json())
    assert restored == snap


def test_state_snapshot_default_factories_independence() -> None:
    """Default-factory darf nicht mutable-shared sein zwischen Instanzen — pydantic-default-factory regression-check."""
    a = StateSnapshot(panel_state=_panel_state())
    b = StateSnapshot(panel_state=_panel_state())
    a.inspector_state.picks.append(_make_pick("p1"))
    assert b.inspector_state.picks == []


# ---------------------------------------------------------------------------
# Codegen-roots — sicherstellen dass alle Pick-types emittiert werden
# ---------------------------------------------------------------------------


def test_codegen_roots_includes_new_models() -> None:
    """Schema 0.4.0 — Region als first-class node hinzu, ElementRect bewusst NICHT.

    ElementRect ist nested in Pick.element.rect UND Region.rect; beide emittieren
    es inline. Wenn man ElementRect auch als root hinzufügt, triggert
    pydantic-zod-codegen einen ``$defs``-Duplikations-Bug
    (``ElementRect1`` mit broken-syntax ``number.optional()``) — siehe
    ``frontprompt.bridge.codegen._strip_dead_duplicates`` workaround.
    """
    from frontprompt.state.state import __codegen_roots__

    for name in [
        "PanelView",
        "PanelStateView",
        "ElementFingerprint",
        "PickElement",
        "Pick",
        "Region",
        "Relation",
        "RelationKind",
        "RelationEndpointKind",
        "InspectorState",
        "StateSnapshot",
    ]:
        assert name in __codegen_roots__, f"{name} fehlt in __codegen_roots__"
    # Bewusst NICHT in __codegen_roots__:
    assert "ElementRect" not in __codegen_roots__, (
        "ElementRect darf nicht root sein — triggert pydantic-zod-codegen "
        "$defs-Duplikations-Bug (ElementRect1 mit number.optional())."
    )


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _panel_state() -> PanelStateView:
    return PanelStateView(
        top=PanelView(open=True, size=56),
        bottom=PanelView(open=True, size=220),
        left=PanelView(open=True, size=300),
        right=PanelView(open=True, size=340),
    )


# ---------------------------------------------------------------------------
# Relation — Heterogeneous edges (Schema 0.4.0)
# ---------------------------------------------------------------------------


def _make_relation(
    relation_id: str = "rel-001",
    source: str = "pick-a",
    source_kind: str = "pick",
    target: str = "pick-b",
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
        timestamp_ms=1_700_000_000_000,
    )


def test_relation_kinds_tuple_matches_literal() -> None:
    assert RELATION_KINDS == ("relates_to", "triggers", "part_of")


def test_relation_roundtrip_full_fields() -> None:
    r = _make_relation(note="user note")
    dumped = r.model_dump(mode="json")
    restored = Relation.model_validate(dumped)
    assert restored == r


def test_relation_note_defaults_to_none() -> None:
    r = _make_relation()
    assert r.note is None


def test_relation_rejects_self_loop_pick_pick() -> None:
    """Pydantic model_validator blocks self-loops independent von StateManager."""
    with pytest.raises(ValidationError) as exc_info:
        Relation(
            relation_id="rel-x",
            source_id="same",
            source_kind="pick",
            target_id="same",
            target_kind="pick",
            kind="relates_to",
            timestamp_ms=0,
        )
    assert "self-loop" in str(exc_info.value).lower() or "must differ" in str(exc_info.value).lower()


def test_relation_allows_pick_and_region_with_same_id() -> None:
    """Same id but different kind is NOT a self-loop — pick:X and region:X are distinct nodes."""
    r = Relation(
        relation_id="rel-mixed",
        source_id="same",
        source_kind="pick",
        target_id="same",
        target_kind="region",
        kind="relates_to",
        timestamp_ms=0,
    )
    assert r.source_kind == "pick"
    assert r.target_kind == "region"


def test_relation_rejects_unknown_kind() -> None:
    with pytest.raises(ValidationError):
        Relation(
            relation_id="rel-x",
            source_id="a",
            source_kind="pick",
            target_id="b",
            target_kind="pick",
            kind="invalid_kind",  # type: ignore[arg-type]
            timestamp_ms=0,
        )


def test_relation_rejects_unknown_endpoint_kind() -> None:
    with pytest.raises(ValidationError):
        Relation(
            relation_id="rel-x",
            source_id="a",
            source_kind="page",  # type: ignore[arg-type]
            target_id="b",
            target_kind="pick",
            kind="relates_to",
            timestamp_ms=0,
        )


def test_inspector_state_relations_default_empty() -> None:
    state = InspectorState()
    assert state.relations == []


def test_inspector_state_regions_default_empty() -> None:
    state = InspectorState()
    assert state.regions == []
    assert state.active_region_id is None


def test_inspector_state_roundtrips_with_relations() -> None:
    state = InspectorState(relations=[_make_relation(), _make_relation("rel-002", kind="triggers")])
    dumped = state.model_dump(mode="json")
    restored = InspectorState.model_validate(dumped)
    assert len(restored.relations) == 2
    assert restored.relations[0].kind == "relates_to"
    assert restored.relations[1].kind == "triggers"


def test_state_snapshot_includes_relations_field() -> None:
    snap = StateSnapshot(
        panel_state=_panel_state(),
        inspector_state=InspectorState(relations=[_make_relation()]),
    )
    dumped = snap.model_dump(mode="json")
    assert "relations" in dumped["inspector_state"]
    assert len(dumped["inspector_state"]["relations"]) == 1
    assert "regions" in dumped["inspector_state"]


# ---------------------------------------------------------------------------
# Region — Schema 0.4.0 first-class container entity
# ---------------------------------------------------------------------------


def _make_region(
    region_id: str = "reg-001",
    member_pick_ids: list[str] | None = None,
    note: str | None = None,
) -> Region:
    return Region(
        region_id=region_id,
        rect=ElementRect(x=0.0, y=0.0, width=200.0, height=100.0),
        member_pick_ids=member_pick_ids or [],
        note=note,
        timestamp_ms=1_700_000_000_002,
    )


def test_region_roundtrip_full_fields() -> None:
    r = _make_region(member_pick_ids=["p-1", "p-2"], note="form area")
    dumped = r.model_dump(mode="json")
    restored = Region.model_validate(dumped)
    assert restored == r


def test_region_defaults_empty_members_and_null_note() -> None:
    r = _make_region()
    assert r.member_pick_ids == []
    assert r.note is None


# ---------------------------------------------------------------------------
# max_length constraints — Phase-1 snapshot-size mitigation
# ---------------------------------------------------------------------------


def test_pick_comment_over_limit_raises() -> None:
    """Pick.comment above PICK_COMMENT_MAX_LENGTH must raise ValidationError."""
    with pytest.raises(ValidationError):
        Pick(
            pick_id="p1",
            url="https://x/",
            timestamp_ms=0,
            element=_make_pick_element(),
            comment="x" * (PICK_COMMENT_MAX_LENGTH + 1),
        )


def test_pick_comment_at_limit_accepted() -> None:
    """Pick.comment exactly at PICK_COMMENT_MAX_LENGTH must be accepted."""
    pick = Pick(
        pick_id="p1",
        url="https://x/",
        timestamp_ms=0,
        element=_make_pick_element(),
        comment="x" * PICK_COMMENT_MAX_LENGTH,
    )
    assert len(pick.comment) == PICK_COMMENT_MAX_LENGTH


def test_region_note_over_limit_raises() -> None:
    """Region.note above REGION_NOTE_MAX_LENGTH must raise ValidationError."""
    with pytest.raises(ValidationError):
        Region(
            region_id="r1",
            rect=ElementRect(x=0.0, y=0.0, width=200.0, height=100.0),
            timestamp_ms=0,
            note="x" * (REGION_NOTE_MAX_LENGTH + 1),
        )


def test_region_note_at_limit_accepted() -> None:
    """Region.note exactly at REGION_NOTE_MAX_LENGTH must be accepted."""
    r = Region(
        region_id="r1",
        rect=ElementRect(x=0.0, y=0.0, width=200.0, height=100.0),
        timestamp_ms=0,
        note="x" * REGION_NOTE_MAX_LENGTH,
    )
    assert r.note is not None
    assert len(r.note) == REGION_NOTE_MAX_LENGTH


def test_region_note_none_accepted() -> None:
    """Region.note=None must still be accepted (field is str | None)."""
    r = Region(
        region_id="r1",
        rect=ElementRect(x=0.0, y=0.0, width=200.0, height=100.0),
        timestamp_ms=0,
        note=None,
    )
    assert r.note is None


# ---------------------------------------------------------------------------
# Schema 0.7.0 — origin_session field on Pick / Region / Relation
# ---------------------------------------------------------------------------


def test_pick_region_relation_carry_origin_session() -> None:
    """Schema 0.7.0: Pick, Region, Relation each accept origin_session kwarg,
    default to None when omitted, and round-trip through JSON.
    """
    # Pick — explicit value
    pick = Pick(
        pick_id="p-os-001",
        url="https://example.com/",
        timestamp_ms=1_700_000_000_000,
        element=_make_pick_element(),
        origin_session="sess-abc-123",
    )
    assert pick.origin_session == "sess-abc-123"
    restored_pick = Pick.model_validate_json(pick.model_dump_json())
    assert restored_pick.origin_session == "sess-abc-123"

    # Pick — default None
    pick_no_session = _make_pick("p-os-002")
    assert pick_no_session.origin_session is None
    restored_no_session = Pick.model_validate_json(pick_no_session.model_dump_json())
    assert restored_no_session.origin_session is None

    # Region — explicit value
    region = Region(
        region_id="reg-os-001",
        rect=ElementRect(x=0.0, y=0.0, width=200.0, height=100.0),
        timestamp_ms=1_700_000_000_001,
        origin_session="sess-abc-123",
    )
    assert region.origin_session == "sess-abc-123"
    restored_region = Region.model_validate_json(region.model_dump_json())
    assert restored_region.origin_session == "sess-abc-123"

    # Region — default None
    region_no_session = _make_region()
    assert region_no_session.origin_session is None

    # Relation — explicit value
    relation = Relation(
        relation_id="rel-os-001",
        source_id="pick-a",
        source_kind="pick",
        target_id="pick-b",
        target_kind="pick",
        kind="relates_to",
        timestamp_ms=1_700_000_000_002,
        origin_session="sess-abc-123",
    )
    assert relation.origin_session == "sess-abc-123"
    restored_relation = Relation.model_validate_json(relation.model_dump_json())
    assert restored_relation.origin_session == "sess-abc-123"

    # Relation — default None
    relation_no_session = _make_relation()
    assert relation_no_session.origin_session is None


def test_schema_version_is_current() -> None:
    """Schema 0.11.0: + SetTranscriptionModelRequested (voiceover-models sub-plan 02); previously 0.10.0."""
    from frontprompt.bridge.messages import SCHEMA_VERSION

    assert SCHEMA_VERSION == "0.11.0"
