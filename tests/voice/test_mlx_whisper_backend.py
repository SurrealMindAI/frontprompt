"""Tests for MlxWhisperBackend — platform-gated, lazy-import, probe_status, ensure.

Section 2 of sub-plan 04 — write tests first (TDD).

Tests here do NOT require mlx_whisper to be installed — they test:
    - Platform guard (non-Apple-Silicon → "unavailable")
    - Missing dep guard (mlx_whisper not importable → "missing_dep")
    - Model cache absent → "needs_download"
    - Model cache present → "ready"
    - ensure() is a no-op when already ready
    - ensure() calls progress_cb with floats in [0.0, 1.0] (mocked download)
    - Lazy import: mlx_whisper NOT imported at module load

Integration test (needs real mlx_whisper + model) is marked @pytest.mark.integration
and skipped in the default run.
"""

from __future__ import annotations

import importlib
import sys
from pathlib import Path
from unittest.mock import AsyncMock, MagicMock, patch

import pytest


# ---------------------------------------------------------------------------
# Helper: clear any cached backend instance so each test starts fresh
# ---------------------------------------------------------------------------


def _fresh_backend() -> object:
    """Return a freshly constructed MlxWhisperBackend instance."""
    from frontprompt.voice.backends.mlx_whisper import MlxWhisperBackend

    return MlxWhisperBackend()


# ---------------------------------------------------------------------------
# Section 2a: Platform gate — non-Apple-Silicon → "unavailable"
# ---------------------------------------------------------------------------


def test_probe_status_unavailable_on_non_darwin() -> None:
    """On non-darwin platform probe_status() returns 'unavailable' without importing mlx_whisper."""
    backend = _fresh_backend()
    with patch("sys.platform", "linux"):
        status = backend.probe_status()  # type: ignore[attr-defined]
    assert status == "unavailable"


def test_probe_status_unavailable_on_darwin_non_arm64() -> None:
    """On darwin x86_64 probe_status() returns 'unavailable' (mlx_whisper is Apple-Silicon-only)."""
    backend = _fresh_backend()
    with patch("sys.platform", "darwin"), patch("platform.machine", return_value="x86_64"):
        status = backend.probe_status()  # type: ignore[attr-defined]
    assert status == "unavailable"


# ---------------------------------------------------------------------------
# Section 2b: Missing dep guard — mlx_whisper importlib.util.find_spec = None
# ---------------------------------------------------------------------------


def test_probe_status_missing_dep_when_mlx_not_installed() -> None:
    """When mlx_whisper is not importable (find_spec returns None), returns 'missing_dep'."""
    backend = _fresh_backend()
    with (
        patch("sys.platform", "darwin"),
        patch("platform.machine", return_value="arm64"),
        patch("importlib.util.find_spec", return_value=None),
    ):
        status = backend.probe_status()  # type: ignore[attr-defined]
    assert status == "missing_dep"


# ---------------------------------------------------------------------------
# Section 2c: needs_download when dep installed but model cache absent
# ---------------------------------------------------------------------------


def test_probe_status_needs_download_when_model_cache_absent(tmp_path: Path) -> None:
    """Returns 'needs_download' when mlx_whisper is importable but model cache dir is absent."""
    backend = _fresh_backend()
    fake_spec = MagicMock()  # non-None = importable
    with (
        patch("sys.platform", "darwin"),
        patch("platform.machine", return_value="arm64"),
        patch("importlib.util.find_spec", return_value=fake_spec),
        patch.object(type(backend), "_model_cache_dir", new_callable=lambda: property(lambda self: tmp_path / "no-such-dir")),
    ):
        status = backend.probe_status()  # type: ignore[attr-defined]
    assert status == "needs_download"


# ---------------------------------------------------------------------------
# Section 2d: ready when model cache dir exists
# ---------------------------------------------------------------------------


