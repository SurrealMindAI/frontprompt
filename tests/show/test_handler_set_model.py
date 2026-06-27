"""Unit tests for ShowSession._on_set_transcription_model handler — sub-plan 06.

TDD: tests written BEFORE the handler implementation.

Covers:
    - test_handler_dispatches_set_model_to_backend (COL-6): set_model called exactly once
    - test_handler_ignores_unknown_backend_id: unknown backend → no state broadcast
    - test_handler_model_id_none_calls_set_model_with_none: None reverts to default
    - test_handler_updates_snapshot_mlx_whisper_model_id: snapshot reflects new model
    - test_handler_count_is_29: ShowSession.handler_count() == 29
    - test_set_backend_preserves_model_id (COL-1): backend switch preserves mlx_whisper_model_id
"""

from __future__ import annotations

from typing import Any
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from frontprompt.state import StateManager
from frontprompt.state.state import SettingsState
from frontprompt.voice.transcription import REGISTERED_BACKENDS, TranscriptionBackend


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _build_session_with_manager(session_id: str = "test-session") -> tuple:
    """Return (ShowSession, StateManager) with in-memory persistence."""
    from frontprompt.show_session import ShowSession

    sm = StateManager(session_id=session_id)
    s = ShowSession(url="https://example.com", state_manager=sm)
    return s, sm


def _make_mock_backend(backend_id: str = "mlx_whisper") -> MagicMock:
    """Build a mock TranscriptionBackend with set_model() and probe_status()."""
    mock = MagicMock(spec=TranscriptionBackend)
    mock.backend_id = backend_id
    mock.set_model = MagicMock(return_value=None)
    mock.probe_status = MagicMock(return_value="ready")
    return mock


# ---------------------------------------------------------------------------
# test_handler_count_is_29
# ---------------------------------------------------------------------------


def test_handler_count_is_29() -> None:
    """ShowSession.handler_count() must return 29 after sub-plan 06 adds SetTranscriptionModelRequested."""
    from frontprompt.show_session import ShowSession

    s = ShowSession(url="https://example.com")
    assert s.handler_count() == 29, (
        f"Expected 29 handlers (28 existing + 1 SetTranscriptionModelRequested), "
        f"got {s.handler_count()}. Update handler_count() and its comment."
    )


# ---------------------------------------------------------------------------
# test_handler_dispatches_set_model_to_backend (COL-6)
# ---------------------------------------------------------------------------


@pytest.mark.anyio
async def test_handler_dispatches_set_model_to_backend() -> None:
    """COL-6: _on_set_transcription_model dispatches via set_mlx_whisper_model().

    set_model() on the backend is called exactly once (from inside set_mlx_whisper_model).
    The handler itself must NOT call set_model() — a call_count of 2 means COL-6 regressed.
    """
    from frontprompt.bridge.messages import SetTranscriptionModelRequested
    from frontprompt.show_session import ShowSession

    s, sm = _build_session_with_manager()
    mock_backend = _make_mock_backend("mlx_whisper")

    msg = SetTranscriptionModelRequested(
        backend_id="mlx_whisper",
        model_id="whisper-large-v3-turbo",
    )

    # Patch REGISTERED_BACKENDS to include only our mock backend
    with patch("frontprompt.voice.transcription.REGISTERED_BACKENDS", [mock_backend]):
        # Also patch set_mlx_whisper_model to call through but track calls
        original = sm.set_mlx_whisper_model
        set_model_calls: list[tuple] = []

        async def _spy(model_id: str | None, backend: Any) -> Any:
            set_model_calls.append((model_id, backend))
            return await original(model_id, backend)

        sm.set_mlx_whisper_model = _spy  # type: ignore[method-assign]
        await s._on_set_transcription_model(msg)

    # set_mlx_whisper_model was called exactly once
    assert len(set_model_calls) == 1, (
        f"Expected set_mlx_whisper_model called once, got {len(set_model_calls)}"
    )
    assert set_model_calls[0][0] == "whisper-large-v3-turbo"
    assert set_model_calls[0][1] is mock_backend

    # backend.set_model was called exactly once (inside set_mlx_whisper_model)
    mock_backend.set_model.assert_called_once_with("whisper-large-v3-turbo")


# ---------------------------------------------------------------------------
# test_handler_ignores_unknown_backend_id
# ---------------------------------------------------------------------------


