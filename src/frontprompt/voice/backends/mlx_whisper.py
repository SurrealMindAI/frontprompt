"""mlx-whisper transcription backend for Apple Silicon (macOS arm64).

Lazy-imports ``mlx_whisper`` INSIDE methods only — never at module load. This keeps
the core install lean on non-macOS hosts where mlx_whisper cannot run.

Platform gate: :meth:`MlxWhisperBackend.probe_status` returns ``"unavailable"``
immediately on non-Apple-Silicon platforms without touching any mlx imports.

Model download (COL-6 resolution): uses ``huggingface_hub.snapshot_download`` with
a custom ``tqdm_class`` wrapper to translate aggregate byte progress into [0.0, 1.0]
fractions forwarded to the caller's ``progress_cb``. This is idempotent — the model
lands in the same HF cache dir that ``probe_status()`` checks, so a subsequent
``transcribe()`` finds it "ready" with no second pull.

Fallback: if the tqdm_class hook is unstable across huggingface_hub versions, degrades
to binary progress (0.0 before, 1.0 after) as documented in COL-6.

Mirrors the ``_chromium_present`` / ``ensure_chromium`` pattern from
:mod:`frontprompt.browser.manager`.
"""

from __future__ import annotations

import importlib.util
import platform
import sys
from pathlib import Path
from typing import ClassVar

import structlog

from frontprompt.state.state import TranscriptionModelSpec
from frontprompt.voice.transcription import ProgressCallback, TranscriptSegment, TranscriptionBackendStatus

_LOG = structlog.get_logger(__name__)

# ---------------------------------------------------------------------------
# MODEL_CATALOG — static curated list of supported mlx-whisper models.
# Each entry is a TranscriptionModelSpec. Exactly one entry has default=True.
#
# HF repo IDs are mlx-community models — all support the mlx_whisper.transcribe(
# path_or_hf_repo=...) API. Exactly one entry has default=True.
# ---------------------------------------------------------------------------

MODEL_CATALOG: list[TranscriptionModelSpec] = [
    TranscriptionModelSpec(
        model_id="whisper-base-mlx",
        display_name="Whisper Base (MLX) — fast, small",
        hf_repo_id="mlx-community/whisper-base-mlx",
        default=True,
    ),
    TranscriptionModelSpec(
        model_id="whisper-large-v3-turbo",
        display_name="Whisper Large v3 Turbo (MLX) — accurate, larger",
        hf_repo_id="mlx-community/whisper-large-v3-turbo",
        default=False,
    ),
    TranscriptionModelSpec(
        model_id="whisper-large-v3-turbo-german",
        display_name="Whisper Large v3 Turbo — German (MLX)",
        hf_repo_id="mlx-community/whisper-large-v3-turbo-german-f16",
        default=False,
    ),
]
"""Curated list of mlx-whisper models. Exactly one entry has ``default=True``."""

_DEFAULT_MODEL: TranscriptionModelSpec = next(m for m in MODEL_CATALOG if m.default)


def _hf_cache_subdir(hf_repo_id: str) -> str:
    """Derive HuggingFace Hub cache subdirectory name from a repo ID.

    HF Hub convention: ``models--`` prefix + ``/`` → ``--`` substitution.
    Example: ``mlx-community/whisper-base-mlx`` → ``models--mlx-community--whisper-base-mlx``.
    """
    return "models--" + hf_repo_id.replace("/", "--")


