"""Tests für StateManager voice-over mutation methods — section 4 of voice-over sub-plan 01.

Covers:
- set_audio_path / set_transcription_status — voice-over meta mutations
- append_transcript_segments — batch append (single lock hold, single broadcast)
- update_microphone_state — topology-hash-guarded device list replacement
- set_mic_device — persists mic device selection to settings
- set_settings — updates durable settings + persists
- update_transcription_backend_status — updates backend info in TranscriptionState
- snapshot() includes microphone_state, settings_state, transcription_state
- _recording_to_meta propagates voice-over fields
- unknown recording_id is a no-op (no crash)
"""

from __future__ import annotations

import anyio
import pytest

from frontprompt.state.persistence.in_memory import InMemoryPersistence
from frontprompt.state.state import (
    MicrophoneDevice,
    MicrophoneState,
    Recording,
    SettingsState,
    TranscriptSegmentEntry,
    TranscriptionBackendInfo,
    TranscriptionState,
)


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _make_manager(
    *,
    transcription_state: TranscriptionState | None = None,
    persistence: InMemoryPersistence | None = None,
):
    """Build a StateManager with an InMemoryPersistence and a test session-id."""
    from frontprompt.state.manager import StateManager

    return StateManager(
        session_id="test-session",
        persistence=persistence or InMemoryPersistence(),
        transcription_state=transcription_state,
    )


def _make_recording_in_manager(manager):
    """Synchronously start a recording via anyio.from_thread.run_sync wrapper."""

    async def _run():
        return await manager.start_recording(name="VO Test Recording")

    return anyio.from_thread.run_sync(anyio.from_thread.run_sync)


async def _start(manager) -> str:
    """Start a recording and return its recording_id."""
    snap = await manager.start_recording(name="Voice Test")
    return snap.recordings_state.active_recording_id


# ---------------------------------------------------------------------------
# Section 4: snapshot() includes voice-over state subtrees
# ---------------------------------------------------------------------------


@pytest.mark.anyio
async def test_snapshot_includes_microphone_state() -> None:
    """snapshot() includes microphone_state with correct defaults."""
    manager = _make_manager()
    snap = manager.snapshot()
    assert snap.microphone_state is not None
    assert snap.microphone_state.devices == []
    assert snap.microphone_state.selected_device_id is None


@pytest.mark.anyio
async def test_snapshot_includes_settings_state() -> None:
    """snapshot() includes settings_state with correct defaults."""
    manager = _make_manager()
    snap = manager.snapshot()
    assert snap.settings_state is not None
    assert snap.settings_state.voice_over_enabled is False
    assert snap.settings_state.selected_transcription_backend_id is None


@pytest.mark.anyio
async def test_snapshot_includes_transcription_state() -> None:
    """snapshot() includes transcription_state (from constructor injection)."""
    ts = TranscriptionState(backends=[TranscriptionBackendInfo(backend_id="mlx", display_name="MLX Whisper", status="unavailable")])
    manager = _make_manager(transcription_state=ts)
    snap = manager.snapshot()
    assert len(snap.transcription_state.backends) == 1
    assert snap.transcription_state.backends[0].backend_id == "mlx"


# ---------------------------------------------------------------------------
# Section 4: _recording_to_meta propagates voice-over fields
# ---------------------------------------------------------------------------


def test_recording_to_meta_propagates_voice_over_fields() -> None:
    """_recording_to_meta includes has_voice_over, audio_path, transcription_status."""
    from frontprompt.state.manager import StateManager

    recording = Recording(
        recording_id="rec-001",
        name="Test",
        status="stopped",
        started_at_ms=1_000_000,
        has_voice_over=True,
        audio_path="/tmp/rec.wav",
        transcription_status="done",
    )
    meta = StateManager._recording_to_meta(recording)
    assert meta.has_voice_over is True
    assert meta.audio_path == "/tmp/rec.wav"
    assert meta.transcription_status == "done"


def test_recording_to_meta_defaults_voice_over_fields() -> None:
    """_recording_to_meta defaults have has_voice_over=False, audio_path=None."""
    from frontprompt.state.manager import StateManager

    recording = Recording(
        recording_id="rec-002",
        name="Test",
        status="active",
        started_at_ms=1_000_000,
    )
    meta = StateManager._recording_to_meta(recording)
    assert meta.has_voice_over is False
    assert meta.audio_path is None
    assert meta.transcription_status == "none"


# ---------------------------------------------------------------------------
# Section 4: set_audio_path
# ---------------------------------------------------------------------------


