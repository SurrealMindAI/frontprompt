"""Wire-message tests für die Voice-Over bridge envelopes (sub-plan 02).

Covers the VoiceOverBridgeMessages per contracts.md:
  - RecordingStartRequested extended with with_voice_over + mic_device_id (additive)
  - SetMicDeviceRequested (new)
  - SetTranscriptionBackendRequested (new)
  - TriggerModelDownloadRequested (new)

Schema version bump 0.9.0 → 0.10.0 verified here.
OutboundMessage discriminated union routing + backward-compat + regression guard.
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
# Schema version bump — 0.9.0 → 0.10.0
# ---------------------------------------------------------------------------


def test_schema_version_bumped_to_0_11_0() -> None:
    """Bridge SCHEMA_VERSION is 0.11.0 after voiceover-models sub-plan 02 (bumped from 0.10.0)."""
    from frontprompt.bridge.messages import SCHEMA_VERSION

    assert SCHEMA_VERSION == "0.11.0"


# ---------------------------------------------------------------------------
# RecordingStartRequested — additive voice-over extension
# ---------------------------------------------------------------------------


def test_recording_start_requested_with_voice_over_and_mic_device() -> None:
    """with_voice_over=True + mic_device_id=3 serializes and deserializes correctly."""
    from frontprompt.bridge.messages import RecordingStartRequested

    msg = RecordingStartRequested(name="Voice Flow", description="", with_voice_over=True, mic_device_id=3)
    assert msg.with_voice_over is True
    assert msg.mic_device_id == 3
    assert msg.kind == "recording_start_requested"
    assert msg.schema_version == "0.11.0"


def test_recording_start_requested_with_voice_over_json_roundtrip() -> None:
    """with_voice_over + mic_device_id round-trip through JSON."""
    from frontprompt.bridge.messages import RecordingStartRequested

    msg = RecordingStartRequested(name="Test", description="", with_voice_over=True, mic_device_id=3)
    dumped = _outbound().dump_json(msg).decode("utf-8")
    restored = _outbound().validate_json(dumped)
    assert isinstance(restored, RecordingStartRequested)
    assert restored.with_voice_over is True
    assert restored.mic_device_id == 3


def test_recording_start_requested_backward_compat_defaults() -> None:
    """Backward compat: without new fields → with_voice_over=False, mic_device_id=None."""
    from frontprompt.bridge.messages import RecordingStartRequested

    # Old-style payload (no voice-over fields)
    payload = {"kind": "recording_start_requested", "schema_version": "0.8.0"}
    msg = _outbound().validate_python(payload)
    assert isinstance(msg, RecordingStartRequested)
    assert msg.with_voice_over is False
    assert msg.mic_device_id is None


def test_recording_start_requested_mic_device_id_none() -> None:
    """mic_device_id=None is valid (use system default)."""
    from frontprompt.bridge.messages import RecordingStartRequested

    msg = RecordingStartRequested(with_voice_over=True, mic_device_id=None)
    assert msg.mic_device_id is None
    assert msg.with_voice_over is True


# ---------------------------------------------------------------------------
# SetMicDeviceRequested
# ---------------------------------------------------------------------------


def test_set_mic_device_requested_with_none_system_default() -> None:
    """mic_device_id=None means system default — round-trips."""
    from frontprompt.bridge.messages import SetMicDeviceRequested

    msg = SetMicDeviceRequested(mic_device_id=None)
    assert msg.kind == "set_mic_device_requested"
    assert msg.mic_device_id is None
    assert msg.schema_version == "0.11.0"


def test_set_mic_device_requested_with_device_id_2() -> None:
    """mic_device_id=2 round-trips."""
    from frontprompt.bridge.messages import SetMicDeviceRequested

    msg = SetMicDeviceRequested(mic_device_id=2)
    assert msg.mic_device_id == 2


def test_set_mic_device_requested_json_roundtrip_none() -> None:
    """JSON roundtrip preserves mic_device_id=None."""
    from frontprompt.bridge.messages import SetMicDeviceRequested

    msg = SetMicDeviceRequested(mic_device_id=None)
    dumped = _outbound().dump_json(msg).decode("utf-8")
    restored = _outbound().validate_json(dumped)
    assert isinstance(restored, SetMicDeviceRequested)
    assert restored.mic_device_id is None


def test_set_mic_device_requested_json_roundtrip_device_id() -> None:
    """JSON roundtrip preserves mic_device_id=2."""
    from frontprompt.bridge.messages import SetMicDeviceRequested

    msg = SetMicDeviceRequested(mic_device_id=2)
    dumped = _outbound().dump_json(msg).decode("utf-8")
    restored = _outbound().validate_json(dumped)
    assert isinstance(restored, SetMicDeviceRequested)
    assert restored.mic_device_id == 2


def test_set_mic_device_requested_routes_via_outbound() -> None:
    """OutboundMessage union routes set_mic_device_requested correctly."""
    from frontprompt.bridge.messages import SetMicDeviceRequested

    payload = {"kind": "set_mic_device_requested", "schema_version": "0.10.0", "mic_device_id": None}
    msg = _outbound().validate_python(payload)
    assert isinstance(msg, SetMicDeviceRequested)
    assert msg.mic_device_id is None


def test_set_mic_device_requested_missing_mic_device_id_fails() -> None:
    """mic_device_id is required — missing raises ValidationError."""
    with pytest.raises(ValidationError):
        _outbound().validate_python(
            {"kind": "set_mic_device_requested", "schema_version": "0.10.0"}
        )


# ---------------------------------------------------------------------------
# SetTranscriptionBackendRequested
# ---------------------------------------------------------------------------


def test_set_transcription_backend_requested_with_backend_id() -> None:
    """backend_id='mlx_whisper' round-trips."""
    from frontprompt.bridge.messages import SetTranscriptionBackendRequested

    msg = SetTranscriptionBackendRequested(backend_id="mlx_whisper")
    assert msg.kind == "set_transcription_backend_requested"
    assert msg.backend_id == "mlx_whisper"
    assert msg.schema_version == "0.11.0"


def test_set_transcription_backend_requested_with_none_auto() -> None:
    """backend_id=None means auto (first ready backend) — round-trips."""
    from frontprompt.bridge.messages import SetTranscriptionBackendRequested

    msg = SetTranscriptionBackendRequested(backend_id=None)
    assert msg.backend_id is None


def test_set_transcription_backend_requested_json_roundtrip_backend_id() -> None:
    """JSON roundtrip preserves backend_id='mlx_whisper'."""
    from frontprompt.bridge.messages import SetTranscriptionBackendRequested

    msg = SetTranscriptionBackendRequested(backend_id="mlx_whisper")
    dumped = _outbound().dump_json(msg).decode("utf-8")
    restored = _outbound().validate_json(dumped)
    assert isinstance(restored, SetTranscriptionBackendRequested)
    assert restored.backend_id == "mlx_whisper"


def test_set_transcription_backend_requested_json_roundtrip_none() -> None:
    """JSON roundtrip preserves backend_id=None."""
    from frontprompt.bridge.messages import SetTranscriptionBackendRequested

    msg = SetTranscriptionBackendRequested(backend_id=None)
    dumped = _outbound().dump_json(msg).decode("utf-8")
    restored = _outbound().validate_json(dumped)
    assert isinstance(restored, SetTranscriptionBackendRequested)
    assert restored.backend_id is None


def test_set_transcription_backend_requested_routes_via_outbound() -> None:
    """OutboundMessage union routes set_transcription_backend_requested correctly."""
    from frontprompt.bridge.messages import SetTranscriptionBackendRequested

    payload = {
        "kind": "set_transcription_backend_requested",
        "schema_version": "0.10.0",
        "backend_id": "mlx_whisper",
    }
    msg = _outbound().validate_python(payload)
    assert isinstance(msg, SetTranscriptionBackendRequested)
    assert msg.backend_id == "mlx_whisper"


def test_set_transcription_backend_requested_missing_backend_id_fails() -> None:
    """backend_id is required — missing raises ValidationError."""
    with pytest.raises(ValidationError):
        _outbound().validate_python(
            {"kind": "set_transcription_backend_requested", "schema_version": "0.10.0"}
        )


# ---------------------------------------------------------------------------
# TriggerModelDownloadRequested
# ---------------------------------------------------------------------------


def test_trigger_model_download_requested_with_backend_id() -> None:
    """backend_id='mlx_whisper' — initiates ensure() on the named backend."""
    from frontprompt.bridge.messages import TriggerModelDownloadRequested

    msg = TriggerModelDownloadRequested(backend_id="mlx_whisper")
    assert msg.kind == "trigger_model_download_requested"
    assert msg.backend_id == "mlx_whisper"
    assert msg.schema_version == "0.11.0"


def test_trigger_model_download_requested_json_roundtrip() -> None:
    """JSON roundtrip preserves backend_id."""
    from frontprompt.bridge.messages import TriggerModelDownloadRequested

    msg = TriggerModelDownloadRequested(backend_id="mlx_whisper")
    dumped = _outbound().dump_json(msg).decode("utf-8")
    restored = _outbound().validate_json(dumped)
    assert isinstance(restored, TriggerModelDownloadRequested)
    assert restored.backend_id == "mlx_whisper"


def test_trigger_model_download_requested_routes_via_outbound() -> None:
    """OutboundMessage union routes trigger_model_download_requested correctly."""
    from frontprompt.bridge.messages import TriggerModelDownloadRequested

    payload = {
        "kind": "trigger_model_download_requested",
        "schema_version": "0.10.0",
        "backend_id": "mlx_whisper",
    }
    msg = _outbound().validate_python(payload)
    assert isinstance(msg, TriggerModelDownloadRequested)
    assert msg.backend_id == "mlx_whisper"


def test_trigger_model_download_requested_missing_backend_id_fails() -> None:
    """backend_id is required (non-None for download trigger) — missing raises ValidationError."""
    with pytest.raises(ValidationError):
        _outbound().validate_python(
            {"kind": "trigger_model_download_requested", "schema_version": "0.10.0"}
        )


# ---------------------------------------------------------------------------
# Codegen roots — all 3 new classes must be in __codegen_roots__
# ---------------------------------------------------------------------------


def test_voice_over_message_classes_in_codegen_roots() -> None:
    """All new voice-over bridge message classes are in __codegen_roots__."""
    from frontprompt.bridge.messages import __codegen_roots__

    expected = [
        "SetMicDeviceRequested",
        "SetTranscriptionBackendRequested",
        "TriggerModelDownloadRequested",
    ]
    for name in expected:
        assert name in __codegen_roots__, f"{name} missing in __codegen_roots__"


# ---------------------------------------------------------------------------
# Regression — existing outbound variants still resolve correctly
# ---------------------------------------------------------------------------


def test_existing_recording_outbound_variants_still_route() -> None:
    """Regression guard: existing recording kinds are unaffected by the new union entries."""
    from frontprompt.bridge.messages import (
        AssertionDeletedRequested,
        RecordingStartRequested,
        RecordingStopRequested,
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
        (
            {
                "kind": "assertion_deleted_requested",
                "schema_version": "0.9.0",
                "recording_id": "rec-1",
                "assertion_id": "asr-1",
            },
            AssertionDeletedRequested,
        ),
    ]
    for payload, expected_cls in cases:
        msg = _outbound().validate_python(payload)
        assert isinstance(msg, expected_cls), f"Expected {expected_cls.__name__}, got {type(msg).__name__}"
