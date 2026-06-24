"""Tests for IntentRequest + IntentRequestQueue — synchronous, no pytest-anyio."""

from __future__ import annotations

import pytest
from pydantic import ValidationError

from frontprompt.queue import DEFAULT_BUFFER_SIZE, IntentRequest, IntentRequestQueue

# ---------------------------------------------------------------------------
# DEFAULT_BUFFER_SIZE
# ---------------------------------------------------------------------------


def test_default_buffer_size_is_positive() -> None:
    assert DEFAULT_BUFFER_SIZE > 0


# ---------------------------------------------------------------------------
# IntentRequest — Pydantic-Validierung
# ---------------------------------------------------------------------------


def test_intent_request_minimal_valid() -> None:
    """Minimal valides IntentRequest: nur intent_type gesetzt."""
    req = IntentRequest(intent_type="request.pick")
    assert req.intent_type == "request.pick"
    assert req.page_session_id is None
    assert req.interaction_flow_step_id is None
    assert req.dom_snapshot_hash is None


def test_intent_request_with_all_optional_fields() -> None:
    req = IntentRequest(
        intent_type="request.pick",
        page_session_id="01HXXXXXXXXXXXXXXXXXXXXXXXXX",
        interaction_flow_step_id="01HYYYYYYYYYYYYYYYYYYYYYY",
        dom_snapshot_hash="sha256:abcdef1234567890",
    )
    assert req.page_session_id == "01HXXXXXXXXXXXXXXXXXXXXXXXXX"
    assert req.interaction_flow_step_id == "01HYYYYYYYYYYYYYYYYYYYYYY"
    assert req.dom_snapshot_hash == "sha256:abcdef1234567890"


def test_intent_request_missing_intent_type_raises() -> None:
    with pytest.raises(ValidationError):
        IntentRequest()  # type: ignore[call-arg]


def test_intent_request_intent_type_empty_string_raises() -> None:
    """Leerer String ist kein valider intent_type (min_length=1)."""
    with pytest.raises(ValidationError):
        IntentRequest(intent_type="")


def test_intent_request_is_pydantic_model() -> None:
    from pydantic import BaseModel

    assert issubclass(IntentRequest, BaseModel)


# ---------------------------------------------------------------------------
# IntentRequestQueue — Konstruktion
# ---------------------------------------------------------------------------


def test_queue_construction_default_buffer() -> None:
    """Queue mit DEFAULT_BUFFER_SIZE erstellt."""
    q = IntentRequestQueue()
    assert q.max_buffer_size == DEFAULT_BUFFER_SIZE


def test_queue_construction_explicit_buffer() -> None:
    q = IntentRequestQueue(max_buffer_size=5)
    assert q.max_buffer_size == 5


def test_queue_construction_zero_buffer_raises() -> None:
    """max_buffer_size=0 ist semantisch falsch: bounded Queue muss mindestens 1 Slot haben."""
    with pytest.raises(ValueError, match="max_buffer_size"):
        IntentRequestQueue(max_buffer_size=0)


def test_queue_construction_negative_buffer_raises() -> None:
    with pytest.raises(ValueError, match="max_buffer_size"):
        IntentRequestQueue(max_buffer_size=-1)
