"""Tests for TranscriptionModelSpec, schema 0.11.0 bump, and persistence round-trips.

TDD for sub-plan 01 — backend model catalog + state 0.11.0.

Covers:
- TranscriptionModelSpec Pydantic model + codegen roots
- StateSnapshot schema_version == "0.11.0"
- SettingsState.mlx_whisper_model_id default == None
- TranscriptionBackendInfo.available_models + selected_model_id defaults
- InMemoryPersistence mlx_whisper_model_id round-trip
- SqlitePersistence mlx_whisper_model_id round-trip
"""

from __future__ import annotations

import pytest


# ---------------------------------------------------------------------------
# TranscriptionModelSpec
# ---------------------------------------------------------------------------


def test_transcription_model_spec_fields() -> None:
    """TranscriptionModelSpec round-trips through Pydantic with all required fields."""
    from frontprompt.state.state import TranscriptionModelSpec

    spec = TranscriptionModelSpec(
        model_id="whisper-base-mlx",
        display_name="Whisper Base (MLX)",
        hf_repo_id="mlx-community/whisper-base-mlx",
        default=True,
    )
    assert spec.model_id == "whisper-base-mlx"
    assert spec.display_name == "Whisper Base (MLX)"
    assert spec.hf_repo_id == "mlx-community/whisper-base-mlx"
    assert spec.default is True

    # Verify JSON round-trip
    dumped = spec.model_dump_json()
    recovered = TranscriptionModelSpec.model_validate_json(dumped)
    assert recovered == spec


def test_transcription_model_spec_in_codegen_roots() -> None:
    """TranscriptionModelSpec is in state.__codegen_roots__ for TS schema emission."""
    from frontprompt.state.state import __codegen_roots__

    assert "TranscriptionModelSpec" in __codegen_roots__


# ---------------------------------------------------------------------------
# StateSnapshot schema_version
# ---------------------------------------------------------------------------


def test_settings_state_schema_version_011() -> None:
    """StateSnapshot with default values has schema_version == '0.11.0'."""
    from frontprompt.state.state import PanelStateView, PanelView, StateSnapshot

    snap = StateSnapshot(
        panel_state=PanelStateView(
            top=PanelView(open=True, size=56),
            bottom=PanelView(open=False, size=220),
            left=PanelView(open=True, size=300),
            right=PanelView(open=True, size=340),
        ),
    )
    assert snap.schema_version == "0.11.0"


# ---------------------------------------------------------------------------
# SettingsState.mlx_whisper_model_id default
# ---------------------------------------------------------------------------


def test_settings_state_mlx_whisper_model_id_default_none() -> None:
    """SettingsState().mlx_whisper_model_id is None by default."""
    from frontprompt.state.state import SettingsState

    s = SettingsState()
    assert s.mlx_whisper_model_id is None


# ---------------------------------------------------------------------------
# TranscriptionBackendInfo defaults
# ---------------------------------------------------------------------------


def test_transcription_backend_info_available_models_default_empty() -> None:
    """TranscriptionBackendInfo() has available_models=[] and selected_model_id=None."""
    from frontprompt.state.state import TranscriptionBackendInfo

    info = TranscriptionBackendInfo(
        backend_id="mlx_whisper",
        display_name="mlx-whisper (Apple Silicon)",
        status="unavailable",
    )
    assert info.available_models == []
    assert info.selected_model_id is None


# ---------------------------------------------------------------------------
# InMemoryPersistence mlx_whisper_model_id round-trip
# ---------------------------------------------------------------------------


def test_in_memory_persistence_model_id_round_trip() -> None:
    """InMemoryPersistence: save then load mlx_whisper_model_id returns same value."""
    from frontprompt.state.persistence.in_memory import InMemoryPersistence

    p = InMemoryPersistence()

    # Initially None
    assert p.load_mlx_whisper_model_id() is None

    # Save a model id
    p.save_mlx_whisper_model_id("whisper-large-v3-turbo")
    assert p.load_mlx_whisper_model_id() == "whisper-large-v3-turbo"

    # Overwrite with None reverts
    p.save_mlx_whisper_model_id(None)
    assert p.load_mlx_whisper_model_id() is None


# ---------------------------------------------------------------------------
# SqlitePersistence mlx_whisper_model_id round-trip
# ---------------------------------------------------------------------------


def test_sqlite_persistence_model_id_round_trip(tmp_path) -> None:
    """SqlitePersistence: save then load mlx_whisper_model_id returns same value."""
    from frontprompt.state.persistence.sqlite import SqlitePersistence

    db = SqlitePersistence(tmp_path / "test.db")

    # Initially None
    assert db.load_mlx_whisper_model_id() is None

    # Save a model id
    db.save_mlx_whisper_model_id("whisper-large-v3-turbo")
    assert db.load_mlx_whisper_model_id() == "whisper-large-v3-turbo"

    # Overwrite with None reverts
    db.save_mlx_whisper_model_id(None)
    assert db.load_mlx_whisper_model_id() is None


__all__ = []
