"""MlxWhisperBackend branch coverage tests.

Covers paths NOT exercised by test_mlx_whisper_backend.py:
- set_model() with unknown id → warning + return (no state change)
- set_model() with None → clears selection (reverts to default)
- set_model() with known id → updates selection
- ensure() exception fallback path (tqdm_class approach fails)
- transcribe() exception → RuntimeError re-raise
"""

from __future__ import annotations

import sys
from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest


def _fresh_backend():  # type: ignore[no-untyped-def]
    from frontprompt.voice.backends.mlx_whisper import MlxWhisperBackend

    return MlxWhisperBackend()


# ── set_model() paths ─────────────────────────────────────────────────────────


def test_set_model_unknown_id_logs_warning_and_keeps_selection() -> None:
    """set_model() with an unknown id logs warning and does NOT update _selected_model_id."""
    backend = _fresh_backend()
    backend.set_model("whisper-base-mlx")  # set a known model first
    backend.set_model("nonexistent-model-xyz-999")  # unknown — should warn + return
    # Selection should remain the previously set valid id
    assert backend._selected_model_id == "whisper-base-mlx"


def test_set_model_none_reverts_to_default() -> None:
    """set_model(None) reverts selection to default model."""
    backend = _fresh_backend()
    backend.set_model("whisper-large-v3-turbo")
    assert backend._selected_model_id == "whisper-large-v3-turbo"
    backend.set_model(None)
    assert backend._selected_model_id is None
    # _active_model should return the default
    from frontprompt.voice.backends.mlx_whisper import _DEFAULT_MODEL

    assert backend._active_model == _DEFAULT_MODEL


def test_set_model_known_id_updates_selection() -> None:
    """set_model() with a known model_id updates _selected_model_id."""
    backend = _fresh_backend()
    backend.set_model("whisper-large-v3-turbo")
    assert backend._selected_model_id == "whisper-large-v3-turbo"


# ── ensure() fallback path ────────────────────────────────────────────────────


@pytest.mark.anyio
async def test_ensure_fallback_when_tqdm_approach_raises(tmp_path: Path) -> None:
    """ensure() falls back to binary progress when the tqdm_class approach raises an exception.

    This covers the `except Exception` branch (lines 283-290) that degrades to
    binary 0.0/1.0 progress if anything in the incremental path fails.
    """
    missing_dir = tmp_path / "no-model"
    backend = _fresh_backend()
    progress_calls: list[float] = []

    async def cb(fraction: float) -> None:
        progress_calls.append(fraction)

    # Fake hf_hub whose snapshot_download raises on first call (with tqdm_class),
    # then succeeds on second call (fallback path without tqdm_class)
    call_count = [0]

    def fake_snapshot_download(repo_id: str, **kwargs: object) -> str:
        call_count[0] += 1
        if "tqdm_class" in kwargs:
            raise RuntimeError("tqdm_class is not supported by this version")
        return str(tmp_path)  # success on fallback call

    fake_hf_hub = MagicMock()
    fake_hf_hub.snapshot_download = MagicMock(side_effect=fake_snapshot_download)

    fake_spec = MagicMock()
    with (
        patch("sys.platform", "darwin"),
        patch("platform.machine", return_value="arm64"),
        patch("importlib.util.find_spec", return_value=fake_spec),
        patch.object(
            type(backend),
            "_model_cache_dir",
            new_callable=lambda: property(lambda self: missing_dir),
        ),
        patch.dict(sys.modules, {"huggingface_hub": fake_hf_hub}),
    ):
        await backend.ensure(cb)  # type: ignore[attr-defined]

    # Binary progress: 0.0 before, 1.0 after (fallback)
    assert 0.0 in progress_calls
    assert 1.0 in progress_calls
    assert call_count[0] == 2  # first attempt (fails) + fallback


# ── transcribe() exception path ───────────────────────────────────────────────


@pytest.mark.anyio
async def test_ensure_tqdm_collecting_context_manager_and_close(tmp_path: Path) -> None:
    """_ProgressTqdmCollecting is used as context manager + close() by some hf_hub versions.

    This covers lines 260 (__enter__ return self), 263 (__exit__ pass), 266 (close pass).
    """
    missing_dir = tmp_path / "no-model-ctx"
    backend = _fresh_backend()
    progress_calls: list[float] = []

    async def cb(fraction: float) -> None:
        progress_calls.append(fraction)

    def fake_snapshot_with_context_manager(repo_id: str, tqdm_class: type, **kwargs: object) -> str:
        """Instantiate tqdm_class as context manager + call close — exercises __enter__, __exit__, close."""
        with tqdm_class(total=1000) as tqdm_instance:
            tqdm_instance.update(500)
        # Also call close() directly (some hf_hub versions do this)
        obj = tqdm_class(total=500)
        obj.close()
        return str(tmp_path)

    fake_hf_hub = MagicMock()
    fake_hf_hub.snapshot_download = MagicMock(side_effect=fake_snapshot_with_context_manager)

    fake_spec = MagicMock()
    with (
        patch("sys.platform", "darwin"),
        patch("platform.machine", return_value="arm64"),
        patch("importlib.util.find_spec", return_value=fake_spec),
        patch.object(
            type(backend),
            "_model_cache_dir",
            new_callable=lambda: property(lambda self: missing_dir),
        ),
        patch.dict(sys.modules, {"huggingface_hub": fake_hf_hub}),
    ):
        await backend.ensure(cb)  # type: ignore[attr-defined]

    assert 0.0 in progress_calls
    assert 1.0 in progress_calls


@pytest.mark.anyio
async def test_transcribe_exception_raises_runtime_error(tmp_path: Path) -> None:
    """transcribe() wraps mlx_whisper failures in RuntimeError."""
    backend = _fresh_backend()
    wav_path = tmp_path / "audio.wav"
    wav_path.write_bytes(b"")  # create empty file

    # Build a fake mlx_whisper module whose transcribe raises
    fake_mlx = MagicMock()
    fake_mlx.transcribe.side_effect = RuntimeError("transcription failed internally")

    with patch.dict(sys.modules, {"mlx_whisper": fake_mlx}):
        with pytest.raises(RuntimeError, match="mlx_whisper transcription failed"):
            await backend.transcribe(wav_path)  # type: ignore[attr-defined]
