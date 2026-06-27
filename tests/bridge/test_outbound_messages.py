"""Wire-message tests für SetTranscriptionModelRequested (sub-plan 02 voiceover-models).

Covers:
  - SetTranscriptionModelRequested (new, Schema 0.11.0)
  - SCHEMA_VERSION bump 0.10.0 → 0.11.0
  - OutboundMessage union routing
  - __all__ completeness guard
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
# Schema version bump — 0.10.0 → 0.11.0
# ---------------------------------------------------------------------------


def test_bridge_schema_version_is_011() -> None:
    """Bridge SCHEMA_VERSION is 0.11.0 after voiceover-models sub-plan 02."""
    from frontprompt.bridge.messages import SCHEMA_VERSION

    assert SCHEMA_VERSION == "0.11.0"


# ---------------------------------------------------------------------------
# SetTranscriptionModelRequested — kind discriminator
# ---------------------------------------------------------------------------


def test_set_transcription_model_requested_kind_literal() -> None:
    """The kind discriminator field equals 'set_transcription_model_requested'."""
    from frontprompt.bridge.messages import SetTranscriptionModelRequested

    msg = SetTranscriptionModelRequested(backend_id="mlx_whisper", model_id=None)
    assert msg.kind == "set_transcription_model_requested"


# ---------------------------------------------------------------------------
# SetTranscriptionModelRequested — model_id variants
# ---------------------------------------------------------------------------


def test_set_transcription_model_requested_model_id_none_valid() -> None:
    """model_id=None passes Pydantic validation (revert-to-default intent)."""
    from frontprompt.bridge.messages import SetTranscriptionModelRequested

    msg = SetTranscriptionModelRequested(backend_id="mlx_whisper", model_id=None)
    assert msg.model_id is None
    assert msg.backend_id == "mlx_whisper"


def test_set_transcription_model_requested_model_id_string_valid() -> None:
    """model_id='whisper-large-v3-turbo' passes validation."""
    from frontprompt.bridge.messages import SetTranscriptionModelRequested

    msg = SetTranscriptionModelRequested(
        backend_id="mlx_whisper",
        model_id="whisper-large-v3-turbo",
    )
    assert msg.model_id == "whisper-large-v3-turbo"
    assert msg.backend_id == "mlx_whisper"


def test_set_transcription_model_requested_schema_version() -> None:
    """schema_version reflects the bumped SCHEMA_VERSION (0.11.0)."""
    from frontprompt.bridge.messages import SetTranscriptionModelRequested

    msg = SetTranscriptionModelRequested(backend_id="mlx_whisper", model_id=None)
    assert msg.schema_version == "0.11.0"


def test_set_transcription_model_requested_json_roundtrip_none() -> None:
    """JSON roundtrip preserves model_id=None."""
    from frontprompt.bridge.messages import SetTranscriptionModelRequested

    msg = SetTranscriptionModelRequested(backend_id="mlx_whisper", model_id=None)
    dumped = _outbound().dump_json(msg).decode("utf-8")
    restored = _outbound().validate_json(dumped)
    assert isinstance(restored, SetTranscriptionModelRequested)
    assert restored.model_id is None
    assert restored.backend_id == "mlx_whisper"


def test_set_transcription_model_requested_json_roundtrip_model_id() -> None:
    """JSON roundtrip preserves model_id string."""
    from frontprompt.bridge.messages import SetTranscriptionModelRequested

    msg = SetTranscriptionModelRequested(backend_id="mlx_whisper", model_id="whisper-large-v3-turbo")
    dumped = _outbound().dump_json(msg).decode("utf-8")
    restored = _outbound().validate_json(dumped)
    assert isinstance(restored, SetTranscriptionModelRequested)
    assert restored.model_id == "whisper-large-v3-turbo"


# ---------------------------------------------------------------------------
# OutboundMessage union routing
# ---------------------------------------------------------------------------


def test_outbound_message_union_includes_set_transcription_model() -> None:
    """OutboundMessage union discriminates on 'set_transcription_model_requested'
    and resolves to SetTranscriptionModelRequested."""
    from frontprompt.bridge.messages import SetTranscriptionModelRequested

    payload = {
        "kind": "set_transcription_model_requested",
        "schema_version": "0.11.0",
        "backend_id": "mlx_whisper",
        "model_id": "whisper-large-v3-turbo",
    }
    msg = _outbound().validate_python(payload)
    assert isinstance(msg, SetTranscriptionModelRequested)
    assert msg.model_id == "whisper-large-v3-turbo"
    assert msg.backend_id == "mlx_whisper"


def test_set_transcription_model_requested_missing_backend_id_fails() -> None:
    """backend_id is required — missing raises ValidationError."""
    with pytest.raises(ValidationError):
        _outbound().validate_python(
            {
                "kind": "set_transcription_model_requested",
                "schema_version": "0.11.0",
                "model_id": None,
            }
        )


# ---------------------------------------------------------------------------
# __all__ completeness guard
# ---------------------------------------------------------------------------


def test_outbound_collection_complete() -> None:
    """SetTranscriptionModelRequested is in __all__ and __codegen_roots__
    (no orphan message classes)."""
    from frontprompt.bridge import messages

    assert "SetTranscriptionModelRequested" in messages.__all__, (
        "SetTranscriptionModelRequested missing from __all__"
    )
    assert "SetTranscriptionModelRequested" in messages.__codegen_roots__, (
        "SetTranscriptionModelRequested missing from __codegen_roots__"
    )
