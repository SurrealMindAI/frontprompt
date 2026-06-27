"""Tests for MlxWhisperBackend model catalog + set_model() support.

TDD for sub-plan 01 — model catalog + selectable model.

Covers:
- MODEL_CATALOG has exactly one default entry
- All catalog entries have non-empty fields
- set_model updates selected model id (COL-7: transcribe uses correct hf_repo_id)
- set_model(None) reverts to default model
- probe_status returns "unavailable" on non-arm64/darwin
- Cache subdir is derived from selected model's hf_repo_id (COL-7)
"""

from __future__ import annotations

import sys
from pathlib import Path
from unittest.mock import patch

import pytest


# ---------------------------------------------------------------------------
# Helper
# ---------------------------------------------------------------------------


def _fresh_backend():
    """Return a freshly constructed MlxWhisperBackend instance."""
    from frontprompt.voice.backends.mlx_whisper import MlxWhisperBackend

    return MlxWhisperBackend()


# ---------------------------------------------------------------------------
# MODEL_CATALOG structure
# ---------------------------------------------------------------------------


def test_model_catalog_has_exactly_one_default() -> None:
    """MODEL_CATALOG list has exactly one entry with default=True."""
    from frontprompt.voice.backends.mlx_whisper import MODEL_CATALOG

    defaults = [m for m in MODEL_CATALOG if m.default]
    assert len(defaults) == 1, f"Expected exactly 1 default, got {len(defaults)}: {defaults}"


def test_model_catalog_all_fields_populated() -> None:
    """Every MODEL_CATALOG entry has non-empty model_id, display_name, hf_repo_id."""
    from frontprompt.voice.backends.mlx_whisper import MODEL_CATALOG

    assert len(MODEL_CATALOG) >= 2, "Catalog must have at least 2 entries"
    for entry in MODEL_CATALOG:
        assert entry.model_id, f"Empty model_id in entry: {entry}"
        assert entry.display_name, f"Empty display_name in entry: {entry}"
        assert entry.hf_repo_id, f"Empty hf_repo_id in entry: {entry}"


# ---------------------------------------------------------------------------
# set_model() — COL-7: transcribe uses correct hf_repo_id
# ---------------------------------------------------------------------------


def test_set_model_updates_selected() -> None:
    """backend.set_model(<id>) stores the id; subsequent calls use that model's hf_repo_id."""
    from frontprompt.voice.backends.mlx_whisper import MODEL_CATALOG, MlxWhisperBackend

    # Find a non-default model
    non_default = next(m for m in MODEL_CATALOG if not m.default)
    backend = MlxWhisperBackend()

    backend.set_model(non_default.model_id)

    # The backend's internal selection should reflect the new model
    # We verify via _current_model property / selected_model field
    assert backend._selected_model_id == non_default.model_id

    # The active hf_repo_id property must return the selected model's repo
    assert backend._active_hf_repo_id == non_default.hf_repo_id


def test_set_model_none_reverts_to_default() -> None:
    """backend.set_model(None) causes the default model's repo ID to be used."""
    from frontprompt.voice.backends.mlx_whisper import MODEL_CATALOG, MlxWhisperBackend

    default_model = next(m for m in MODEL_CATALOG if m.default)
    non_default = next(m for m in MODEL_CATALOG if not m.default)
    backend = MlxWhisperBackend()

    # Switch to non-default
    backend.set_model(non_default.model_id)
    assert backend._active_hf_repo_id == non_default.hf_repo_id

    # Revert to default
    backend.set_model(None)
    assert backend._active_hf_repo_id == default_model.hf_repo_id


# ---------------------------------------------------------------------------
# probe_status — platform gate
# ---------------------------------------------------------------------------


def test_probe_status_skips_unknown_platform() -> None:
    """On non-arm64/darwin platform, probe_status() returns 'unavailable'."""
    backend = _fresh_backend()
    with patch("sys.platform", "linux"):
        status = backend.probe_status()
    assert status == "unavailable"


# ---------------------------------------------------------------------------
# Cache subdir — derived from hf_repo_id (COL-7)
# ---------------------------------------------------------------------------


def test_cache_subdir_derived_from_hf_repo_id() -> None:
    """The cache directory logic uses hf_repo_id of the currently selected model."""
    from frontprompt.voice.backends.mlx_whisper import MODEL_CATALOG, MlxWhisperBackend

    non_default = next(m for m in MODEL_CATALOG if not m.default)
    backend = MlxWhisperBackend()
    backend.set_model(non_default.model_id)

    # The cache dir path should contain the non-default model's repo subdir
    # HF convention: "models--" prefix + "/" → "--" substitution
    expected_subdir = "models--" + non_default.hf_repo_id.replace("/", "--")
    cache_dir = backend._model_cache_dir

    assert expected_subdir in str(cache_dir), (
        f"Expected cache dir to contain '{expected_subdir}', got: {cache_dir}"
    )


def test_cache_subdir_default_model() -> None:
    """Cache dir for default model is derived from default model's hf_repo_id."""
    from frontprompt.voice.backends.mlx_whisper import MODEL_CATALOG, MlxWhisperBackend

    default_model = next(m for m in MODEL_CATALOG if m.default)
    backend = MlxWhisperBackend()

    expected_subdir = "models--" + default_model.hf_repo_id.replace("/", "--")
    cache_dir = backend._model_cache_dir

    assert expected_subdir in str(cache_dir), (
        f"Expected cache dir to contain '{expected_subdir}', got: {cache_dir}"
    )


__all__ = []