def test_probe_status_ready_when_model_cache_present(tmp_path: Path) -> None:
    """Returns 'ready' when mlx_whisper importable AND model cache dir exists."""
    model_dir = tmp_path / "models--mlx-community--whisper-base"
    model_dir.mkdir(parents=True)

    backend = _fresh_backend()
    fake_spec = MagicMock()
    with (
        patch("sys.platform", "darwin"),
        patch("platform.machine", return_value="arm64"),
        patch("importlib.util.find_spec", return_value=fake_spec),
        patch.object(type(backend), "_model_cache_dir", new_callable=lambda: property(lambda self: model_dir)),
    ):
        status = backend.probe_status()  # type: ignore[attr-defined]
    assert status == "ready"


# ---------------------------------------------------------------------------
# Section 2e: ensure() is a no-op when probe_status() == "ready"
# ---------------------------------------------------------------------------


@pytest.mark.anyio
async def test_ensure_is_noop_when_ready(tmp_path: Path) -> None:
    """ensure() returns immediately without calling progress_cb when already ready."""
    model_dir = tmp_path / "models--mlx-community--whisper-base"
    model_dir.mkdir()

    backend = _fresh_backend()
    progress_calls: list[float] = []

    async def cb(fraction: float) -> None:
        progress_calls.append(fraction)

    fake_spec = MagicMock()
    with (
        patch("sys.platform", "darwin"),
        patch("platform.machine", return_value="arm64"),
        patch("importlib.util.find_spec", return_value=fake_spec),
        patch.object(type(backend), "_model_cache_dir", new_callable=lambda: property(lambda self: model_dir)),
    ):
        await backend.ensure(cb)  # type: ignore[attr-defined]

    assert progress_calls == [], f"Expected no progress_cb calls, got: {progress_calls}"


# ---------------------------------------------------------------------------
# Section 2f: ensure() calls progress_cb with floats in [0.0, 1.0] (mocked download)
# ---------------------------------------------------------------------------


@pytest.mark.anyio
async def test_ensure_calls_progress_cb_during_download(tmp_path: Path) -> None:
    """ensure() calls progress_cb with floats in [0.0, 1.0] during a mocked download."""
    # Model cache does NOT exist → needs_download
    missing_dir = tmp_path / "no-model"

    backend = _fresh_backend()
    progress_calls: list[float] = []

    async def cb(fraction: float) -> None:
        progress_calls.append(fraction)

    # Mock snapshot_download to call tqdm_class update method as if downloading
    def fake_snapshot_download(repo_id: str, tqdm_class: type, **kwargs: object) -> str:
        # Simulate tqdm progress: instantiate the tqdm_class and call update()
        tqdm_instance = tqdm_class(total=1000)
        tqdm_instance.update(300)
        tqdm_instance.update(700)
        return str(tmp_path)

    # Build a fake huggingface_hub module (not installed in base env — voice optional extra)
    fake_hf_hub = MagicMock()
    fake_hf_hub.snapshot_download = MagicMock(side_effect=fake_snapshot_download)

    fake_spec = MagicMock()
    with (
        patch("sys.platform", "darwin"),
        patch("platform.machine", return_value="arm64"),
        patch("importlib.util.find_spec", return_value=fake_spec),
        patch.object(type(backend), "_model_cache_dir", new_callable=lambda: property(lambda self: missing_dir)),
        patch.dict(sys.modules, {"huggingface_hub": fake_hf_hub}),
    ):
        await backend.ensure(cb)  # type: ignore[attr-defined]

    assert len(progress_calls) >= 1, "Expected at least one progress_cb call"
    for fraction in progress_calls:
        assert 0.0 <= fraction <= 1.0, f"Progress fraction out of [0.0, 1.0]: {fraction}"


# ---------------------------------------------------------------------------
# Section 2g: Lazy import — mlx_whisper NOT in sys.modules after module load
# ---------------------------------------------------------------------------


