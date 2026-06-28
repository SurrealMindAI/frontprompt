"""Tests for TranscriptionBackend Protocol + registry + TranscriptSegment.

Section 1 of sub-plan 04 — write tests first (TDD).
"""

from __future__ import annotations

import sys
from pathlib import Path
from typing import ClassVar

import pytest


# ---------------------------------------------------------------------------
# Section 1a: TranscriptSegment round-trip
# ---------------------------------------------------------------------------


def test_transcript_segment_round_trip() -> None:
    """TranscriptSegment round-trips with start_ms, end_ms, text fields."""
    from frontprompt.voice.transcription import TranscriptSegment

    seg = TranscriptSegment(start_ms=100, end_ms=2500, text="hello world")
    assert seg.start_ms == 100
    assert seg.end_ms == 2500
    assert seg.text == "hello world"


def test_transcript_segment_is_frozen() -> None:
    """TranscriptSegment is immutable (frozen dataclass or frozen Pydantic model)."""
    from frontprompt.voice.transcription import TranscriptSegment

    seg = TranscriptSegment(start_ms=0, end_ms=1000, text="test")
    with pytest.raises((AttributeError, TypeError)):
        seg.text = "mutated"  # type: ignore[misc]


# ---------------------------------------------------------------------------
# Section 1b: TranscriptionBackendStatus matches state.py literals
# ---------------------------------------------------------------------------


def test_backend_status_literals_match_state_py() -> None:
    """TranscriptionBackendStatus from transcription.py matches state.py's Literal."""
    from frontprompt.state.state import TranscriptionBackendStatus as StateStatus
    from frontprompt.voice.transcription import TranscriptionBackendStatus

    # Both should define the same set of valid values
    import typing

    transcription_args = set(typing.get_args(TranscriptionBackendStatus))
    state_args = set(typing.get_args(StateStatus))
    assert transcription_args == state_args, (
        f"Mismatch: transcription.py has {transcription_args}, state.py has {state_args}"
    )


# ---------------------------------------------------------------------------
# Section 1c: Fake backend implementing the Protocol passes duck-type checks
# ---------------------------------------------------------------------------


class _FakeBackend:
    """A minimal fake backend for testing — no real deps."""

    backend_id: ClassVar[str] = "fake_test_backend"
    display_name: ClassVar[str] = "Fake (Test)"

    def probe_status(self) -> str:
        return "ready"

    async def ensure(self, progress_cb: object) -> None:
        pass

    async def transcribe(self, audio_path: Path) -> list[object]:
        return []

    def set_model(self, model_id: str | None) -> None:
        pass


def test_fake_backend_satisfies_protocol() -> None:
    """A fake backend implementing the Protocol is accepted by the runtime check."""
    from frontprompt.voice.transcription import TranscriptionBackend

    fake = _FakeBackend()
    # Runtime isinstance check via typing.runtime_checkable or structural duck-type:
    # Protocol with @runtime_checkable lets isinstance work.
    assert isinstance(fake, TranscriptionBackend)


def test_fake_backend_has_required_class_vars() -> None:
    """Fake backend has the required ClassVar attributes."""
    assert _FakeBackend.backend_id == "fake_test_backend"
    assert _FakeBackend.display_name == "Fake (Test)"


# ---------------------------------------------------------------------------
# Section 1d: REGISTERED_BACKENDS registry
# ---------------------------------------------------------------------------


def test_registered_backends_is_a_list() -> None:
    """REGISTERED_BACKENDS is a list (may be empty or contain registered backends)."""
    from frontprompt.voice.transcription import REGISTERED_BACKENDS

    assert isinstance(REGISTERED_BACKENDS, list)


def test_fake_backend_can_be_registered_and_deregistered() -> None:
    """A fake backend can be appended to REGISTERED_BACKENDS for test injection."""
    from frontprompt.voice.transcription import REGISTERED_BACKENDS

    fake = _FakeBackend()
    original_length = len(REGISTERED_BACKENDS)
    REGISTERED_BACKENDS.append(fake)  # type: ignore[arg-type]
    try:
        assert len(REGISTERED_BACKENDS) == original_length + 1
        assert REGISTERED_BACKENDS[-1] is fake
    finally:
        REGISTERED_BACKENDS.remove(fake)  # type: ignore[arg-type]
    assert len(REGISTERED_BACKENDS) == original_length


# ---------------------------------------------------------------------------
# Section 1e: ProgressCallback type alias
# ---------------------------------------------------------------------------


def test_progress_callback_alias_is_callable() -> None:
    """ProgressCallback type alias exists and is a Callable annotation."""
    from frontprompt.voice.transcription import ProgressCallback

    # Just verify it exists as an annotation — can't instantiate a type alias directly
    assert ProgressCallback is not None


# ---------------------------------------------------------------------------
# Section 1f: transcription module does NOT import mlx_whisper at load time
# ---------------------------------------------------------------------------


