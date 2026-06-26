"""Tests für voice-over persistence extensions — section 3 of voice-over sub-plan 01.

Covers:
- SqlitePersistence.save_settings / load_settings round-trip (key-value settings table)
- SqlitePersistence.save_mic_device_id / load_mic_device_id round-trip
- SqlitePersistence.upsert_recording persists voice-over fields
- SqlitePersistence.load_recordings reloads voice-over fields
- SqlitePersistence.append_timeline_entry handles TranscriptSegmentEntry (new kind)
- InMemoryPersistence stubs for new methods (no-op, return defaults)
"""

from __future__ import annotations

from pathlib import Path

import pytest

from frontprompt.state.state import (
    Recording,
    SettingsState,
    TranscriptSegmentEntry,
)


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _make_sqlite(tmp_path: Path):  # type: ignore[no-untyped-def]
    from frontprompt.state.persistence.sqlite import SqlitePersistence

    return SqlitePersistence(tmp_path / "test_vo.db")


def _make_recording(recording_id: str = "rec-vo-001", **kwargs: object) -> Recording:  # type: ignore[no-untyped-def]
    return Recording(
        recording_id=recording_id,
        name="Voice Test",
        status="active",
        started_at_ms=1_700_000_000_000,
        **kwargs,  # type: ignore[arg-type]
    )


# ---------------------------------------------------------------------------
# Section 3: save_settings / load_settings round-trip
# ---------------------------------------------------------------------------


def test_save_load_settings_roundtrip(tmp_path: Path) -> None:
    """save_settings writes to settings table; load_settings round-trips the values."""
    db = _make_sqlite(tmp_path)
    settings = SettingsState(
        voice_over_enabled=True,
        selected_transcription_backend_id="mlx_whisper",
    )
    db.save_settings(settings)

    loaded = db.load_settings()
    assert loaded is not None
    assert loaded.voice_over_enabled is True
    assert loaded.selected_transcription_backend_id == "mlx_whisper"


def test_load_settings_returns_none_when_no_settings(tmp_path: Path) -> None:
    """load_settings returns None when no settings have been saved yet."""
    db = _make_sqlite(tmp_path)
    assert db.load_settings() is None


def test_save_settings_default_values_roundtrip(tmp_path: Path) -> None:
    """Default SettingsState (False, None) round-trips through save/load."""
    db = _make_sqlite(tmp_path)
    settings = SettingsState()  # defaults
    db.save_settings(settings)

    loaded = db.load_settings()
    assert loaded is not None
    assert loaded.voice_over_enabled is False
    assert loaded.selected_transcription_backend_id is None


def test_save_settings_overwrites_previous(tmp_path: Path) -> None:
    """Calling save_settings twice keeps only the latest values (last-write-wins)."""
    db = _make_sqlite(tmp_path)
    db.save_settings(SettingsState(voice_over_enabled=True, selected_transcription_backend_id="mlx_whisper"))
    db.save_settings(SettingsState(voice_over_enabled=False, selected_transcription_backend_id=None))

    loaded = db.load_settings()
    assert loaded is not None
    assert loaded.voice_over_enabled is False
    assert loaded.selected_transcription_backend_id is None


# ---------------------------------------------------------------------------
# Section 3: save_mic_device_id / load_mic_device_id round-trip
# ---------------------------------------------------------------------------


def test_save_load_mic_device_id_roundtrip(tmp_path: Path) -> None:
    """save_mic_device_id writes to settings table; load_mic_device_id reads it back."""
    db = _make_sqlite(tmp_path)
    db.save_mic_device_id(2)

    loaded = db.load_mic_device_id()
    assert loaded == 2


def test_load_mic_device_id_returns_none_when_not_set(tmp_path: Path) -> None:
    """load_mic_device_id returns None when no device has been saved."""
    db = _make_sqlite(tmp_path)
    assert db.load_mic_device_id() is None


def test_save_mic_device_id_none_clears_preference(tmp_path: Path) -> None:
    """save_mic_device_id(None) stores system-default preference; load returns None."""
    db = _make_sqlite(tmp_path)
    db.save_mic_device_id(3)
    db.save_mic_device_id(None)

    loaded = db.load_mic_device_id()
    assert loaded is None


# ---------------------------------------------------------------------------
# Section 3: upsert_recording persists voice-over fields
# ---------------------------------------------------------------------------