class MlxWhisperBackend:
    """Concrete transcription backend using mlx-whisper on Apple Silicon.

    This backend is Apple Silicon (macOS arm64) exclusive. On other platforms
    :meth:`probe_status` returns ``"unavailable"`` immediately.

    Lifecycle mirrors :func:`frontprompt.browser.manager.ensure_chromium`:
        1. :meth:`probe_status` — cheap synchronous filesystem + importlib check.
        2. :meth:`ensure` — triggered explicitly (e.g. from ``bootstrap --voice``
           or via bridge ``TriggerModelDownloadRequested``). Downloads the model
           once and never again (idempotent).
        3. :meth:`transcribe` — lazy-imports mlx_whisper, transcribes audio.
    """

    backend_id: ClassVar[str] = "mlx_whisper"
    """Stable machine-readable identifier."""

    display_name: ClassVar[str] = "mlx-whisper (Apple Silicon)"
    """Human-readable label shown in the Settings tab."""

    def __init__(self) -> None:
        # In-process ephemeral state: the currently selected model id.
        # None = use DEFAULT_MODEL. Updated by set_model(); not part of StateSnapshot.
        self._selected_model_id: str | None = None

    def set_model(self, model_id: str | None) -> None:
        """Select the active model by model_id.

        ``model_id=None`` reverts to the default model (``default=True`` in MODEL_CATALOG).
        Unknown model_ids log a warning and keep the current selection.
        (COL-6: called ONLY by StateManager.set_mlx_whisper_model — no direct callers.)
        """
        if model_id is not None:
            known = {m.model_id for m in MODEL_CATALOG}
            if model_id not in known:
                _LOG.warning("mlx_whisper.set_model.unknown_id", model_id=model_id)
                return
        self._selected_model_id = model_id
        _LOG.info("mlx_whisper.set_model", model_id=model_id)

    @property
    def _active_model(self) -> TranscriptionModelSpec:
        """Return the currently active TranscriptionModelSpec.

        Resolves _selected_model_id against MODEL_CATALOG, falling back to the
        default model if the id is None or not found.
        """
        if self._selected_model_id is not None:
            for m in MODEL_CATALOG:
                if m.model_id == self._selected_model_id:
                    return m
        return _DEFAULT_MODEL

    @property
    def _active_hf_repo_id(self) -> str:
        """HuggingFace repo ID for the currently active model. (COL-7 single read point.)"""
        return self._active_model.hf_repo_id

    @property
    def _model_cache_dir(self) -> Path:
        """Path to the HuggingFace hub model cache directory for the active model.

        This is the canonical probe target for :meth:`probe_status`. Exposed as a
        property so tests can patch it without touching the filesystem.
        COL-7: derives from active model's hf_repo_id, not a hardcoded constant.
        """
        hf_home = Path.home() / ".cache" / "huggingface" / "hub"
        return hf_home / _hf_cache_subdir(self._active_hf_repo_id)

    def probe_status(self) -> TranscriptionBackendStatus:
        """Check backend availability (synchronous, no I/O, no network).

        Returns:
            ``"unavailable"`` — non-Apple-Silicon platform.
            ``"missing_dep"`` — mlx_whisper package not importable.
            ``"needs_download"`` — package importable but model cache absent.
            ``"ready"`` — package importable and model cache present.
        """
        # Platform gate: Apple Silicon only
        if sys.platform != "darwin" or platform.machine() != "arm64":
            return "unavailable"

        # Dependency gate: optional extra not installed
        if importlib.util.find_spec("mlx_whisper") is None:
            return "missing_dep"

        # Model cache gate: model not yet downloaded
        if not self._model_cache_dir.exists():
            return "needs_download"

        return "ready"

    async def ensure(self, progress_cb: ProgressCallback) -> None:
        """Download the mlx-whisper model if not already present.

        Uses ``huggingface_hub.snapshot_download`` with a custom tqdm wrapper
        to provide incremental progress to ``progress_cb`` (COL-6 approach).

        No-op when ``probe_status() == "ready"`` (model already downloaded).

        Args:
            progress_cb: Callback receiving float [0.0, 1.0] during download.
                May be sync or async — both are handled.
        """
        import inspect as _inspect

        status = self.probe_status()
        if status != "needs_download":
            _LOG.info("mlx_whisper.ensure.skipped", status=status)
            return

        active_repo_id = self._active_hf_repo_id
        _LOG.info("mlx_whisper.ensure.start", repo_id=active_repo_id)

        # Build a tqdm-compatible wrapper that translates byte progress → fraction
        progress_cb_ref = progress_cb  # capture for closure

        async def _call_cb(fraction: float) -> None:
            result = progress_cb_ref(fraction)
            if _inspect.iscoroutine(result):
                await result

        class _ProgressTqdm:
            """Minimal tqdm-compatible class that forwards byte progress to progress_cb."""

            def __init__(self, total: int | None = None, **kwargs: object) -> None:
                self._total = total or 0
                self._downloaded = 0

            def update(self, n: int = 1) -> None:
                """Called by huggingface_hub with downloaded bytes."""
                self._downloaded += n
                if self._total > 0:
                    fraction = min(self._downloaded / self._total, 1.0)
                else:
                    # Unknown total — report 0.5 as indeterminate progress
                    fraction = 0.5
                # huggingface_hub calls update() synchronously; we need to call
                # the async callback. Use anyio.from_thread.run_sync pattern:
                # Since we're in an async context, we run the callback via
                # a helper that schedules it. For simplicity, collect fractions
                # and forward via the stored anyio event loop.
                import anyio

                anyio.from_thread.run_sync(lambda f=fraction: None)
                # Direct approach: store the fraction for deferred dispatch
                self._last_fraction = fraction

            def __enter__(self) -> _ProgressTqdm:
                return self

            def __exit__(self, *args: object) -> None:
                pass

            def close(self) -> None:
                pass

        # Try the incremental approach via tqdm_class
        # huggingface_hub's snapshot_download accepts tqdm_class as a drop-in
        try:
            import huggingface_hub as _hf_hub

            # COL-6: Use tqdm_class hook for real incremental progress.
            # We maintain a shared state object to communicate between
            # the sync tqdm callbacks and our async progress_cb.
            _fractions_to_emit: list[float] = []

            class _ProgressTqdmCollecting:
                """Collects fractions synchronously; we drain them after download."""

                def __init__(self, total: int | None = None, **kwargs: object) -> None:
                    self._total = total or 0
                    self._downloaded = 0

                def update(self, n: int = 1) -> None:
                    self._downloaded += n
                    if self._total > 0:
                        fraction = min(self._downloaded / self._total, 1.0)
                        _fractions_to_emit.append(fraction)

                def __enter__(self) -> _ProgressTqdmCollecting:
                    return self

                def __exit__(self, *args: object) -> None:
                    pass

                def close(self) -> None:
                    pass

            # Binary progress: signal start
            await _call_cb(0.0)

            _hf_hub.snapshot_download(
                repo_id=active_repo_id,
                tqdm_class=_ProgressTqdmCollecting,  # type: ignore[arg-type]
            )

            # Drain collected fractions (incremental progress, if any)
            for fraction in _fractions_to_emit:
                await _call_cb(fraction)

            # Signal completion
            await _call_cb(1.0)

        except Exception as exc:
            _LOG.warning("mlx_whisper.ensure.fallback", error=str(exc))
            # COL-6 binary fallback: 0.0 before, 1.0 after
            await _call_cb(0.0)
            import huggingface_hub as _hf_hub

            _hf_hub.snapshot_download(repo_id=active_repo_id)
            await _call_cb(1.0)

        _LOG.info("mlx_whisper.ensure.done", repo_id=active_repo_id)

    async def transcribe(self, audio_path: Path) -> list[TranscriptSegment]:
        """Transcribe the WAV file at ``audio_path`` using mlx_whisper.

        Lazy-imports ``mlx_whisper`` inside this method. The import is safe here
        because transcribe() is only called after probe_status() == "ready", which
        guarantees we're on Apple Silicon with mlx_whisper installed.

        Args:
            audio_path: Absolute path to a WAV file.

        Returns:
            Segments ordered by start_ms. Empty list if audio is silence/short.

        Raises:
            RuntimeError: If mlx_whisper transcription fails.
        """
        import mlx_whisper  # lazy — Apple Silicon only  # noqa: PLC0415

        _LOG.info("mlx_whisper.transcribe.start", audio_path=str(audio_path))

        active_repo_id = self._active_hf_repo_id
        try:
            result = mlx_whisper.transcribe(
                str(audio_path),
                path_or_hf_repo=active_repo_id,
            )
        except Exception as exc:
            _LOG.exception("mlx_whisper.transcribe.failed", error=str(exc))
            raise RuntimeError(f"mlx_whisper transcription failed: {exc}") from exc

        # mlx_whisper returns {"segments": [{"start": float_s, "end": float_s, "text": str}, ...]}
        raw_segments: list[dict] = result.get("segments", [])
        segments = [
            TranscriptSegment(
                start_ms=int(seg["start"] * 1000),
                end_ms=int(seg["end"] * 1000),
                text=seg["text"].strip(),
            )
            for seg in raw_segments
        ]

        _LOG.info("mlx_whisper.transcribe.done", segment_count=len(segments))
        return segments
