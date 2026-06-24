"""Tests für EventEnvelope discriminated-union — synchron, kein pytest-anyio.

Konvention: alle Field-Namen mandatory-prefixed (page_session_id, daemon_id etc.).
Pydantic 2.13 ConfigDict(extra='forbid', frozen=True) auf allen Models.
"""

from __future__ import annotations

import pytest
from pydantic import ValidationError

from frontprompt.wire.events import (
    AnnotationPersisted,
    EventEnvelope,
    PageNavigated,
    PickAcknowledged,
    SessionStarted,
)

# ---------------------------------------------------------------------------
# Fixtures — minimal-valide Raw-Dicts pro Payload-Type
# ---------------------------------------------------------------------------

SESSION_STARTED_PAYLOAD = {
    "type": "session_started",
    "page_session_id": "01HAAAAAAAAAAAAAAAAAAAAAA1",
    "dns_domain": "example.com",
    "started_at_monotonic_ns": 1_000_000_000,
}

PAGE_NAVIGATED_PAYLOAD = {
    "type": "page_navigated",
    "page_session_id": "01HAAAAAAAAAAAAAAAAAAAAAA1",
    "url": "https://example.com/path",
    "dom_snapshot_hash": "sha256:deadbeef",
    "navigated_at_monotonic_ns": 2_000_000_000,
}

PICK_ACKNOWLEDGED_PAYLOAD = {
    "type": "pick_acknowledged",
    "pick_id": "01HBBBBBBBBBBBBBBBBBBBBBB1",
    "pointing_session_id": "01HCCCCCCCCCCCCCCCCCCCCCC1",
    "acknowledged_at_monotonic_ns": 3_000_000_000,
}

ANNOTATION_PERSISTED_PAYLOAD = {
    "type": "annotation_persisted",
    "annotation_id": "01HDDDDDDDDDDDDDDDDDDDDDD1",
    "pointing_session_id": "01HCCCCCCCCCCCCCCCCCCCCCC1",
    "persisted_at_monotonic_ns": 4_000_000_000,
}

ENVELOPE_BASE = {
    "schema_version": 1,
    "daemon_id": "daemon-abc-123",
    "emitted_at_monotonic_ns": 5_000_000_000,
}


def _envelope(payload: dict) -> dict:  # type: ignore[type-arg]
    return {**ENVELOPE_BASE, "payload": payload}


# ---------------------------------------------------------------------------
# EventEnvelope — Konstruktion über model_validate (discriminated-union Pfad)
# ---------------------------------------------------------------------------


def test_session_started_envelope_round_trips() -> None:
    """SessionStarted Envelope parsed korrekt via discriminated-union."""
    raw = _envelope(SESSION_STARTED_PAYLOAD)
    env = EventEnvelope.model_validate(raw)
    assert isinstance(env.payload, SessionStarted)
    assert env.payload.type == "session_started"
    assert env.payload.page_session_id == "01HAAAAAAAAAAAAAAAAAAAAAA1"
    assert env.payload.dns_domain == "example.com"
    assert env.payload.started_at_monotonic_ns == 1_000_000_000
    assert env.schema_version == 1
    assert env.daemon_id == "daemon-abc-123"
    assert env.emitted_at_monotonic_ns == 5_000_000_000


def test_page_navigated_envelope_round_trips() -> None:
    raw = _envelope(PAGE_NAVIGATED_PAYLOAD)
    env = EventEnvelope.model_validate(raw)
    assert isinstance(env.payload, PageNavigated)
    assert env.payload.type == "page_navigated"
    assert env.payload.url == "https://example.com/path"
    assert env.payload.dom_snapshot_hash == "sha256:deadbeef"


def test_pick_acknowledged_envelope_round_trips() -> None:
    raw = _envelope(PICK_ACKNOWLEDGED_PAYLOAD)
    env = EventEnvelope.model_validate(raw)
    assert isinstance(env.payload, PickAcknowledged)
    assert env.payload.type == "pick_acknowledged"
    assert env.payload.pick_id == "01HBBBBBBBBBBBBBBBBBBBBBB1"
    assert env.payload.pointing_session_id == "01HCCCCCCCCCCCCCCCCCCCCCC1"


def test_annotation_persisted_envelope_round_trips() -> None:
    raw = _envelope(ANNOTATION_PERSISTED_PAYLOAD)
    env = EventEnvelope.model_validate(raw)
    assert isinstance(env.payload, AnnotationPersisted)
    assert env.payload.type == "annotation_persisted"
    assert env.payload.annotation_id == "01HDDDDDDDDDDDDDDDDDDDDDD1"


