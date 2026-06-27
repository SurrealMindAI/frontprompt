"""Tests for StateManager.set_mlx_whisper_model — sub-plan 01.

Covers COL-2, COL-3, COL-6, COL-8:
- set_mlx_whisper_model updates SettingsState.mlx_whisper_model_id
- set_mlx_whisper_model calls backend.set_model (COL-6: single caller)
- set_mlx_whisper_model persists to InMemoryPersistence
- set_mlx_whisper_model broadcasts snapshot exactly once
- COL-3: updates selected_model_id on matching TranscriptionBackendInfo
- COL-2: re-probes backend.probe_status and updates TranscriptionBackendInfo.status
"""

from __future__ import annotations

import pytest

from frontprompt.state.persistence.in_memory import InMemoryPersistence
from frontprompt.state.state import TranscriptionBackendInfo, TranscriptionState


# ---------------------------------------------------------------------------
# Fake backend (implements TranscriptionBackend Protocol)
# ---------------------------------------------------------------------------


class _FakeBackend:
    """Minimal fake backend for testing set_mlx_whisper_model."""

    backend_id = "mlx_whisper"
    display_name = "Fake MLX Whisper"

    def __init__(self, probe_return: str = "ready") -> None:
        self._probe_return = probe_return
        self.set_model_calls: list[str | None] = []

    def probe_status(self) -> str:
        return self._probe_return

    def set_model(self, model_id: str | None) -> None:
        self.set_model_calls.append(model_id)

    async def ensure(self, progress_cb) -> None:
        pass

    async def transcribe(self, audio_path):
        return []


# ---------------------------------------------------------------------------
# Helper
# ---------------------------------------------------------------------------


def _make_manager(
    *,
    transcription_state: TranscriptionState | None = None,
    persistence: InMemoryPersistence | None = None,
):
    from frontprompt.state.manager import StateManager

    return StateManager(
        session_id="test-session",
        persistence=persistence or InMemoryPersistence(),
        transcription_state=transcription_state,
    )


def _make_transcription_state_with_backend(backend_id: str = "mlx_whisper") -> TranscriptionState:
    return TranscriptionState(
        backends=[
            TranscriptionBackendInfo(
                backend_id=backend_id,
                display_name="Test Backend",
                status="ready",
            )
        ]
    )


# ---------------------------------------------------------------------------
# Tests
# ---------------------------------------------------------------------------


@pytest.mark.anyio
async def test_set_mlx_whisper_model_updates_snapshot() -> None:
    """After set_mlx_whisper_model, snapshot.settings_state.mlx_whisper_model_id == given id."""
    ts = _make_transcription_state_with_backend()
    manager = _make_manager(transcription_state=ts)
    backend = _FakeBackend()

    await manager.set_mlx_whisper_model("whisper-large-v3-turbo", backend)
    snap = manager.snapshot()

    assert snap.settings_state.mlx_whisper_model_id == "whisper-large-v3-turbo"
    assert backend.set_model_calls == ["whisper-large-v3-turbo"]


@pytest.mark.anyio
async def test_set_mlx_whisper_model_persists() -> None:
    """After set_mlx_whisper_model, persistence.load_mlx_whisper_model_id() returns the id."""
    ts = _make_transcription_state_with_backend()
    persistence = InMemoryPersistence()
    manager = _make_manager(transcription_state=ts, persistence=persistence)
    backend = _FakeBackend()

    await manager.set_mlx_whisper_model("whisper-large-v3-turbo", backend)

    assert persistence.load_mlx_whisper_model_id() == "whisper-large-v3-turbo"


@pytest.mark.anyio
async def test_set_mlx_whisper_model_broadcasts() -> None:
    """State broadcast fires exactly once after set_mlx_whisper_model."""
    ts = _make_transcription_state_with_backend()
    manager = _make_manager(transcription_state=ts)
    backend = _FakeBackend()

    broadcasts = []

    def _listener(snap) -> None:
        broadcasts.append(snap)

    manager.add_snapshot_listener(_listener)
    await manager.set_mlx_whisper_model("whisper-large-v3-turbo", backend)

    assert len(broadcasts) == 1


@pytest.mark.anyio
async def test_set_mlx_whisper_model_updates_backend_selected_model_id() -> None:
    """COL-3: matching TranscriptionBackendInfo.selected_model_id == given id after call."""
    ts = _make_transcription_state_with_backend("mlx_whisper")
    manager = _make_manager(transcription_state=ts)
    backend = _FakeBackend()

    await manager.set_mlx_whisper_model("whisper-large-v3-turbo", backend)
    snap = manager.snapshot()

    mlx_info = next(b for b in snap.transcription_state.backends if b.backend_id == "mlx_whisper")
    assert mlx_info.selected_model_id == "whisper-large-v3-turbo"


@pytest.mark.anyio
async def test_set_mlx_whisper_model_reprobes_status() -> None:
    """COL-2: after set_model, status is re-probed; stale 'ready' does not leak."""
    class _NeedsDownloadBackend(_FakeBackend):
        def probe_status(self) -> str:
            # Before set_model: ready; after set_model: needs_download
            if self.set_model_calls:
                return "needs_download"
            return "ready"

    ts = _make_transcription_state_with_backend("mlx_whisper")
    manager = _make_manager(transcription_state=ts)
    backend = _NeedsDownloadBackend()

    await manager.set_mlx_whisper_model("whisper-large-v3-turbo", backend)
    snap = manager.snapshot()

    mlx_info = next(b for b in snap.transcription_state.backends if b.backend_id == "mlx_whisper")
    assert mlx_info.status == "needs_download", (
        f"Expected status='needs_download' after model switch, got '{mlx_info.status}'. "
        "COL-2: re-probe must happen after set_model()."
    )


__all__ = []