@pytest.mark.anyio
async def test_set_audio_path_updates_recording_and_snapshot() -> None:
    """set_audio_path sets audio_path on recording; snapshot recordings_state reflects it."""
    manager = _make_manager()
    recording_id = await _start(manager)

    snap = await manager.set_audio_path(recording_id, "/var/audio/rec.wav")

    # In-memory recording updated
    recording = manager.get_recording(recording_id)
    assert recording is not None
    assert recording.audio_path == "/var/audio/rec.wav"

    # Meta in snapshot updated
    meta = next(m for m in snap.recordings_state.recordings if m.recording_id == recording_id)
    assert meta.audio_path == "/var/audio/rec.wav"


@pytest.mark.anyio
async def test_set_audio_path_unknown_recording_is_noop() -> None:
    """set_audio_path on unknown recording_id is a no-op — does not raise."""
    manager = _make_manager()
    snap = await manager.set_audio_path("nonexistent-id", "/tmp/x.wav")
    # Should return a snapshot without crashing
    assert snap is not None


# ---------------------------------------------------------------------------
# Section 4: set_transcription_status
# ---------------------------------------------------------------------------


@pytest.mark.anyio
async def test_set_transcription_status_updates_and_broadcasts() -> None:
    """set_transcription_status updates status atomically; snapshot reflects it."""
    manager = _make_manager()
    recording_id = await _start(manager)

    snap = await manager.set_transcription_status(recording_id, "transcribing", None)
    recording = manager.get_recording(recording_id)
    assert recording is not None
    assert recording.transcription_status == "transcribing"
    assert recording.transcription_error is None

    meta = next(m for m in snap.recordings_state.recordings if m.recording_id == recording_id)
    assert meta.transcription_status == "transcribing"


@pytest.mark.anyio
async def test_set_transcription_status_with_error() -> None:
    """set_transcription_status with error string persists transcription_error."""
    manager = _make_manager()
    recording_id = await _start(manager)

    await manager.set_transcription_status(recording_id, "failed", "Model load failed: OOM")
    recording = manager.get_recording(recording_id)
    assert recording is not None
    assert recording.transcription_status == "failed"
    assert recording.transcription_error == "Model load failed: OOM"


@pytest.mark.anyio
async def test_set_transcription_status_unknown_recording_is_noop() -> None:
    """set_transcription_status on unknown recording_id is a no-op."""
    manager = _make_manager()
    snap = await manager.set_transcription_status("nonexistent", "done", None)
    assert snap is not None


# ---------------------------------------------------------------------------
# Section 4: append_transcript_segments
# ---------------------------------------------------------------------------


@pytest.mark.anyio
async def test_append_transcript_segments_appends_all_segments() -> None:
    """append_transcript_segments appends all segments with correct seq."""
    manager = _make_manager()
    recording_id = await _start(manager)

    segments = [
        TranscriptSegmentEntry(
            kind="transcript_segment",
            seq=0,  # will be overwritten by manager
            timestamp_ms=0,  # will be overwritten: started_at_ms + start_ms
            start_ms=0,
            end_ms=3000,
            text="Hello world",
            backend_id="mlx_whisper",
        ),
        TranscriptSegmentEntry(
            kind="transcript_segment",
            seq=0,
            timestamp_ms=0,
            start_ms=3000,
            end_ms=6000,
            text="How are you",
            backend_id="mlx_whisper",
        ),
    ]

    await manager.append_transcript_segments(recording_id, segments, backend_id="mlx_whisper")

    recording = manager.get_recording(recording_id)
    assert recording is not None
    assert len(recording.entries) == 2
    assert recording.entries[0].kind == "transcript_segment"
    assert recording.entries[0].text == "Hello world"  # type: ignore[union-attr]
    assert recording.entries[1].kind == "transcript_segment"
    assert recording.entries[1].text == "How are you"  # type: ignore[union-attr]
    # seq must be monotonically assigned by Python
    assert recording.entries[0].seq == 0
    assert recording.entries[1].seq == 1


@pytest.mark.anyio
async def test_append_transcript_segments_stamps_timestamp_from_started_at() -> None:
    """append_transcript_segments stamps timestamp_ms = started_at_ms + start_ms."""
    manager = _make_manager()
    recording_id = await _start(manager)
    recording = manager.get_recording(recording_id)
    assert recording is not None
    started_at_ms = recording.started_at_ms

    segment = TranscriptSegmentEntry(
        kind="transcript_segment",
        seq=0,
        timestamp_ms=0,
        start_ms=5000,
        end_ms=8000,
        text="Test",
        backend_id="mlx_whisper",
    )
    await manager.append_transcript_segments(recording_id, [segment], backend_id="mlx_whisper")

    entry = recording.entries[0]
    assert entry.timestamp_ms == started_at_ms + 5000  # type: ignore[union-attr]


