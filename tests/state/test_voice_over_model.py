"""Tests für Voice-Over state models — sections 1 + 2 of voice-over sub-plan 01.

Schema 0.10.0 additions: TranscriptSegmentEntry (7th TimelineEntry variant),
voice-over fields on Recording/RecordingMeta, MicrophoneState, SettingsState,
TranscriptionState.
"""

from __future__ import annotations

import pytest
from pydantic import TypeAdapter, ValidationError

from frontprompt.state.state import (
    MicrophoneDevice,
    MicrophoneState,
    Recording,
    RecordingMeta,
    RecordingStatus,
    SettingsState,
    StateSnapshot,
    TimelineEntry,
    TranscriptSegmentEntry,
    TranscriptionBackendInfo,
    TranscriptionBackendStatus,
    TranscriptionState,
    TranscriptionStatus,
)


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _panel_state():  # type: ignore[no-untyped-def]
    from frontprompt.state.state import PanelStateView, PanelView

    return PanelStateView(
        top=PanelView(open=True, size=56),
        bottom=PanelView(open=False, size=220),
        left=PanelView(open=True, size=300),
        right=PanelView(open=True, size=340),
    )


# ---------------------------------------------------------------------------
# Section 1: TranscriptionStatus
# ---------------------------------------------------------------------------


def test_transcription_status_all_values_accepted() -> None:
    """TranscriptionStatus accepts all five literal values."""
    ta: TypeAdapter[TranscriptionStatus] = TypeAdapter(TranscriptionStatus)
    for value in ["none", "pending", "transcribing", "done", "failed"]:
        assert ta.validate_python(value) == value


def test_transcription_status_rejects_unknown() -> None:
    """TranscriptionStatus rejects invalid literal values."""
    ta: TypeAdapter[TranscriptionStatus] = TypeAdapter(TranscriptionStatus)
    with pytest.raises(ValidationError):
        ta.validate_python("invalid_status")


# ---------------------------------------------------------------------------
# Section 1: Recording with voice-over fields
# ---------------------------------------------------------------------------


def test_recording_with_voice_over_fields_roundtrip() -> None:
    """Recording with has_voice_over=True, audio_path, transcription_status='done' round-trips."""
    rec = Recording(
        recording_id="rec-vo-001",
        name="Test Recording",
        status="active",
        started_at_ms=1_700_000_000_000,
        has_voice_over=True,
        audio_path="/tmp/recording-rec-vo-001.wav",
        transcription_status="done",
        transcription_error=None,
    )
    assert rec.has_voice_over is True
    assert rec.audio_path == "/tmp/recording-rec-vo-001.wav"
    assert rec.transcription_status == "done"
    assert rec.transcription_error is None

    restored = Recording.model_validate_json(rec.model_dump_json())
    assert restored == rec


def test_recording_voice_over_defaults() -> None:
    """Recording voice-over fields default correctly: False, None, 'none', None."""
    rec = Recording(
        recording_id="rec-vo-002",
        name="Default",
        status="active",
        started_at_ms=0,
    )
    assert rec.has_voice_over is False
    assert rec.audio_path is None
    assert rec.transcription_status == "none"
    assert rec.transcription_error is None


def test_recording_transcription_error_only_on_full_recording() -> None:
    """transcription_error is present on Recording only (not on RecordingMeta)."""
    rec = Recording(
        recording_id="rec-vo-003",
        name="Failed",
        status="stopped",
        started_at_ms=0,
        has_voice_over=True,
        transcription_status="failed",
        transcription_error="Model not available",
    )
    assert rec.transcription_error == "Model not available"
    # RecordingMeta does NOT have transcription_error field
    meta = RecordingMeta(
        recording_id="rec-vo-003",
        name="Failed",
        status="stopped",
        started_at_ms=0,
        entry_count=0,
    )
    assert not hasattr(meta, "transcription_error")


