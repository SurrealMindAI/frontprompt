"""Tests for PostProcessor — async off-lock transcription + segment injection.

Sub-plan 05, Section 1 — TDD first.

Covers:
    - Status transitions: pending → transcribing → done
    - Segment batch-inject via append_transcript_segments (single lock acquire)
    - Segment ordering: sorted by start_ms ascending before inject
    - timestamp_ms = started_at_ms + segment.start_ms (via StateManager)
    - On backend exception: status → "failed", transcription_error set, no crash
    - On cancellation (COL-1): shielded finalize writes "failed" before propagating
    - started_at_ms is a PARAMETER (COL-3): PostProcessor never calls get_recording()
"""

from __future__ import annotations

import asyncio
from pathlib import Path
from typing import ClassVar
from unittest.mock import AsyncMock, MagicMock, call, patch

import anyio
import pytest


# ---------------------------------------------------------------------------
# Helpers — fake backend + counting StateManager
# ---------------------------------------------------------------------------


class _TwoSegmentBackend:
    """Mock backend returning 2 segments sorted by start_ms."""

    backend_id: ClassVar[str] = "fake_two_seg"
    display_name: ClassVar[str] = "Fake Two Segment"

    def probe_status(self) -> str:
        return "ready"

    async def ensure(self, progress_cb: object) -> None:
        pass

    async def transcribe(self, audio_path: Path) -> list:
        from frontprompt.voice.transcription import TranscriptSegment

        return [
            TranscriptSegment(start_ms=0, end_ms=500, text="Hello"),
            TranscriptSegment(start_ms=1000, end_ms=2000, text="world"),
        ]


class _FailingBackend:
    """Mock backend that raises on transcribe."""

    backend_id: ClassVar[str] = "fake_fail"
    display_name: ClassVar[str] = "Fake Failing"

    def probe_status(self) -> str:
        return "ready"

    async def ensure(self, progress_cb: object) -> None:
        pass

    async def transcribe(self, audio_path: Path) -> list:
        raise RuntimeError("transcription engine crashed")


class _ReverseOrderBackend:
    """Mock backend returning 2 segments in DESCENDING start_ms (tests sort discipline)."""

    backend_id: ClassVar[str] = "fake_reverse"
    display_name: ClassVar[str] = "Fake Reverse"

    def probe_status(self) -> str:
        return "ready"

    async def ensure(self, progress_cb: object) -> None:
        pass

    async def transcribe(self, audio_path: Path) -> list:
        from frontprompt.voice.transcription import TranscriptSegment

        return [
            TranscriptSegment(start_ms=2000, end_ms=3000, text="second"),
            TranscriptSegment(start_ms=100, end_ms=900, text="first"),
        ]


class _CancellationBackend:
    """Mock backend that raises the anyio cancellation exception (simulates COL-1)."""

    backend_id: ClassVar[str] = "fake_cancel"
    display_name: ClassVar[str] = "Fake Cancel"

    def probe_status(self) -> str:
        return "ready"

    async def ensure(self, progress_cb: object) -> None:
        pass

    async def transcribe(self, audio_path: Path) -> list:
        raise anyio.get_cancelled_exc_class()()


# ---------------------------------------------------------------------------
# Counting StateManager double — counts lock acquisitions for append_transcript_segments
# ---------------------------------------------------------------------------


class _CountingStateManager:
    """Minimal StateManager test double that records calls and lock acquisitions."""

    def __init__(self, session_id: str = "test-session", started_at_ms: int = 1_000_000_000) -> None:
        self.session_id = session_id
        self._transcription_status_calls: list[tuple[str, str, str | None]] = []
        self._append_calls: list[tuple[str, list, str]] = []
        self._lock_acquire_count = 0
        # Simulate the recording for timestamp_ms verification
        self._started_at_ms = started_at_ms

    async def set_transcription_status(
        self, recording_id: str, status: str, error: str | None = None
    ) -> object:
        self._transcription_status_calls.append((recording_id, status, error))
        return MagicMock()

    async def append_transcript_segments(
        self, recording_id: str, segments: list, backend_id: str = ""
    ) -> object:
        self._lock_acquire_count += 1
        self._append_calls.append((recording_id, segments, backend_id))
        return MagicMock()