@pytest.mark.anyio
async def test_handler_ignores_unknown_backend_id() -> None:
    """Unknown backend_id → handler returns without raising; state NOT broadcast."""
    from frontprompt.bridge.messages import SetTranscriptionModelRequested
    from frontprompt.show_session import ShowSession

    s, sm = _build_session_with_manager()

    # Track snapshot listener calls
    broadcast_count = 0

    def _listener(snap: Any) -> None:
        nonlocal broadcast_count
        broadcast_count += 1

    sm.add_snapshot_listener(_listener)

    msg = SetTranscriptionModelRequested(
        backend_id="nonexistent_backend",
        model_id="some-model",
    )

    with patch("frontprompt.voice.transcription.REGISTERED_BACKENDS", []):
        # Must not raise
        await s._on_set_transcription_model(msg)

    # No snapshot broadcast on unknown backend
    assert broadcast_count == 0, (
        f"Expected 0 broadcasts for unknown backend, got {broadcast_count}"
    )


# ---------------------------------------------------------------------------
# test_handler_model_id_none_calls_set_model_with_none
# ---------------------------------------------------------------------------


@pytest.mark.anyio
async def test_handler_model_id_none_calls_set_model_with_none() -> None:
    """model_id=None → backend.set_model(None) called exactly once (revert to default)."""
    from frontprompt.bridge.messages import SetTranscriptionModelRequested
    from frontprompt.show_session import ShowSession

    s, sm = _build_session_with_manager()
    mock_backend = _make_mock_backend("mlx_whisper")

    msg = SetTranscriptionModelRequested(
        backend_id="mlx_whisper",
        model_id=None,
    )

    with patch("frontprompt.voice.transcription.REGISTERED_BACKENDS", [mock_backend]):
        await s._on_set_transcription_model(msg)

    # set_model called with None exactly once
    mock_backend.set_model.assert_called_once_with(None)


# ---------------------------------------------------------------------------
# test_handler_updates_snapshot_mlx_whisper_model_id
# ---------------------------------------------------------------------------


@pytest.mark.anyio
async def test_handler_updates_snapshot_mlx_whisper_model_id() -> None:
    """After handler, snapshot.settings_state.mlx_whisper_model_id equals msg.model_id."""
    from frontprompt.bridge.messages import SetTranscriptionModelRequested
    from frontprompt.show_session import ShowSession

    s, sm = _build_session_with_manager()
    mock_backend = _make_mock_backend("mlx_whisper")

    chosen_model = "whisper-large-v3-turbo"
    msg = SetTranscriptionModelRequested(
        backend_id="mlx_whisper",
        model_id=chosen_model,
    )

    with patch("frontprompt.voice.transcription.REGISTERED_BACKENDS", [mock_backend]):
        await s._on_set_transcription_model(msg)

    snap = sm.snapshot()
    assert snap.settings_state.mlx_whisper_model_id == chosen_model, (
        f"Expected mlx_whisper_model_id={chosen_model!r}, "
        f"got {snap.settings_state.mlx_whisper_model_id!r}"
    )


# ---------------------------------------------------------------------------
# test_set_backend_preserves_model_id (COL-1)
# ---------------------------------------------------------------------------


@pytest.mark.anyio
async def test_set_backend_preserves_model_id() -> None:
    """COL-1: switching transcription backend must NOT wipe mlx_whisper_model_id.

    Seeds SettingsState.mlx_whisper_model_id with a non-None value, then dispatches
    SetTranscriptionBackendRequested. Post-handler snapshot must still carry the
    seeded model_id — the backend switch must not revert the model selection to None.
    """
    from frontprompt.bridge.messages import SetTranscriptionBackendRequested
    from frontprompt.show_session import ShowSession

    s, sm = _build_session_with_manager()

    # Seed the model id before the backend switch
    seeded_model_id = "whisper-large-v3-turbo"
    async with sm._lock:
        sm._settings_state.mlx_whisper_model_id = seeded_model_id

    # Verify the seed is in place
    assert sm.snapshot().settings_state.mlx_whisper_model_id == seeded_model_id

    # Now switch the backend
    backend_switch_msg = SetTranscriptionBackendRequested(backend_id="mlx_whisper")
    await s._on_set_transcription_backend(backend_switch_msg)

    # The model_id must survive the backend switch
    snap_after = sm.snapshot()
    assert snap_after.settings_state.mlx_whisper_model_id == seeded_model_id, (
        f"COL-1 violated: mlx_whisper_model_id was wiped by backend switch. "
        f"Expected {seeded_model_id!r}, got {snap_after.settings_state.mlx_whisper_model_id!r}. "
        f"Fix _on_set_transcription_backend to forward mlx_whisper_model_id=current.mlx_whisper_model_id."
    )