def test_recording_meta_with_voice_over_fields_roundtrip() -> None:
    """RecordingMeta with voice-over fields round-trips."""
    meta = RecordingMeta(
        recording_id="rec-vo-001",
        name="Test",
        status="stopped",
        started_at_ms=1_000,
        entry_count=5,
        has_voice_over=True,
        audio_path="/tmp/rec.wav",
        transcription_status="pending",
    )
    assert meta.has_voice_over is True
    assert meta.audio_path == "/tmp/rec.wav"
    assert meta.transcription_status == "pending"

    restored = RecordingMeta.model_validate_json(meta.model_dump_json())
    assert restored == meta


def test_recording_meta_voice_over_defaults() -> None:
    """RecordingMeta voice-over fields default correctly."""
    meta = RecordingMeta(
        recording_id="rec-vo-003",
        name="Default",
        status="active",
        started_at_ms=0,
        entry_count=0,
    )
    assert meta.has_voice_over is False
    assert meta.audio_path is None
    assert meta.transcription_status == "none"


# ---------------------------------------------------------------------------
# Section 1: TranscriptSegmentEntry — discriminated union (7th variant)
# ---------------------------------------------------------------------------


def test_transcript_segment_entry_roundtrip_through_discriminated_union() -> None:
    """TranscriptSegmentEntry serializes via Pydantic discriminated union through TimelineEntry."""
    entry = TranscriptSegmentEntry(
        kind="transcript_segment",
        seq=3,
        timestamp_ms=1_700_000_005_000,
        start_ms=5000,
        end_ms=8000,
        text="Hello world",
        backend_id="mlx_whisper",
    )
    ta: TypeAdapter[TimelineEntry] = TypeAdapter(TimelineEntry)
    dumped = entry.model_dump_json()
    restored = ta.validate_json(dumped)
    assert restored == entry
    assert restored.kind == "transcript_segment"  # type: ignore[union-attr]
    assert restored.text == "Hello world"  # type: ignore[union-attr]


def test_timeline_entry_routes_transcript_segment_kind() -> None:
    """TimelineEntry discriminated union routes kind='transcript_segment' to TranscriptSegmentEntry."""
    ta: TypeAdapter[TimelineEntry] = TypeAdapter(TimelineEntry)
    data = {
        "kind": "transcript_segment",
        "seq": 0,
        "timestamp_ms": 1000,
        "start_ms": 0,
        "end_ms": 1000,
        "text": "Test segment",
        "backend_id": "mlx_whisper",
    }
    entry = ta.validate_python(data)
    assert isinstance(entry, TranscriptSegmentEntry)
    assert entry.text == "Test segment"
    assert entry.backend_id == "mlx_whisper"
    assert entry.start_ms == 0
    assert entry.end_ms == 1000


def test_timeline_entry_kind_includes_transcript_segment() -> None:
    """TimelineEntryKind Literal includes 'transcript_segment'."""
    from frontprompt.state.state import TimelineEntryKind
    from pydantic import TypeAdapter

    ta: TypeAdapter[TimelineEntryKind] = TypeAdapter(TimelineEntryKind)
    assert ta.validate_python("transcript_segment") == "transcript_segment"


def test_recording_status_remains_compatible() -> None:
    """RecordingStatus is unchanged — voice-over status is a separate TranscriptionStatus."""
    ta: TypeAdapter[RecordingStatus] = TypeAdapter(RecordingStatus)
    assert ta.validate_python("active") == "active"
    assert ta.validate_python("stopped") == "stopped"
    # TranscriptionStatus values must NOT be valid RecordingStatus values
    with pytest.raises(ValidationError):
        ta.validate_python("pending")
    with pytest.raises(ValidationError):
        ta.validate_python("done")


# ---------------------------------------------------------------------------
# Section 1: StateSnapshot schema 0.10.0 — new additive fields
# ---------------------------------------------------------------------------


