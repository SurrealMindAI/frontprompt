"""Tests für MutationEnvelope discriminated-union — synchron, kein pytest-anyio.

Konvention: alle Field-Namen mandatory-prefixed.
Pydantic 2.13 ConfigDict(extra='forbid', frozen=True).
IDEMPOTENCY_TTL_NS-Konstante aus mutations.py als Idempotenz-TTL-Anker.
"""

from __future__ import annotations

import pytest
from pydantic import ValidationError

from frontprompt.wire.mutations import (
    IDEMPOTENCY_TTL_NS,
    AnnotationDraftSubmitted,
    IdempotencyKey,
    MutationEnvelope,
    PickRequested,
)

# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------

PICK_REQUESTED_PAYLOAD = {
    "type": "pick_requested",
    "pointing_session_id": "01HCCCCCCCCCCCCCCCCCCCCCC1",
    "selector": "div.hero-button",
    "score": "0.95",
    "idempotency_key": "idk-uuid-001",
}

ANNOTATION_DRAFT_PAYLOAD = {
    "type": "annotation_draft_submitted",
    "pointing_session_id": "01HCCCCCCCCCCCCCCCCCCCCCC1",
    "content": "Click the checkout button",
    "idempotency_key": "idk-uuid-002",
}

ANNOTATION_DRAFT_WITH_DEHYDRATED = {
    **ANNOTATION_DRAFT_PAYLOAD,
    "page_session_id": "01HAAAAAAAAAAAAAAAAAAAAAA1",
    "interaction_flow_step_id": "01HEEEEEEEEEEEEEEEEEEEEEE1",
    "dom_snapshot_hash": "sha256:cafebabe",
}

ENVELOPE_BASE = {
    "schema_version": 1,
    "received_at_monotonic_ns": 9_000_000_000,
}


def _envelope(payload: dict) -> dict:  # type: ignore[type-arg]
    return {**ENVELOPE_BASE, "payload": payload}


# ---------------------------------------------------------------------------
# MutationEnvelope — Konstruktion
# ---------------------------------------------------------------------------


def test_pick_requested_envelope_round_trips() -> None:
    raw = _envelope(PICK_REQUESTED_PAYLOAD)
    env = MutationEnvelope.model_validate(raw)
    assert isinstance(env.payload, PickRequested)
    assert env.payload.type == "pick_requested"
    assert env.payload.pointing_session_id == "01HCCCCCCCCCCCCCCCCCCCCCC1"
    assert env.payload.selector == "div.hero-button"
    assert env.payload.score == "0.95"
    assert env.payload.idempotency_key == "idk-uuid-001"
    assert env.schema_version == 1
    assert env.received_at_monotonic_ns == 9_000_000_000


def test_annotation_draft_submitted_minimal_round_trips() -> None:
    """Ohne optionale dehydrated IDs — alle None."""
    raw = _envelope(ANNOTATION_DRAFT_PAYLOAD)
    env = MutationEnvelope.model_validate(raw)
    assert isinstance(env.payload, AnnotationDraftSubmitted)
    assert env.payload.type == "annotation_draft_submitted"
    assert env.payload.content == "Click the checkout button"
    assert env.payload.page_session_id is None
    assert env.payload.interaction_flow_step_id is None
    assert env.payload.dom_snapshot_hash is None


def test_annotation_draft_submitted_with_dehydrated_ids() -> None:
    """Mit optionalen dehydrated IDs."""
    raw = _envelope(ANNOTATION_DRAFT_WITH_DEHYDRATED)
    env = MutationEnvelope.model_validate(raw)
    assert isinstance(env.payload, AnnotationDraftSubmitted)
    assert env.payload.page_session_id == "01HAAAAAAAAAAAAAAAAAAAAAA1"
    assert env.payload.interaction_flow_step_id == "01HEEEEEEEEEEEEEEEEEEEEEE1"
    assert env.payload.dom_snapshot_hash == "sha256:cafebabe"


# ---------------------------------------------------------------------------
# Discriminator — unbekannter type-Wert
# ---------------------------------------------------------------------------


def test_unknown_mutation_type_raises() -> None:
    raw = _envelope({"type": "rogue_mutation", "x": 1})
    with pytest.raises(ValidationError):
        MutationEnvelope.model_validate(raw)