# ---------------------------------------------------------------------------
# Section 1a: Happy-path — status transitions + segment injection
# ---------------------------------------------------------------------------


@pytest.mark.anyio
async def test_post_processor_status_transitions_pending_transcribing_done() -> None:
    """PostProcessor.run transitions: pending → transcribing → done."""
    from frontprompt.voice.post_processor import PostProcessor

    sm = _CountingStateManager()
    backend = _TwoSegmentBackend()
    pp = PostProcessor()

    await pp.run(
        recording_id="rec-001",
        audio_path=Path("/fake/audio.wav"),
        started_at_ms=1_000_000_000,
        state_manager=sm,  # type: ignore[arg-type]
        backend=backend,  # type: ignore[arg-type]
    )

    # Verify status transitions in order
    statuses = [(rec_id, status) for rec_id, status, _ in sm._transcription_status_calls]
    assert statuses == [
        ("rec-001", "pending"),
        ("rec-001", "transcribing"),
    ], f"Unexpected status transitions: {statuses}"
    # done is set via append_transcript_segments (atomically in the lock)
    assert sm._append_calls[0][0] == "rec-001"


@pytest.mark.anyio
async def test_post_processor_calls_append_transcript_segments_once() -> None:
    """append_transcript_segments is called exactly once for a 2-segment batch."""
    from frontprompt.voice.post_processor import PostProcessor

    sm = _CountingStateManager()
    backend = _TwoSegmentBackend()
    pp = PostProcessor()

    await pp.run(
        recording_id="rec-002",
        audio_path=Path("/fake/audio.wav"),
        started_at_ms=1_000_000_000,
        state_manager=sm,  # type: ignore[arg-type]
        backend=backend,  # type: ignore[arg-type]
    )

    # Exactly one batch-append call (PIT-105 non-broadcasting, single lock acquire)
    assert sm._lock_acquire_count == 1, (
        f"Expected exactly 1 lock acquisition for batch append, got {sm._lock_acquire_count}"
    )
    assert len(sm._append_calls) == 1, f"Expected 1 append_transcript_segments call, got {len(sm._append_calls)}"
    # 2 segments in the batch
    assert len(sm._append_calls[0][1]) == 2, f"Expected 2 segments in batch, got {len(sm._append_calls[0][1])}"


@pytest.mark.anyio
async def test_post_processor_segments_sorted_ascending() -> None:
    """Segments are sorted by start_ms ascending before injection."""
    from frontprompt.voice.post_processor import PostProcessor

    sm = _CountingStateManager()
    backend = _ReverseOrderBackend()
    pp = PostProcessor()

    await pp.run(
        recording_id="rec-003",
        audio_path=Path("/fake/audio.wav"),
        started_at_ms=0,
        state_manager=sm,  # type: ignore[arg-type]
        backend=backend,  # type: ignore[arg-type]
    )

    segments = sm._append_calls[0][1]
    start_times = [s.start_ms for s in segments]
    assert start_times == sorted(start_times), f"Segments not sorted by start_ms: {start_times}"
    assert start_times[0] == 100, f"Expected first segment start_ms=100, got {start_times[0]}"


@pytest.mark.anyio
async def test_post_processor_passes_started_at_ms_as_parameter() -> None:
    """PostProcessor uses started_at_ms parameter (COL-3 — no get_recording() call)."""
    from frontprompt.voice.post_processor import PostProcessor

    sm = _CountingStateManager(started_at_ms=5_000)
    backend = _TwoSegmentBackend()
    pp = PostProcessor()

    # Track if get_recording was ever called (it should never be)
    get_recording_called = False

    def _fail_on_get_recording(recording_id: str) -> None:  # type: ignore[return]
        nonlocal get_recording_called
        get_recording_called = True
        raise AssertionError("PostProcessor must NOT call state_manager.get_recording()")

    sm.get_recording = _fail_on_get_recording  # type: ignore[attr-defined]

    await pp.run(
        recording_id="rec-004",
        audio_path=Path("/fake/audio.wav"),
        started_at_ms=5_000,
        state_manager=sm,  # type: ignore[arg-type]
        backend=backend,  # type: ignore[arg-type]
    )

    assert not get_recording_called, "PostProcessor must NOT call get_recording() (COL-3)"