def test_state_snapshot_schema_version_is_0_10_0() -> None:
    """StateSnapshot default schema_version is 0.10.0 after voice-over extension."""
    snap = StateSnapshot(panel_state=_panel_state())
    assert snap.schema_version == "0.10.0"


def test_state_snapshot_includes_microphone_state() -> None:
    """StateSnapshot includes microphone_state field (MicrophoneState)."""
    snap = StateSnapshot(panel_state=_panel_state())
    assert isinstance(snap.microphone_state, MicrophoneState)
    assert snap.microphone_state.devices == []


def test_state_snapshot_includes_settings_state() -> None:
    """StateSnapshot includes settings_state field (SettingsState)."""
    snap = StateSnapshot(panel_state=_panel_state())
    assert isinstance(snap.settings_state, SettingsState)
    assert snap.settings_state.voice_over_enabled is False


def test_state_snapshot_includes_transcription_state() -> None:
    """StateSnapshot includes transcription_state field (TranscriptionState)."""
    snap = StateSnapshot(panel_state=_panel_state())
    assert isinstance(snap.transcription_state, TranscriptionState)
    assert snap.transcription_state.backends == []


def test_state_snapshot_old_without_new_fields_deserializes_via_defaults() -> None:
    """Old StateSnapshot without microphone/settings/transcription_state deserializes without error."""
    old_data = {
        "schema_version": "0.9.0",
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
        "recordings_state": {
            "active_recording_id": None,
            "recordings": [],
            "active_detail_recording_id": None,
            "detail_recording": None,
            "active_replay_progress": None,
        },
        # microphone_state, settings_state, transcription_state are ABSENT
    }
    snap = StateSnapshot.model_validate(old_data)
    assert snap.microphone_state.devices == []
    assert snap.settings_state.voice_over_enabled is False
    assert snap.transcription_state.backends == []


# ---------------------------------------------------------------------------
# Section 2: MicrophoneDevice / MicrophoneState
# ---------------------------------------------------------------------------


def test_microphone_device_roundtrip() -> None:
    """MicrophoneDevice round-trips with all fields."""
    device = MicrophoneDevice(
        device_id=2,
        name="Built-in Microphone",
        channels=1,
        default_sample_rate=44100.0,
    )
    restored = MicrophoneDevice.model_validate_json(device.model_dump_json())
    assert restored == device
    assert restored.device_id == 2
    assert restored.name == "Built-in Microphone"
    assert restored.channels == 1
    assert restored.default_sample_rate == 44100.0


def test_microphone_state_empty_devices_valid_initial_state() -> None:
    """MicrophoneState with empty devices list is valid (initial state before first watcher cycle)."""
    state = MicrophoneState()
    assert state.devices == []
    assert state.selected_device_id is None
    assert state.system_default_device_id is None


def test_microphone_state_selected_device_id_none_is_valid() -> None:
    """MicrophoneState with selected_device_id=None (system default) is valid."""
    state = MicrophoneState(selected_device_id=None)
    assert state.selected_device_id is None


def test_microphone_state_roundtrip_with_devices_and_selection() -> None:
    """MicrophoneState round-trips with devices and selection."""
    state = MicrophoneState(
        devices=[
            MicrophoneDevice(device_id=0, name="Default Mic", channels=2, default_sample_rate=48000.0),
            MicrophoneDevice(device_id=2, name="Built-in Mic", channels=1, default_sample_rate=44100.0),
        ],
        selected_device_id=2,
        system_default_device_id=0,
    )
    restored = MicrophoneState.model_validate_json(state.model_dump_json())
    assert restored == state
    assert len(restored.devices) == 2
    assert restored.selected_device_id == 2
    assert restored.system_default_device_id == 0


# ---------------------------------------------------------------------------
# Section 2: SettingsState
# ---------------------------------------------------------------------------


def test_settings_state_defaults_voice_over_disabled() -> None:
    """SettingsState defaults: voice_over_enabled=False, selected_transcription_backend_id=None."""
    settings = SettingsState()
    assert settings.voice_over_enabled is False
    assert settings.selected_transcription_backend_id is None