# ---------------------------------------------------------------------------
# schema_version
# ---------------------------------------------------------------------------


def test_wrong_schema_version_raises() -> None:
    raw = _envelope(PICK_REQUESTED_PAYLOAD)
    raw["schema_version"] = 99
    with pytest.raises(ValidationError):
        MutationEnvelope.model_validate(raw)


# ---------------------------------------------------------------------------
# extra='forbid'
# ---------------------------------------------------------------------------


def test_extra_field_on_mutation_envelope_raises() -> None:
    raw = _envelope(PICK_REQUESTED_PAYLOAD)
    raw["unexpected"] = "field"
    with pytest.raises(ValidationError):
        MutationEnvelope.model_validate(raw)


def test_extra_field_on_pick_requested_payload_raises() -> None:
    payload = {**PICK_REQUESTED_PAYLOAD, "rogue": "field"}
    with pytest.raises(ValidationError):
        MutationEnvelope.model_validate(_envelope(payload))


# ---------------------------------------------------------------------------
# frozen=True
# ---------------------------------------------------------------------------


def test_mutation_envelope_is_frozen() -> None:
    env = MutationEnvelope.model_validate(_envelope(PICK_REQUESTED_PAYLOAD))
    with pytest.raises((AttributeError, TypeError, ValidationError)):
        env.schema_version = 99  # type: ignore[misc]


# ---------------------------------------------------------------------------
# Pflichtfelder
# ---------------------------------------------------------------------------


def test_pick_requested_missing_selector_raises() -> None:
    payload = {k: v for k, v in PICK_REQUESTED_PAYLOAD.items() if k != "selector"}
    with pytest.raises(ValidationError):
        MutationEnvelope.model_validate(_envelope(payload))


def test_pick_requested_missing_idempotency_key_raises() -> None:
    payload = {k: v for k, v in PICK_REQUESTED_PAYLOAD.items() if k != "idempotency_key"}
    with pytest.raises(ValidationError):
        MutationEnvelope.model_validate(_envelope(payload))


def test_annotation_draft_missing_content_raises() -> None:
    payload = {k: v for k, v in ANNOTATION_DRAFT_PAYLOAD.items() if k != "content"}
    with pytest.raises(ValidationError):
        MutationEnvelope.model_validate(_envelope(payload))


# ---------------------------------------------------------------------------
# IdempotencyKey NewType — Verhalten im Runtime
# ---------------------------------------------------------------------------


def test_idempotency_key_is_str_at_runtime() -> None:
    """NewType ist zur Laufzeit ein str — kein overhead."""
    key = IdempotencyKey("my-key-001")
    assert isinstance(key, str)
    assert key == "my-key-001"


# ---------------------------------------------------------------------------
# IDEMPOTENCY_TTL_NS — Idempotenz-TTL-Anker-Konstante
# ---------------------------------------------------------------------------


def test_idempotency_ttl_ns_is_300_seconds_in_ns() -> None:
    """300 Sekunden in Nanosekunden — authorisierter Idempotenz-TTL-Wert."""
    assert IDEMPOTENCY_TTL_NS == 300 * 1_000_000_000


def test_idempotency_ttl_ns_is_positive_int() -> None:
    assert isinstance(IDEMPOTENCY_TTL_NS, int)
    assert IDEMPOTENCY_TTL_NS > 0


# ---------------------------------------------------------------------------
# model_dump Round-Trip
# ---------------------------------------------------------------------------


def test_pick_requested_model_dump_round_trip() -> None:
    raw = _envelope(PICK_REQUESTED_PAYLOAD)
    env = MutationEnvelope.model_validate(raw)
    dumped = env.model_dump(mode="json")
    assert dumped["payload"]["type"] == "pick_requested"
    assert dumped["payload"]["selector"] == "div.hero-button"


def test_annotation_draft_model_dump_omits_none_optional_fields() -> None:
    """model_dump(exclude_none=True) gibt optionale None-Felder nicht raus — wichtig für den HTTP-Body."""
    raw = _envelope(ANNOTATION_DRAFT_PAYLOAD)
    env = MutationEnvelope.model_validate(raw)
    dumped = env.model_dump(mode="json", exclude_none=True)
    assert "page_session_id" not in dumped["payload"]
    assert "interaction_flow_step_id" not in dumped["payload"]
    assert "dom_snapshot_hash" not in dumped["payload"]