@pytest.mark.anyio
async def test_append_transcript_segments_sets_status_done() -> None:
    """append_transcript_segments sets transcription_status='done' in the same call."""
    manager = _make_manager()
    recording_id = await _start(manager)

    await manager.set_transcription_status(recording_id, "transcribing", None)

    segment = TranscriptSegmentEntry(
        kind="transcript_segment",
        seq=0,
        timestamp_ms=0,
        start_ms=0,
        end_ms=1000,
        text="Done",
        backend_id="mlx_whisper",
    )
    await manager.append_transcript_segments(recording_id, [segment], backend_id="mlx_whisper")

    recording = manager.get_recording(recording_id)
    assert recording is not None
    assert recording.transcription_status == "done"


@pytest.mark.anyio
async def test_append_transcript_segments_broadcasts_once() -> None:
    """append_transcript_segments fires listener exactly once for N segments."""
    manager = _make_manager()
    recording_id = await _start(manager)

    broadcast_count = 0

    def _listener(snap):
        nonlocal broadcast_count
        broadcast_count += 1

    manager.add_snapshot_listener(_listener)
    # Reset counter after start_recording broadcast
    broadcast_count = 0

    segments = [
        TranscriptSegmentEntry(kind="transcript_segment", seq=0, timestamp_ms=0, start_ms=0, end_ms=1000, text=f"Seg {i}", backend_id="mlx")
        for i in range(5)
    ]
    await manager.append_transcript_segments(recording_id, segments, backend_id="mlx")

    assert broadcast_count == 1


@pytest.mark.anyio
async def test_append_transcript_segments_unknown_recording_is_noop() -> None:
    """append_transcript_segments on unknown recording_id is a no-op."""
    manager = _make_manager()
    segment = TranscriptSegmentEntry(kind="transcript_segment", seq=0, timestamp_ms=0, start_ms=0, end_ms=1000, text="X", backend_id="mlx")
    snap = await manager.append_transcript_segments("nonexistent", [segment], backend_id="mlx")
    assert snap is not None


# ---------------------------------------------------------------------------
# Section 4: update_microphone_state
# ---------------------------------------------------------------------------


@pytest.mark.anyio
async def test_update_microphone_state_replaces_device_list() -> None:
    """update_microphone_state sets devices in microphone_state; snapshot reflects it."""
    manager = _make_manager()

    devices = [
        MicrophoneDevice(device_id=0, name="Built-in Mic", channels=1, default_sample_rate=44100),
        MicrophoneDevice(device_id=1, name="USB Headset", channels=2, default_sample_rate=48000),
    ]
    snap = await manager.update_microphone_state(devices, system_default_device_id=0)

    assert len(snap.microphone_state.devices) == 2
    assert snap.microphone_state.system_default_device_id == 0


@pytest.mark.anyio
async def test_update_microphone_state_preserves_selected_device_id() -> None:
    """update_microphone_state preserves selected_device_id when topology changes."""
    manager = _make_manager()

    # First update
    devices_v1 = [MicrophoneDevice(device_id=2, name="USB Mic", channels=1, default_sample_rate=48000)]
    await manager.update_microphone_state(devices_v1, system_default_device_id=2)
    await manager.set_mic_device(2)

    # Second update with same device still present
    devices_v2 = [
        MicrophoneDevice(device_id=2, name="USB Mic", channels=1, default_sample_rate=48000),
        MicrophoneDevice(device_id=3, name="New Mic", channels=1, default_sample_rate=44100),
    ]
    snap = await manager.update_microphone_state(devices_v2, system_default_device_id=2)

    assert snap.microphone_state.selected_device_id == 2


@pytest.mark.anyio
async def test_update_microphone_state_no_broadcast_on_same_topology() -> None:
    """update_microphone_state is a no-op (no listener call) when topology is unchanged."""
    manager = _make_manager()
    devices = [MicrophoneDevice(device_id=0, name="Built-in", channels=1, default_sample_rate=44100)]

    # First call should broadcast
    await manager.update_microphone_state(devices, system_default_device_id=0)

    broadcast_count = 0

    def _listener(snap):
        nonlocal broadcast_count
        broadcast_count += 1

    manager.add_snapshot_listener(_listener)

    # Second call with identical devices — should NOT broadcast
    await manager.update_microphone_state(devices, system_default_device_id=0)
    assert broadcast_count == 0


# ---------------------------------------------------------------------------
# Section 4: set_mic_device
# ---------------------------------------------------------------------------


