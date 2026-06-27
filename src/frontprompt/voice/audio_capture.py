"""AudioCaptureManager — sounddevice InputStream → WAV drainer pipeline.

Captures microphone audio into a per-session WAV file for voice-over transcription.

Design constraints:
    - COL-2: ``import sounddevice`` is LAZY — inside methods only, never at module top.
      sounddevice is a core dependency (promoted from [voice] optional extra in 0.0.6);
      the lazy import defers PortAudio initialization until capture is actually needed.
    - COL-5: drainer join pattern — C-callback → queue.Queue.put_nowait → anyio drainer task.
      ``stop()`` sets stop_flag, awaits drain_complete (set by drainer on exit), then
      wave.close(). WAV header is only finalised AFTER all frames are written.
    - COL-7: ``sounddevice.InputStream()`` may raise ``PortAudioError`` on invalid device /
      permission denied / disconnected device. ``start()`` catches it, logs warning, cleans up
      any partial WAV, calls ``state_manager.set_has_voice_over(False)`` to degrade, returns
      False — never propagates the exception.
    - COL-8: WAV file is kept as a durable source artifact after stop(); it is NOT deleted.
      Reclamation deferred to a future ``recordings clean-audio`` command.

WAV format: 16 kHz mono 16-bit PCM (mlx-whisper's expected input format).

Capture source extension seam:
    The module-level ``capture_source_override`` variable (default: ``None``) provides
    an extension point for alternative WAV sources. When set to an async callable with
    signature ``(recording_id: str, device_id: int | None, wav_path: Path) -> bool``,
    ``start()`` delegates to it instead of opening a real sounddevice stream.
    ``stop()`` in override mode returns ``wav_path`` immediately (no drainer wait).

    Production code must never set this variable. See
    ``tests/_subprocess_bootstrap/sitecustomize.py`` for the test-tree injection pattern.
"""

from __future__ import annotations

import queue
import threading
import wave
from pathlib import Path
from typing import TYPE_CHECKING

import anyio
import structlog

if TYPE_CHECKING:
    import anyio.abc

    from frontprompt.state import StateManager

_LOG = structlog.get_logger("frontprompt.voice.audio_capture")

# WAV constants — mlx-whisper expects 16 kHz mono int16
_SAMPLE_RATE: int = 16_000
_CHANNELS: int = 1
_SAMPLE_WIDTH: int = 2  # bytes — 16-bit PCM

# ---------------------------------------------------------------------------
# Capture source override — extension seam for alternative WAV providers.
# Production code must leave this as None.
# When set: async callable (recording_id: str, device_id: int | None, wav_path: Path) → bool.
# The callable must create the WAV file at wav_path before returning True.
# See tests/_subprocess_bootstrap/sitecustomize.py for the test-tree injection pattern.
# ---------------------------------------------------------------------------
capture_source_override: object = None


