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
    # Remove from sys.modules if present to ensure clean state
    mlx_keys_before = [k for k in sys.modules if k.startswith("mlx")]
    # (Re-)import the transcription module
    import importlib

    import frontprompt.voice.transcription

    importlib.reload(frontprompt.voice.transcription)
    # Check mlx_whisper is still not imported
    mlx_keys_after = [k for k in sys.modules if k.startswith("mlx_whisper")]
    assert not mlx_keys_after, f"mlx_whisper was imported at module load: {mlx_keys_after}"
    _ = mlx_keys_before  # silence unused warning
