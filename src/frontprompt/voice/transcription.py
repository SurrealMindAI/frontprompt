"""TranscriptionBackend Protocol + registry.

Defines the abstract interface that all transcription backends must satisfy,
plus the global registry that backends register themselves into on import.

Design principles:
    - ``TranscriptionBackend`` is a ``@runtime_checkable`` Protocol so that fake/mock
      backends can be used in tests via ``isinstance()`` checks without inheriting
      from a concrete base class (sub-plan 06 e2e uses this for mock injection).
    - ``REGISTERED_BACKENDS`` is a plain list — backends append themselves when their
      module is imported (e.g. ``voice/backends/__init__.py`` imports MlxWhisperBackend).
    - All backend-specific imports (mlx_whisper, sounddevice, ...) are lazy — inside
      methods only — so importing this module never pulls heavy platform-specific deps.
"""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import TYPE_CHECKING, Awaitable, Callable, ClassVar, Literal, get_args, runtime_checkable

from typing_extensions import Protocol

if TYPE_CHECKING:
    pass

# ---------------------------------------------------------------------------
# TranscriptionBackendStatus — mirrors state.py's Literal exactly
# ---------------------------------------------------------------------------

TranscriptionBackendStatus = Literal[
    "unavailable", "missing_dep", "needs_download", "downloading", "ready", "error"
]
"""Availability status of a transcription backend.

Mirrors :data:`frontprompt.state.state.TranscriptionBackendStatus` exactly —
both must define the same values. The state.py definition is the Pydantic SSoT
(used in wire serialisation); this alias is the backend Protocol's vocabulary.

- ``unavailable``: Platform not supported (e.g. non-Apple-Silicon for mlx_whisper).
- ``missing_dep``: Optional extra not installed (``uv pip install frontprompt[voice]``).
- ``needs_download``: Dep installed, model not yet downloaded.
- ``downloading``: Model download in progress.
- ``ready``: Ready to transcribe.
- ``error``: Initialization error (see TranscriptionBackendInfo.error_message).
"""

# ---------------------------------------------------------------------------
# TranscriptSegment — return type from transcribe()
# ---------------------------------------------------------------------------


@dataclass(frozen=True)
class TranscriptSegment:
    """A single transcribed speech segment.

    Returned as a list by :meth:`TranscriptionBackend.transcribe`. Times are in
    integer milliseconds relative to the start of the audio recording.
    """

    start_ms: int
    """Segment start time in milliseconds (relative to recording start)."""

    end_ms: int
    """Segment end time in milliseconds (relative to recording start)."""

    text: str
    """Transcribed text for this segment."""


# ---------------------------------------------------------------------------
# ProgressCallback — type alias for download progress callbacks
# ---------------------------------------------------------------------------

ProgressCallback = Callable[[float], "Awaitable[None] | None"]
"""Callback type for download progress reporting.

Receives a float in ``[0.0, 1.0]``. May return an awaitable (async) or None (sync).
The backend implementation must handle both via ``inspect.iscoroutine`` / ``await``.
"""

# ---------------------------------------------------------------------------
# TranscriptionBackend — @runtime_checkable Protocol
# ---------------------------------------------------------------------------


@runtime_checkable
class TranscriptionBackend(Protocol):
    """Protocol for transcription backends.

    All concrete backends must implement this interface. Use ``@runtime_checkable``
    so that test fakes can be verified via ``isinstance(fake, TranscriptionBackend)``
    without subclassing.

    Platform notes:
        - :meth:`probe_status` is synchronous and cheap (filesystem + importlib check only,
          no network I/O). Mirrors :func:`frontprompt.browser.manager._chromium_present`.
        - :meth:`ensure` triggers the (potentially long) model download; call only when
          ``probe_status() == "needs_download"``.
        - :meth:`transcribe` must lazy-import heavy deps inside the method body.
    """

    backend_id: ClassVar[str]
    """Stable machine-readable identifier (e.g. ``"mlx_whisper"``)."""

    display_name: ClassVar[str]
    """Human-readable label (e.g. ``"mlx-whisper (Apple Silicon)"``). """

    def probe_status(self) -> TranscriptionBackendStatus:
        """Check backend availability synchronously (no I/O, no network).

        Returns one of :data:`TranscriptionBackendStatus` literals.
        """
        ...

    async def ensure(self, progress_cb: ProgressCallback) -> None:
        """Ensure the backend is ready (download model if needed).

        No-op when ``probe_status() == "ready"``. Calls ``progress_cb(fraction)``
        with floats in ``[0.0, 1.0]`` during download for progress reporting.
        """
        ...

    async def transcribe(self, audio_path: Path) -> list[TranscriptSegment]:
        """Transcribe the WAV file at ``audio_path``.

        Returns segments ordered by ``start_ms``. Lazy-imports backend deps inside.
        """
        ...


# ---------------------------------------------------------------------------
# REGISTERED_BACKENDS — global registry
# ---------------------------------------------------------------------------

REGISTERED_BACKENDS: list[TranscriptionBackend] = []
"""Global list of registered transcription backends.

Backends register themselves by appending an instance here when their module
is imported. Typically done in ``frontprompt/voice/backends/__init__.py``:

    from frontprompt.voice.backends.mlx_whisper import MlxWhisperBackend
    from frontprompt.voice import transcription
    transcription.REGISTERED_BACKENDS.append(MlxWhisperBackend())

This registry is what sub-plan 04's CLI ``bootstrap --voice`` and sub-plan 06's
e2e tests iterate over. E2E tests inject a mock backend by appending it before the
test and removing it after (see ``test_fake_backend_can_be_registered_and_deregistered``).
"""

# ---------------------------------------------------------------------------
# Validation helper — ensure TranscriptionBackendStatus matches state.py
# ---------------------------------------------------------------------------

_VALID_STATUSES: frozenset[str] = frozenset(get_args(TranscriptionBackendStatus))
"""Frozenset of valid backend status strings for runtime guard in select_backend()."""


def select_backend(preferred_id: str | None = None) -> TranscriptionBackend | None:
    """Select the best available backend from the registry.

    Args:
        preferred_id: If given, try this backend first. Falls back to the first
            ``"ready"`` backend in registration order. Returns None if no backend
            is ready.

    Returns:
        The selected backend instance, or ``None`` if none are ready.
    """
    if preferred_id is not None:
        for backend in REGISTERED_BACKENDS:
            if backend.backend_id == preferred_id and backend.probe_status() == "ready":
                return backend
    # Auto: first ready backend
    for backend in REGISTERED_BACKENDS:
        if backend.probe_status() == "ready":
            return backend
    return None