class AudioCaptureManager:
    """Manages a single microphone capture session: stream open → WAV drain → stop.

    Lifecycle::

        manager = AudioCaptureManager(task_group, state_manager=sm)
        started = await manager.start(recording_id, device_id, wav_path)
        if started:
            # ... recording runs ...
            wav_path = await manager.stop(recording_id)
            await sm.set_audio_path(recording_id, str(wav_path))

    Thread-safety:
        The sounddevice C-callback runs in a PortAudio thread. It only calls
        ``queue.Queue.put_nowait(bytes(indata))`` — thread-safe, no anyio calls.
        The drainer anyio task polls the queue via ``get_nowait()`` on a 10 ms
        interval. ``stop_flag`` (threading.Event) and ``drain_complete`` (anyio.Event)
        coordinate the shutdown sequence so ``wave.close()`` is called only after
        all frames are written (COL-5).
    """

    def __init__(
        self,
        task_group: anyio.abc.TaskGroup,
        *,
        state_manager: StateManager | None = None,
    ) -> None:
        self._tg = task_group
        self._state_manager = state_manager
        # Per-capture state — reset on each start()
        self._stream: object | None = None
        self._wav: wave.Wave_write | None = None
        self._queue: queue.Queue[bytes] | None = None
        self._stop_flag: threading.Event | None = None
        self._drain_complete: anyio.Event | None = None
        self._current_recording_id: str | None = None
        self._current_wav_path: Path | None = None
        # Alternative source mode — set when capture_source_override was used
        self._alternative_source_active: bool = False

    async def start(
        self,
        recording_id: str,
        device_id: int | None,
        wav_path: Path,
    ) -> bool:
        """Open microphone stream and start WAV drainer task.

        Args:
            recording_id: The recording being captured (used for degrade call on failure).
            device_id: sounddevice device index. ``None`` = system default.
            wav_path: Path where the WAV file will be written.

        Returns:
            ``True`` on success; ``False`` on PortAudioError (COL-7 degrade path,
            no exception propagated).

        Note:
            ``import sounddevice`` is lazy — only executed inside this method (COL-2);
            defers PortAudio initialization until capture is actually needed.

            When ``capture_source_override`` is set (non-None), delegates to it and
            returns without opening a real sounddevice stream.
        """
        # Extension seam: alternative capture source (set from test-tree bootstrap only).
        # Production code must never set capture_source_override. See tests/_subprocess_bootstrap/.
        if capture_source_override is not None:
            started: bool = await capture_source_override(recording_id, device_id, wav_path)  # type: ignore[misc]
            if started:
                self._current_recording_id = recording_id
                self._current_wav_path = wav_path
                self._alternative_source_active = True
                _LOG.info(
                    "voice.audio_capture.alternative_source_started",
                    recording_id=recording_id,
                    wav_path=str(wav_path),
                )
            return started

        import sounddevice as sd  # COL-2: lazy import — defer PortAudio init until capture needed

        # Reset per-capture state
        self._queue = queue.Queue()
        self._stop_flag = threading.Event()
        self._drain_complete = anyio.Event()
        self._current_recording_id = recording_id
        self._current_wav_path = wav_path

        # Open WAV file before stream to ensure we can write
        try:
            wav_file = wave.open(str(wav_path), "wb")
            wav_file.setnchannels(_CHANNELS)
            wav_file.setsampwidth(_SAMPLE_WIDTH)
            wav_file.setframerate(_SAMPLE_RATE)
            self._wav = wav_file
        except OSError as exc:
            _LOG.warning(
                "voice.audio_capture.wav_open_failed",
                recording_id=recording_id,
                wav_path=str(wav_path),
                error=str(exc),
            )
            self._reset_state()
            if self._state_manager is not None:
                await self._state_manager.set_has_voice_over(recording_id, False)
            return False

        # Open sounddevice InputStream — may raise PortAudioError (COL-7)
        def _callback(indata: object, frames: int, time_info: object, status: object) -> None:
            # C-callback: must only call thread-safe operations (no anyio, no await)
            self._queue.put_nowait(bytes(indata))  # type: ignore[union-attr]

        try:
            stream = sd.InputStream(
                device=device_id,
                samplerate=_SAMPLE_RATE,
                channels=_CHANNELS,
                dtype="int16",
                callback=_callback,
            )
            stream.start()
            self._stream = stream
        except sd.PortAudioError as exc:
            # COL-7: degrade gracefully — warn, clean up partial WAV, degrade state
            _LOG.warning(
                "voice.audio_capture.portaudio_error",
                recording_id=recording_id,
                device_id=device_id,
                error=str(exc),
            )
            # Close and remove partial WAV
            if self._wav is not None:
                try:
                    self._wav.close()
                except Exception:
                    pass
                self._wav = None
            try:
                wav_path.unlink(missing_ok=True)
            except Exception:
                pass
            self._reset_state()
            if self._state_manager is not None:
                await self._state_manager.set_has_voice_over(recording_id, False)
            return False

        # Launch drainer task via the injected task group (COL-5)
        # Captures local references so the drainer is self-contained
        stop_flag = self._stop_flag
        drain_complete = self._drain_complete
        q = self._queue
        wav_ref = self._wav
        self._tg.start_soon(self._drain, stop_flag, drain_complete, q, wav_ref)

        _LOG.info(
            "voice.audio_capture.started",
            recording_id=recording_id,
            device_id=device_id,
            wav_path=str(wav_path),
        )
        return True

    async def stop(self, recording_id: str) -> Path | None:
        """Stop the capture and finalise the WAV file.

        Args:
            recording_id: Must match the recording_id passed to ``start()``.

        Returns:
            The ``wav_path`` on success (COL-8: file is retained).
            ``None`` if no capture was active for ``recording_id`` (no-op).

        Note:
            ``wave.close()`` is called ONLY after ``drain_complete`` is awaited
            (COL-5) so the WAV header frame count is never corrupted by a premature
            close while frames are still in the drainer queue.

            When started via ``capture_source_override``, returns ``wav_path``
            immediately without waiting for a drainer (no stream was opened).
        """
        # Alternative source fast-path: no stream teardown needed.
        if self._alternative_source_active and self._current_recording_id == recording_id:
            wav_path = self._current_wav_path
            self._alternative_source_active = False
            self._reset_state()
            _LOG.info(
                "voice.audio_capture.alternative_source_stopped",
                recording_id=recording_id,
                wav_path=str(wav_path),
            )
            return wav_path

        if self._current_recording_id != recording_id or self._stream is None:
            _LOG.debug("voice.audio_capture.stop_noop", recording_id=recording_id)
            return None

        # Stop the stream — no more callbacks after this
        try:
            self._stream.stop()  # type: ignore[attr-defined]
            self._stream.close()  # type: ignore[attr-defined]
        except Exception as exc:
            _LOG.warning("voice.audio_capture.stream_close_error", error=str(exc))
        self._stream = None

        # Signal drainer to finish after draining remaining frames (COL-5)
        self._stop_flag.set()  # type: ignore[union-attr]
        await self._drain_complete.wait()  # type: ignore[union-attr]

        # Close WAV ONLY after drain_complete (COL-5 — header written after all frames)
        wav_path = self._current_wav_path
        if self._wav is not None:
            self._wav.close()
            self._wav = None

        _LOG.info("voice.audio_capture.stopped", recording_id=recording_id, wav_path=str(wav_path))
        self._reset_state()
        return wav_path  # COL-8: retained as durable artifact

    # ----- Internal helpers -------------------------------------------------

    def _reset_state(self) -> None:
        """Clear per-capture state without touching stop_flag/drain_complete."""
        self._current_recording_id = None
        self._current_wav_path = None

    @staticmethod
    async def _drain(
        stop_flag: threading.Event,
        drain_complete: anyio.Event,
        q: queue.Queue[bytes],
        wav: wave.Wave_write,
    ) -> None:
        """Anyio drainer task — COL-5 pattern.

        Polls the queue every 10 ms. Continues until stop_flag is set AND the
        queue is empty (all in-flight frames from the C-callback are written).
        Sets drain_complete before exiting so stop() can safely call wave.close().
        """
        while not (stop_flag.is_set() and q.empty()):
            await anyio.sleep(0.01)  # 10 ms poll — fine for a post-processing flow
            # Drain all available frames in this tick
            while True:
                try:
                    frames = q.get_nowait()
                    wav.writeframes(frames)
                except queue.Empty:
                    break
        drain_complete.set()  # signal stop() that all frames are written


__all__ = ["AudioCaptureManager"]