# ---------------------------------------------------------------------------
# Section 1b: Backend exception → status "failed"
# ---------------------------------------------------------------------------


@pytest.mark.anyio
async def test_post_processor_backend_exception_sets_failed_status() -> None:
    """On backend exception: status → 'failed', transcription_error set, no crash."""
    from frontprompt.voice.post_processor import PostProcessor

    sm = _CountingStateManager()
    backend = _FailingBackend()
    pp = PostProcessor()

    # Must NOT raise — exception is swallowed via re-raise inside BaseException guard
    # BUT wait — re-raise is for cancellation. For normal exceptions, what happens?
    # The plan says: "For a normal backend exception the same path applies — 'failed' + error, then re-raise."
    # The re-raise on a normal Exception means the caller needs to catch it too.
    # BUT for our PostProcessor.run() to not crash the task group, we need to handle it.
    # Actually the plan says: "the bare `raise` preserves cancellation semantics for the rest of the task group"
    # For normal exceptions, re-raising means the task fails. Let's check: the plan says
    # "For a normal backend exception the same path applies — 'failed' + error, then re-raise."
    # So PostProcessor.run() does re-raise. That means the caller (show_session) needs to handle it.
    # But the test says "no crash" — meaning the failed status is written. The re-raise is OK
    # because tg.start_soon() will propagate it to the task group.
    # For this test, we'll catch the re-raised exception.
    with pytest.raises(RuntimeError, match="transcription engine crashed"):
        await pp.run(
            recording_id="rec-005",
            audio_path=Path("/fake/audio.wav"),
            started_at_ms=0,
            state_manager=sm,  # type: ignore[arg-type]
            backend=backend,  # type: ignore[arg-type]
        )

    # Failed status was written before re-raise
    statuses = [(rec_id, status) for rec_id, status, _ in sm._transcription_status_calls]
    assert ("rec-005", "failed") in statuses, f"Expected 'failed' status, got: {statuses}"

    # transcription_error is set
    error_calls = [(rec_id, status, error) for rec_id, status, error in sm._transcription_status_calls
                   if status == "failed"]
    assert len(error_calls) == 1
    assert error_calls[0][2] is not None, "transcription_error must be set on failure"
    assert "transcription engine crashed" in error_calls[0][2]


# ---------------------------------------------------------------------------
# Section 1c: Cancellation (COL-1) — shielded finalize writes "failed"
# ---------------------------------------------------------------------------


@pytest.mark.anyio
async def test_post_processor_cancellation_writes_failed_status_before_propagating() -> None:
    """On cancellation: shielded finalize writes 'failed' before re-raising (COL-1)."""
    from frontprompt.voice.post_processor import PostProcessor

    sm = _CountingStateManager()
    backend = _CancellationBackend()
    pp = PostProcessor()

    cancelled_exc_class = anyio.get_cancelled_exc_class()

    with pytest.raises(cancelled_exc_class):
        await pp.run(
            recording_id="rec-006",
            audio_path=Path("/fake/audio.wav"),
            started_at_ms=0,
            state_manager=sm,  # type: ignore[arg-type]
            backend=backend,  # type: ignore[arg-type]
        )

    # The shielded finalize must have written "failed" BEFORE the cancellation propagated
    statuses = [(rec_id, status) for rec_id, status, _ in sm._transcription_status_calls]
    assert ("rec-006", "failed") in statuses, (
        f"COL-1 violated: 'failed' not written before cancellation propagated. Got: {statuses}"
    )
    # transcription_status must NOT be stuck at "transcribing"
    last_status_for_rec = [status for rec_id, status in statuses if rec_id == "rec-006"][-1]
    assert last_status_for_rec == "failed", (
        f"COL-1 violated: last status for rec-006 is {last_status_for_rec!r}, expected 'failed'"
    )