@pytest.mark.anyio
async def test_set_mic_device_updates_snapshot() -> None:
    """set_mic_device updates microphone_state.selected_device_id; snapshot reflects it."""
    manager = _make_manager()
    snap = await manager.set_mic_device(3)
    assert snap.microphone_state.selected_device_id == 3


@pytest.mark.anyio
async def test_set_mic_device_persists_to_settings() -> None:
    """set_mic_device calls persistence.save_mic_device_id."""
    persistence = InMemoryPersistence()
    manager = _make_manager(persistence=persistence)

    # InMemoryPersistence is no-op for save_mic_device_id, but we verify no crash
    await manager.set_mic_device(5)
    # Can't easily assert InMemory write-through, but no exception = ok

    # Use SqlitePersistence for a real round-trip
    from pathlib import Path

    import pytest
    tmp_db = Path("/tmp/test_mic_device.db")
    tmp_db.unlink(missing_ok=True)
    from frontprompt.state.persistence.sqlite import SqlitePersistence

    sqlite_p = SqlitePersistence(tmp_db)
    manager2 = _make_manager(persistence=sqlite_p)
    await manager2.set_mic_device(7)
    loaded = sqlite_p.load_mic_device_id()
    assert loaded == 7
    tmp_db.unlink(missing_ok=True)


@pytest.mark.anyio
async def test_set_mic_device_none_clears_selection() -> None:
    """set_mic_device(None) clears selected_device_id."""
    manager = _make_manager()
    await manager.set_mic_device(3)
    snap = await manager.set_mic_device(None)
    assert snap.microphone_state.selected_device_id is None


# ---------------------------------------------------------------------------
# Section 4: set_settings
# ---------------------------------------------------------------------------


@pytest.mark.anyio
async def test_set_settings_updates_snapshot() -> None:
    """set_settings updates settings_state; snapshot reflects new values."""
    manager = _make_manager()
    new_settings = SettingsState(voice_over_enabled=True, selected_transcription_backend_id="mlx_whisper")
    snap = await manager.set_settings(new_settings)
    assert snap.settings_state.voice_over_enabled is True
    assert snap.settings_state.selected_transcription_backend_id == "mlx_whisper"


@pytest.mark.anyio
async def test_set_settings_persists_to_storage() -> None:
    """set_settings calls persistence.save_settings."""
    from pathlib import Path

    tmp_db = Path("/tmp/test_set_settings.db")
    tmp_db.unlink(missing_ok=True)
    from frontprompt.state.persistence.sqlite import SqlitePersistence

    sqlite_p = SqlitePersistence(tmp_db)
    manager = _make_manager(persistence=sqlite_p)
    settings = SettingsState(voice_over_enabled=True, selected_transcription_backend_id="mlx_whisper")
    await manager.set_settings(settings)

    loaded = sqlite_p.load_settings()
    assert loaded is not None
    assert loaded.voice_over_enabled is True
    assert loaded.selected_transcription_backend_id == "mlx_whisper"
    tmp_db.unlink(missing_ok=True)


# ---------------------------------------------------------------------------
# Section 4: update_transcription_backend_status
# ---------------------------------------------------------------------------


@pytest.mark.anyio
async def test_update_transcription_backend_status_updates_existing_backend() -> None:
    """update_transcription_backend_status updates the matching backend info."""
    ts = TranscriptionState(backends=[
        TranscriptionBackendInfo(backend_id="mlx_whisper", display_name="MLX Whisper", status="unavailable"),
    ])
    manager = _make_manager(transcription_state=ts)

    snap = await manager.update_transcription_backend_status("mlx_whisper", "ready", None)
    backend = next(b for b in snap.transcription_state.backends if b.backend_id == "mlx_whisper")
    assert backend.status == "ready"
    assert backend.download_progress is None


@pytest.mark.anyio
async def test_update_transcription_backend_status_with_progress() -> None:
    """update_transcription_backend_status sets download_progress."""
    ts = TranscriptionState(backends=[
        TranscriptionBackendInfo(backend_id="mlx_whisper", display_name="MLX Whisper", status="unavailable"),
    ])
    manager = _make_manager(transcription_state=ts)

    snap = await manager.update_transcription_backend_status("mlx_whisper", "downloading", 0.42)
    backend = next(b for b in snap.transcription_state.backends if b.backend_id == "mlx_whisper")
    assert backend.status == "downloading"
    assert abs(backend.download_progress - 0.42) < 1e-9


@pytest.mark.anyio
async def test_update_transcription_backend_status_unknown_backend_is_noop() -> None:
    """update_transcription_backend_status on unknown backend_id is a no-op."""
    manager = _make_manager()
    snap = await manager.update_transcription_backend_status("unknown_backend", "ready", None)
    assert snap is not None