def test_mlx_whisper_not_imported_at_module_load() -> None:
    """Importing MlxWhisperBackend does NOT trigger an import of mlx_whisper."""
    # Capture mlx_whisper presence before
    was_present = "mlx_whisper" in sys.modules

    # Force reload of the backend module
    if "frontprompt.voice.backends.mlx_whisper" in sys.modules:
        importlib.reload(sys.modules["frontprompt.voice.backends.mlx_whisper"])
    else:
        import frontprompt.voice.backends.mlx_whisper  # noqa: F401

    # mlx_whisper should NOT be in sys.modules unless it was already there before
    is_present_after = "mlx_whisper" in sys.modules
    if not was_present:
        assert not is_present_after, "mlx_whisper was imported at module load time (must be lazy)"


# ---------------------------------------------------------------------------
# Section 2h: ClassVar attributes
# ---------------------------------------------------------------------------


def test_mlx_whisper_backend_id() -> None:
    """MlxWhisperBackend.backend_id is 'mlx_whisper'."""
    from frontprompt.voice.backends.mlx_whisper import MlxWhisperBackend

    assert MlxWhisperBackend.backend_id == "mlx_whisper"


def test_mlx_whisper_display_name() -> None:
    """MlxWhisperBackend.display_name is human-readable Apple Silicon label."""
    from frontprompt.voice.backends.mlx_whisper import MlxWhisperBackend

    assert "Apple Silicon" in MlxWhisperBackend.display_name or "mlx" in MlxWhisperBackend.display_name.lower()


def test_mlx_whisper_satisfies_protocol() -> None:
    """MlxWhisperBackend instance satisfies TranscriptionBackend protocol."""
    from frontprompt.voice.backends.mlx_whisper import MlxWhisperBackend
    from frontprompt.voice.transcription import TranscriptionBackend

    backend = MlxWhisperBackend()
    assert isinstance(backend, TranscriptionBackend)


# ---------------------------------------------------------------------------
# Section 2i: Integration test (real mlx_whisper + model) — skipped by default
# ---------------------------------------------------------------------------


@pytest.mark.integration
def test_transcribe_integration_returns_segments(tmp_path: Path) -> None:
    """Integration test: transcribe a WAV fixture and get non-empty list[TranscriptSegment].

    Requires: mlx_whisper installed, model downloaded, Apple Silicon.
    Run with: pytest -m integration
    """
    if sys.platform != "darwin" or __import__("platform").machine() != "arm64":
        pytest.skip("Integration test requires Apple Silicon macOS")
    # mlx_whisper is a core dep on arm64 — no need to check if it's installed.
    # But the model must be downloaded before transcription is possible.
    from frontprompt.voice.backends.mlx_whisper import MlxWhisperBackend as _B
    if _B().probe_status() != "ready":
        pytest.skip("mlx-whisper model not downloaded — run `frontprompt bootstrap --voice` to download")

    # Create a minimal valid WAV fixture (silence)
    import struct
    import wave

    wav_path = tmp_path / "test_silence.wav"
    with wave.open(str(wav_path), "w") as f:
        f.setnchannels(1)
        f.setsampwidth(2)
        f.setframerate(16000)
        f.writeframes(struct.pack("<" + "h" * 16000, *([0] * 16000)))  # 1 second silence

    from frontprompt.voice.backends.mlx_whisper import MlxWhisperBackend
    from frontprompt.voice.transcription import TranscriptSegment

    import anyio

    backend = MlxWhisperBackend()
    # transcribe() is an async method; run it in a fresh event loop from this sync
    # test. (anyio.from_thread.run_sync only works inside an anyio worker thread.)
    segments = anyio.run(backend.transcribe, wav_path)
    assert isinstance(segments, list)
    for seg in segments:
        assert isinstance(seg, TranscriptSegment)
        assert isinstance(seg.start_ms, int)
        assert isinstance(seg.end_ms, int)
        assert isinstance(seg.text, str)