def test_settings_state_roundtrip_with_all_fields() -> None:
    """SettingsState round-trips with all fields set."""
    settings = SettingsState(
        voice_over_enabled=True,
        selected_transcription_backend_id="mlx_whisper",
    )
    restored = SettingsState.model_validate_json(settings.model_dump_json())
    assert restored == settings
    assert restored.voice_over_enabled is True
    assert restored.selected_transcription_backend_id == "mlx_whisper"


def test_settings_state_backend_id_none_is_auto() -> None:
    """SettingsState with selected_transcription_backend_id=None means auto-select."""
    settings = SettingsState(voice_over_enabled=True, selected_transcription_backend_id=None)
    assert settings.selected_transcription_backend_id is None


# ---------------------------------------------------------------------------
# Section 2: TranscriptionBackendInfo / TranscriptionState
# ---------------------------------------------------------------------------


def test_transcription_backend_status_all_values_accepted() -> None:
    """TranscriptionBackendStatus accepts all six valid values."""
    ta: TypeAdapter[TranscriptionBackendStatus] = TypeAdapter(TranscriptionBackendStatus)
    for value in ["unavailable", "missing_dep", "needs_download", "downloading", "ready", "error"]:
        assert ta.validate_python(value) == value


def test_transcription_backend_status_rejects_unknown() -> None:
    """TranscriptionBackendStatus rejects unknown values."""
    ta: TypeAdapter[TranscriptionBackendStatus] = TypeAdapter(TranscriptionBackendStatus)
    with pytest.raises(ValidationError):
        ta.validate_python("broken")


def test_transcription_backend_info_downloading_roundtrip() -> None:
    """TranscriptionBackendInfo with status='downloading' and download_progress=0.5 round-trips."""
    info = TranscriptionBackendInfo(
        backend_id="mlx_whisper",
        display_name="mlx-whisper (Apple Silicon)",
        status="downloading",
        download_progress=0.5,
    )
    restored = TranscriptionBackendInfo.model_validate_json(info.model_dump_json())
    assert restored == info
    assert restored.download_progress == 0.5


def test_transcription_backend_info_defaults() -> None:
    """TranscriptionBackendInfo defaults: download_progress=None, error_message=None."""
    info = TranscriptionBackendInfo(
        backend_id="mlx_whisper",
        display_name="mlx-whisper (Apple Silicon)",
        status="ready",
    )
    assert info.download_progress is None
    assert info.error_message is None


def test_transcription_state_one_backend_unavailable_roundtrip() -> None:
    """TranscriptionState with one backend in 'unavailable' status round-trips."""
    state = TranscriptionState(
        backends=[
            TranscriptionBackendInfo(
                backend_id="mlx_whisper",
                display_name="mlx-whisper (Apple Silicon)",
                status="unavailable",
            )
        ]
    )
    restored = TranscriptionState.model_validate_json(state.model_dump_json())
    assert len(restored.backends) == 1
    assert restored.backends[0].status == "unavailable"
    assert restored.backends[0].backend_id == "mlx_whisper"


def test_transcription_state_empty_backends_valid() -> None:
    """TranscriptionState with empty backends list is valid."""
    state = TranscriptionState()
    assert state.backends == []


# ---------------------------------------------------------------------------
# __codegen_roots__ — new voice-over types included
# ---------------------------------------------------------------------------


def test_codegen_roots_includes_voice_over_models() -> None:
    """__codegen_roots__ includes all new voice-over models."""
    from frontprompt.state.state import __codegen_roots__

    for name in [
        "TranscriptionStatus",
        "TranscriptSegmentEntry",
        "MicrophoneDevice",
        "MicrophoneState",
        "SettingsState",
        "TranscriptionBackendStatus",
        "TranscriptionBackendInfo",
        "TranscriptionState",
    ]:
        assert name in __codegen_roots__, f"{name} missing from __codegen_roots__"
