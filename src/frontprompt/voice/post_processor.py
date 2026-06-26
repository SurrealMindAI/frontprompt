"""PostProcessor — async off-lock transcription trigger + segment injection.

After a voice-over recording stops, ``PostProcessor.run`` is spawned as a
separate anyio task (via ``tg.start_soon``) from ``show_session.py``.

Design principles:
    - **Off-lock**: transcription (which may take seconds) runs completely
      outside the StateManager lock. Only the batch-inject and status flips
      use the lock (via StateManager methods).
    - **COL-1 (cancellation safety)**: the body is wrapped in
      ``try/except BaseException`` with a ``anyio.CancelScope(shield=True)``
      finaliser. When the browser closes (``tg.cancel_scope.cancel()``), the
      in-flight task receives cancellation at the next ``await`` checkpoint.
      Without shielding, the recording would be stuck at ``transcription_status
      = "transcribing"`` in SQLite forever. The shielded finaliser writes
      ``"failed"`` before re-raising so cancellation still propagates correctly.
    - **COL-3 (started_at_ms parameter)**: ``started_at_ms`` is passed in as a
      parameter from the ``_on_recording_stop`` handler — PostProcessor NEVER
      calls ``state_manager.get_recording()``.
    - **COL-8 (WAV retention)**: PostProcessor does NOT delete the WAV after
      segments persist. The WAV is a durable source artifact for re-transcription.
    - **Single broadcast**: ``append_transcript_segments`` holds the lock once
      for all appends and sets ``transcription_status="done"`` atomically,
      emitting a single snapshot broadcast (PIT-105 discipline).
"""

from __future__ import annotations

from pathlib import Path
from typing import TYPE_CHECKING

import anyio
import structlog

from frontprompt.state.state import TranscriptSegmentEntry

if TYPE_CHECKING:
    from frontprompt.state.manager import StateManager
    from frontprompt.voice.transcription import TranscriptionBackend

_LOG = structlog.get_logger("frontprompt.voice.post_processor")


class PostProcessor:
    """Async off-lock post-processor: transcription trigger + segment injection.

    Instantiated once in ``ShowSession.__init__`` and reused across recordings.
    Each recording stop spawns a new ``run`` task via ``tg.start_soon``.
    """

    async def run(
        self,
        recording_id: str,
        audio_path: Path,
        started_at_ms: int,
        state_manager: StateManager,
        backend: TranscriptionBackend,
    ) -> None:
        """Transcribe ``audio_path`` and inject segments into the recording timeline.

        Steps:
            1. Set status → ``"pending"`` (locked, broadcast)
            2. Yield to let broadcast fire before heavy I/O
            3. Set status → ``"transcribing"`` (locked, broadcast)
            4. Transcribe off-lock (may take seconds)
            5. Sort segments by ``start_ms`` ascending
            6. Build ``TranscriptSegmentEntry`` list
            7. Batch-inject via ``append_transcript_segments`` (single lock + broadcast)

        COL-1 (shielded finalize): the entire body is wrapped in
        ``try/except BaseException``. On any exception (including anyio
        cancellation), the handler writes ``"failed"`` inside a
        ``anyio.CancelScope(shield=True)`` so the write completes even if
        the outer task group is cancelling. The bare ``raise`` preserves
        cancellation semantics.

        COL-3: ``started_at_ms`` is a parameter — not read from the StateManager.
        """
        log = _LOG.bind(recording_id=recording_id, audio_path=str(audio_path))
        try:
            # Step 1: pending
            await state_manager.set_transcription_status(recording_id, "pending", error=None)
            # Step 2: yield so pending broadcast fires before heavy I/O
            await anyio.sleep(0)
            # Step 3: transcribing
            await state_manager.set_transcription_status(recording_id, "transcribing", error=None)
            log.info("voice_over.post_processor.transcribing_started")

            # Step 4: transcribe off-lock (async, may take many seconds)
            segments = await backend.transcribe(audio_path)
            log.info("voice_over.post_processor.transcription_done", segment_count=len(segments))

            # Step 5: sort by start_ms ascending
            segments = sorted(segments, key=lambda s: s.start_ms)

            # Step 6: build TranscriptSegmentEntry objects
            # timestamp_ms = started_at_ms + segment.start_ms
            # (StateManager also computes this internally from recording.started_at_ms,
            # but we pass it anyway for explicitness and to satisfy COL-3 — the
            # manager's computation uses its own recording.started_at_ms which must
            # equal the started_at_ms passed here.)
            entries = [
                TranscriptSegmentEntry(
                    kind="transcript_segment",
                    seq=0,           # stamped Python-side in append_transcript_segments
                    timestamp_ms=started_at_ms + seg.start_ms,
                    start_ms=seg.start_ms,
                    end_ms=seg.end_ms,
                    text=seg.text,
                    backend_id=backend.backend_id,
                )
                for seg in segments
            ]

            # Step 7: batch inject + set status="done" atomically (single lock, single broadcast)
            await state_manager.append_transcript_segments(
                recording_id, entries, backend_id=backend.backend_id
            )
            log.info("voice_over.post_processor.segments_injected", count=len(entries))

        except BaseException as exc:
            # COL-1: shielded finalize — writes "failed" status even if the task
            # group is cancelling. This prevents a permanently-stuck "transcribing"
            # status in SQLite after browser close.
            with anyio.CancelScope(shield=True):
                try:
                    await state_manager.set_transcription_status(
                        recording_id, "failed", error=str(exc)
                    )
                    log.warning(
                        "voice_over.post_processor.failed",
                        error=str(exc),
                        exc_type=type(exc).__name__,
                    )
                except Exception as inner_exc:
                    # If even the status-write fails (e.g. StateManager shutdown),
                    # log but don't suppress the original exception.
                    log.error("voice_over.post_processor.failed_status_write_error", error=str(inner_exc))
            raise


__all__ = ["PostProcessor"]