# ---------------------------------------------------------------------------
# Discriminator — unbekannter type-Wert muss ValidationError auslösen
# ---------------------------------------------------------------------------


def test_unknown_payload_type_raises_validation_error() -> None:
    """Unbekannter `type`-Discriminator darf NICHT still durchfallen."""
    raw = _envelope({"type": "something_unknown", "foo": "bar"})
    with pytest.raises(ValidationError):
        EventEnvelope.model_validate(raw)


# ---------------------------------------------------------------------------
# schema_version — nur Literal[1] erlaubt
# ---------------------------------------------------------------------------


def test_wrong_schema_version_raises() -> None:
    raw = _envelope(SESSION_STARTED_PAYLOAD)
    raw["schema_version"] = 2
    with pytest.raises(ValidationError):
        EventEnvelope.model_validate(raw)


def test_missing_schema_version_raises() -> None:
    raw = _envelope(SESSION_STARTED_PAYLOAD)
    del raw["schema_version"]
    with pytest.raises(ValidationError):
        EventEnvelope.model_validate(raw)


# ---------------------------------------------------------------------------
# extra='forbid' — unbekannte Felder auf Envelope-Ebene verboten
# ---------------------------------------------------------------------------


def test_extra_field_on_envelope_raises() -> None:
    raw = _envelope(SESSION_STARTED_PAYLOAD)
    raw["surprise"] = "value"
    with pytest.raises(ValidationError):
        EventEnvelope.model_validate(raw)


def test_extra_field_on_payload_raises() -> None:
    payload = {**SESSION_STARTED_PAYLOAD, "rogue_field": "evil"}
    raw = _envelope(payload)
    with pytest.raises(ValidationError):
        EventEnvelope.model_validate(raw)


# ---------------------------------------------------------------------------
# frozen=True — Mutationsversuch nach Konstruktion muss fehlschlagen
# ---------------------------------------------------------------------------


def test_envelope_is_frozen() -> None:
    env = EventEnvelope.model_validate(_envelope(SESSION_STARTED_PAYLOAD))
    with pytest.raises((AttributeError, TypeError, ValidationError)):
        env.schema_version = 99  # type: ignore[misc]


def test_payload_is_frozen() -> None:
    env = EventEnvelope.model_validate(_envelope(SESSION_STARTED_PAYLOAD))
    with pytest.raises((AttributeError, TypeError, ValidationError)):
        env.payload.dns_domain = "mutated.example.com"  # type: ignore[misc]


# ---------------------------------------------------------------------------
# Pflichtfelder auf Payload-Ebene
# ---------------------------------------------------------------------------


def test_session_started_missing_page_session_id_raises() -> None:
    payload = {k: v for k, v in SESSION_STARTED_PAYLOAD.items() if k != "page_session_id"}
    with pytest.raises(ValidationError):
        EventEnvelope.model_validate(_envelope(payload))


def test_session_started_missing_dns_domain_raises() -> None:
    payload = {k: v for k, v in SESSION_STARTED_PAYLOAD.items() if k != "dns_domain"}
    with pytest.raises(ValidationError):
        EventEnvelope.model_validate(_envelope(payload))


def test_page_navigated_missing_url_raises() -> None:
    payload = {k: v for k, v in PAGE_NAVIGATED_PAYLOAD.items() if k != "url"}
    with pytest.raises(ValidationError):
        EventEnvelope.model_validate(_envelope(payload))


def test_pick_acknowledged_missing_pick_id_raises() -> None:
    payload = {k: v for k, v in PICK_ACKNOWLEDGED_PAYLOAD.items() if k != "pick_id"}
    with pytest.raises(ValidationError):
        EventEnvelope.model_validate(_envelope(payload))


def test_annotation_persisted_missing_annotation_id_raises() -> None:
    payload = {k: v for k, v in ANNOTATION_PERSISTED_PAYLOAD.items() if k != "annotation_id"}
    with pytest.raises(ValidationError):
        EventEnvelope.model_validate(_envelope(payload))


# ---------------------------------------------------------------------------
# model_dump — Round-Trip-Serialisierung (wichtig für JSON-Push-Serialisierung)
# ---------------------------------------------------------------------------


def test_session_started_model_dump_round_trip() -> None:
    """model_dump(mode='json') muss das Original-Dict reproduzieren."""
    raw = _envelope(SESSION_STARTED_PAYLOAD)
    env = EventEnvelope.model_validate(raw)
    dumped = env.model_dump(mode="json")
    assert dumped["schema_version"] == 1
    assert dumped["payload"]["type"] == "session_started"
    assert dumped["payload"]["dns_domain"] == "example.com"