def test_upsert_recording_persists_voice_over_fields(tmp_path: Path) -> None:
    """upsert_recording includes voice-over fields; load_recordings reloads them."""
    db = _make_sqlite(tmp_path)
    rec = _make_recording(
        has_voice_over=True,
        audio_path="/tmp/rec.wav",
        transcription_status="done",
        transcription_error=None,
    )
    db.upsert_recording(rec)

    recordings = db.load_recordings()
    assert len(recordings) == 1
    loaded = recordings[0]
    assert loaded.has_voice_over is True
    assert loaded.audio_path == "/tmp/rec.wav"
    assert loaded.transcription_status == "done"
    assert loaded.transcription_error is None


def test_upsert_recording_voice_over_defaults_are_preserved(tmp_path: Path) -> None:
    """load_recordings respects default voice-over field values (has_voice_over=False etc.)."""
    db = _make_sqlite(tmp_path)
    rec = _make_recording()  # defaults: has_voice_over=False, audio_path=None, transcription_status='none'
    db.upsert_recording(rec)

    recordings = db.load_recordings()
    assert len(recordings) == 1
    loaded = recordings[0]
    assert loaded.has_voice_over is False
    assert loaded.audio_path is None
    assert loaded.transcription_status == "none"


def test_upsert_recording_with_transcription_error(tmp_path: Path) -> None:
    """upsert_recording persists transcription_error field."""
    db = _make_sqlite(tmp_path)
    rec = _make_recording(
        has_voice_over=True,
        transcription_status="failed",
        transcription_error="Model not available on this platform",
    )
    db.upsert_recording(rec)

    recordings = db.load_recordings()
    assert len(recordings) == 1
    loaded = recordings[0]
    assert loaded.transcription_status == "failed"
    assert loaded.transcription_error == "Model not available on this platform"


# ---------------------------------------------------------------------------
# Section 3: append_timeline_entry handles TranscriptSegmentEntry
# ---------------------------------------------------------------------------


def test_append_timeline_entry_handles_transcript_segment(tmp_path: Path) -> None:
    """append_timeline_entry persists TranscriptSegmentEntry; load_recordings reloads it."""
    db = _make_sqlite(tmp_path)
    rec = _make_recording(has_voice_over=True, transcription_status="done")
    db.upsert_recording(rec)

    segment = TranscriptSegmentEntry(
        kind="transcript_segment",
        seq=0,
        timestamp_ms=1_700_000_005_000,
        start_ms=5000,
        end_ms=8000,
        text="Hello world",
        backend_id="mlx_whisper",
    )
    db.append_timeline_entry(rec.recording_id, segment)

    recordings = db.load_recordings()
    assert len(recordings) == 1
    entries = recordings[0].entries
    assert len(entries) == 1
    entry = entries[0]
    assert entry.kind == "transcript_segment"
    assert entry.text == "Hello world"  # type: ignore[union-attr]
    assert entry.backend_id == "mlx_whisper"  # type: ignore[union-attr]
    assert entry.start_ms == 5000  # type: ignore[union-attr]
    assert entry.end_ms == 8000  # type: ignore[union-attr]


# ---------------------------------------------------------------------------
# Section 3: InMemoryPersistence stubs for new methods
# ---------------------------------------------------------------------------


def test_in_memory_persistence_save_settings_no_op() -> None:
    """InMemoryPersistence.save_settings is a no-op (does not raise)."""
    from frontprompt.state.persistence.in_memory import InMemoryPersistence

    persistence = InMemoryPersistence()
    # Should not raise
    persistence.save_settings(SettingsState(voice_over_enabled=True))


def test_in_memory_persistence_load_settings_returns_none() -> None:
    """InMemoryPersistence.load_settings returns None (no persistent storage)."""
    from frontprompt.state.persistence.in_memory import InMemoryPersistence

    persistence = InMemoryPersistence()
    assert persistence.load_settings() is None


def test_in_memory_persistence_save_mic_device_id_no_op() -> None:
    """InMemoryPersistence.save_mic_device_id is a no-op (does not raise)."""
    from frontprompt.state.persistence.in_memory import InMemoryPersistence

    persistence = InMemoryPersistence()
    persistence.save_mic_device_id(3)  # no exception


def test_in_memory_persistence_load_mic_device_id_returns_none() -> None:
    """InMemoryPersistence.load_mic_device_id returns None."""
    from frontprompt.state.persistence.in_memory import InMemoryPersistence

    persistence = InMemoryPersistence()
    assert persistence.load_mic_device_id() is None