def test_transcription_module_does_not_import_mlx_whisper_at_load() -> None:
    """Importing frontprompt.voice.transcription does NOT pull mlx_whisper into sys.modules."""
    import importlib

    # Drop any mlx_whisper modules a PRIOR test (e.g. the real-transcribe integration
    # test) left in sys.modules, so we measure ONLY what reloading the transcription
    # module itself pulls in — order-independent.
    for key in [k for k in sys.modules if k.startswith("mlx_whisper")]:
        del sys.modules[key]

    import frontprompt.voice.transcription

    importlib.reload(frontprompt.voice.transcription)
    # The transcription module's load must not (re-)import mlx_whisper (lazy-import discipline).
    mlx_keys_after = [k for k in sys.modules if k.startswith("mlx_whisper")]
    assert not mlx_keys_after, f"mlx_whisper was imported at module load: {mlx_keys_after}"


# ---------------------------------------------------------------------------
# Section 1g: select_backend — registry selection logic
# ---------------------------------------------------------------------------


class _ReadyBackend:
    """Fake backend that is always ready."""

    backend_id: str = "ready_backend"
    display_name: str = "Ready Backend"

    def probe_status(self) -> str:
        return "ready"

    async def ensure(self, progress_cb: object) -> None:
        pass

    async def transcribe(self, audio_path: object) -> list[object]:
        return []

    def set_model(self, model_id: object) -> None:
        pass


class _NotReadyBackend:
    """Fake backend that is never ready."""

    backend_id: str = "not_ready_backend"
    display_name: str = "Not Ready Backend"

    def probe_status(self) -> str:
        return "unavailable"

    async def ensure(self, progress_cb: object) -> None:
        pass

    async def transcribe(self, audio_path: object) -> list[object]:
        return []

    def set_model(self, model_id: object) -> None:
        pass


def test_select_backend_returns_none_when_registry_empty() -> None:
    """select_backend returns None when no backends are registered (covers line 190)."""
    from frontprompt.voice import transcription

    original = list(transcription.REGISTERED_BACKENDS)
    transcription.REGISTERED_BACKENDS.clear()
    try:
        result = transcription.select_backend()
        assert result is None
    finally:
        transcription.REGISTERED_BACKENDS.extend(original)


def test_select_backend_returns_none_when_no_backend_ready() -> None:
    """select_backend returns None when all registered backends are unavailable."""
    from frontprompt.voice import transcription

    original = list(transcription.REGISTERED_BACKENDS)
    transcription.REGISTERED_BACKENDS.clear()
    not_ready = _NotReadyBackend()
    transcription.REGISTERED_BACKENDS.append(not_ready)  # type: ignore[arg-type]
    try:
        result = transcription.select_backend()
        assert result is None
    finally:
        transcription.REGISTERED_BACKENDS.clear()
        transcription.REGISTERED_BACKENDS.extend(original)


def test_select_backend_with_preferred_id_finds_backend() -> None:
    """select_backend with preferred_id returns the matching ready backend (lines 183-185)."""
    from frontprompt.voice import transcription

    original = list(transcription.REGISTERED_BACKENDS)
    transcription.REGISTERED_BACKENDS.clear()
    ready = _ReadyBackend()
    transcription.REGISTERED_BACKENDS.append(ready)  # type: ignore[arg-type]
    try:
        result = transcription.select_backend(preferred_id="ready_backend")
        assert result is ready
    finally:
        transcription.REGISTERED_BACKENDS.clear()
        transcription.REGISTERED_BACKENDS.extend(original)


def test_select_backend_preferred_id_not_ready_falls_back() -> None:
    """select_backend with preferred_id that is not ready falls back to auto-select."""
    from frontprompt.voice import transcription

    original = list(transcription.REGISTERED_BACKENDS)
    transcription.REGISTERED_BACKENDS.clear()
    not_ready = _NotReadyBackend()
    ready = _ReadyBackend()
    transcription.REGISTERED_BACKENDS.append(not_ready)  # type: ignore[arg-type]
    transcription.REGISTERED_BACKENDS.append(ready)  # type: ignore[arg-type]
    try:
        # preferred_id=not_ready_backend exists but is not ready → falls back to first ready
        result = transcription.select_backend(preferred_id="not_ready_backend")
        assert result is ready
    finally:
        transcription.REGISTERED_BACKENDS.clear()
        transcription.REGISTERED_BACKENDS.extend(original)


# ---------------------------------------------------------------------------
# Section 1h: Protocol default set_model (line 126 in transcription.py)
# ---------------------------------------------------------------------------


def test_protocol_set_model_default_is_noop() -> None:
    """A class subclassing TranscriptionBackend inherits the Protocol's set_model no-op.

    Calling the inherited set_model() executes line 126 (the ``return`` body).
    """
    from frontprompt.voice.transcription import TranscriptionBackend

    class _MinimalBackend(TranscriptionBackend):  # type: ignore[misc]
        backend_id: str = "minimal_proto"
        display_name: str = "Minimal Proto"

        def probe_status(self) -> str:
            return "ready"

        async def ensure(self, progress_cb: object) -> None:
            pass

        async def transcribe(self, audio_path: object) -> list[object]:
            return []

        # set_model intentionally NOT overridden → inherits Protocol default body

    backend = _MinimalBackend()
    # Should complete without raising — Protocol default is a bare `return`
    backend.set_model("any_model_id")
    backend.set_model(None)
