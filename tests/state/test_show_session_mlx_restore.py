"""Round-trip restore of the persisted mlx-whisper model id on restart.

Regression guard for the wiring bug where ``ShowSession._build_state_manager``
constructed the initial :class:`TranscriptionState` *without* threading the
persisted ``mlx_whisper_model_id`` through ``build_initial_transcription_state``.
The model id was written by ``StateManager.set_mlx_whisper_model`` but never read
back, so a model selected in one session silently reverted to the default on the
next one.

The fix: ``_build_state_manager`` reads ``persistence.load_mlx_whisper_model_id()``
and passes it into ``build_initial_transcription_state``.
"""

from __future__ import annotations

from typing import TYPE_CHECKING

from frontprompt.state.persistence import make_persistence

if TYPE_CHECKING:
    from pathlib import Path

    import pytest


def test_build_state_manager_restores_persisted_mlx_model(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """A model id persisted in a prior session is restored into the initial
    transcription state when a new StateManager is built from the same DB.
    """
    from frontprompt import show_session as show_session_mod
    from frontprompt.ipc.session import SessionMetadata
    from frontprompt.show_session import ShowSession

    db_path = tmp_path / "restore.db"

    # Prior session: persist a non-default model selection to disk.
    seed = make_persistence(db_path)
    seed.save_mlx_whisper_model_id("whisper-large-v3-turbo")

    # _build_state_manager calls make_persistence() with no args; redirect it to
    # the same seeded DB so this is a genuine through-disk round-trip.
    monkeypatch.setattr(show_session_mod, "make_persistence", lambda: make_persistence(db_path))

    session = ShowSession(url="https://example.com")
    meta = SessionMetadata.for_current_process(session_id="restore-sess", url="https://example.com")
    manager = session._build_state_manager(meta)

    backends = manager.snapshot().transcription_state.backends
    mlx = next((b for b in backends if b.backend_id == "mlx_whisper"), None)
    assert mlx is not None, "mlx_whisper backend must be registered in the initial transcription state"
    assert mlx.selected_model_id == "whisper-large-v3-turbo", (
        f"persisted mlx-whisper model id must be restored on restart, got selected_model_id={mlx.selected_model_id!r}"
    )


def test_build_state_manager_no_persisted_model_leaves_selection_none(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """With nothing persisted, the mlx-whisper backend has no selected model
    (default behaviour, proves the restore is conditional on a saved value).
    """
    from frontprompt import show_session as show_session_mod
    from frontprompt.ipc.session import SessionMetadata
    from frontprompt.show_session import ShowSession

    db_path = tmp_path / "empty.db"
    monkeypatch.setattr(show_session_mod, "make_persistence", lambda: make_persistence(db_path))

    session = ShowSession(url="https://example.com")
    meta = SessionMetadata.for_current_process(session_id="empty-sess", url="https://example.com")
    manager = session._build_state_manager(meta)

    backends = manager.snapshot().transcription_state.backends
    mlx = next((b for b in backends if b.backend_id == "mlx_whisper"), None)
    assert mlx is not None, "mlx_whisper backend must be registered in the initial transcription state"
    assert mlx.selected_model_id is None
