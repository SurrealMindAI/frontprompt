"""Deterministic mock transcription backend for testing only.

Registered in the show-child subprocess when the env var
``FRONTPROMPT_TRANSCRIPTION_BACKEND=mock`` is active (wired in
``show_session.py:_run_browser``).

Returns 2 fixed segments regardless of input WAV content — designed so e2e
tests can assert exact segment indexing without installing mlx_whisper or
having real audio hardware.

NOT imported or registered in production code paths.
"""

from __future__ import annotations

from pathlib import Path
from typing import ClassVar

from frontprompt.voice.transcription import TranscriptSegment, TranscriptionBackendStatus


class MockTranscriptionBackend:
    """Fixed-segment mock backend for end-to-end tests.

    Returns deterministic segments so assertion on ``timestamp_ms``,
    ``text``, and ``seq`` is stable across runs.

    Segments (``MOCK_SEGMENTS``) are defined as class-level constants so
    test code can import them to construct expected values.
    """

    backend_id: ClassVar[str] = "mock"
    display_name: ClassVar[str] = "Mock (Test-Injection)"

    #: Fixed segments returned by this backend — import in tests to construct expected values.
    MOCK_SEGMENTS: ClassVar[tuple[TranscriptSegment, ...]] = (
        TranscriptSegment(start_ms=1000, end_ms=2500, text="hello world"),
        TranscriptSegment(start_ms=3000, end_ms=4500, text="from frontprompt"),
    )

    def probe_status(self) -> TranscriptionBackendStatus:
        return "ready"

    async def ensure(self, progress_cb: object) -> None:
        """No-op — mock backend needs no model download."""

    async def transcribe(self, audio_path: Path) -> list[TranscriptSegment]:
        """Return deterministic segments. audio_path is intentionally ignored."""
        return list(self.MOCK_SEGMENTS)


__all__ = ["MockTranscriptionBackend"]
