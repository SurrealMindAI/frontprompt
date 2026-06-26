"""Tests for AudioCaptureManager — sounddevice → WAV drainer pipeline.

Sub-plan 03 (voice-over). All tests mock sounddevice — no real PortAudio needed.

Coverage:
    - COL-2: lazy import (sounddevice not at module level)
    - COL-5: drainer join pattern (drain_complete before wave.close)
    - COL-7: PortAudioError degrade (warn, cleanup, set_has_voice_over=False)
    - COL-8: WAV retained as durable artifact (not deleted on stop)
"""

from __future__ import annotations

import queue
import sys
import threading
import types
import wave
from pathlib import Path
from unittest.mock import AsyncMock, MagicMock, call, patch

import anyio
import pytest


# ---------------------------------------------------------------------------
# Helpers: fake sounddevice module + FakeStream factory
# ---------------------------------------------------------------------------


def _make_fake_sd(raise_on_open: bool = False) -> types.ModuleType:
    """Build a minimal sounddevice substitute that satisfies AudioCaptureManager."""
    fake = types.ModuleType("sounddevice")

    class FakePortAudioError(Exception):
        pass

    fake.PortAudioError = FakePortAudioError  # type: ignore[attr-defined]

    class FakeInputStream:
        def __init__(self, *args: object, callback: object = None, **kwargs: object) -> None:
            self.callback = callback
            self._started = False
            if raise_on_open:
                raise FakePortAudioError("test: device unavailable")

        def start(self) -> None:
            self._started = True

        def stop(self) -> None:
            self._started = False

        def close(self) -> None:
            pass

    fake.InputStream = FakeInputStream  # type: ignore[attr-defined]
    return fake


def _make_mock_state_manager() -> MagicMock:
    """AsyncMock-based StateManager double with set_has_voice_over."""
    sm = MagicMock()
    sm.set_has_voice_over = AsyncMock()
    return sm


# ---------------------------------------------------------------------------
# COL-2: lazy import — sounddevice NOT imported at module load
# ---------------------------------------------------------------------------


def test_audio_capture_lazy_import_no_sounddevice_at_module_level() -> None:
    """Importing voice/audio_capture.py must NOT trigger `import sounddevice`.

    COL-2: sounddevice is a [voice] optional extra. Module-level import would crash
    on every non-[voice] install.
    """
    # Remove sounddevice from sys.modules if cached from another test
    sd_backup = sys.modules.pop("sounddevice", None)
    # Also clear any cached audio_capture module to force re-evaluation
    sys.modules.pop("frontprompt.voice.audio_capture", None)

    try:
        import frontprompt.voice.audio_capture  # noqa: F401 — import side-effect only
        assert "sounddevice" not in sys.modules, (
            "sounddevice MUST NOT be imported at module level of voice/audio_capture.py — "
            "it is a [voice] optional extra. Use lazy import inside methods."
        )
    finally:
        # Restore sys.modules state
        if sd_backup is not None:
            sys.modules["sounddevice"] = sd_backup
        sys.modules.pop("frontprompt.voice.audio_capture", None)


# ---------------------------------------------------------------------------
# Basic: stop a never-started capture is a no-op
# ---------------------------------------------------------------------------


@pytest.mark.anyio
async def test_stop_never_started_is_noop() -> None:
    """Calling stop() on an AudioCaptureManager that never started returns None."""
    from frontprompt.voice.audio_capture import AudioCaptureManager

    async with anyio.create_task_group() as tg:
        manager = AudioCaptureManager(tg)
        result = await manager.stop("nonexistent-recording-id")
        tg.cancel_scope.cancel()

    assert result is None


# ---------------------------------------------------------------------------
# Core: start writes frames, stop finalizes WAV
# ---------------------------------------------------------------------------


@pytest.mark.anyio
async def test_start_and_stop_produces_valid_wav(tmp_path: Path) -> None:
    """start() + stop() produces a valid WAV file at wav_path."""
    fake_sd = _make_fake_sd()

    with patch.dict(sys.modules, {"sounddevice": fake_sd}):
        from frontprompt.voice.audio_capture import AudioCaptureManager

        wav_path = tmp_path / "recording-test.wav"
        recording_id = "test-recording-1"

        async with anyio.create_task_group() as tg:
            manager = AudioCaptureManager(tg)
            started = await manager.start(recording_id, device_id=None, wav_path=wav_path)
            assert started is True, "start() should return True on success"

            # Simulate frames arriving from the C-callback (thread-safe put_nowait)
            # 1600 samples × 2 bytes = 3200 bytes of 16-bit mono audio at 16 kHz → 0.1 s
            frame_data = b"\x00\x01" * 1600
            assert manager._queue is not None
            manager._queue.put_nowait(frame_data)

            # Small delay to let drainer process the frame
            await anyio.sleep(0.05)

            result_path = await manager.stop(recording_id)
            tg.cancel_scope.cancel()

    assert result_path == wav_path
    assert wav_path.exists(), "WAV file must exist after stop (COL-8 retention)"

    # Verify valid WAV header
    with wave.open(str(wav_path), "rb") as wf:
        assert wf.getnchannels() == 1
        assert wf.getsampwidth() == 2  # 16-bit
        assert wf.getframerate() == 16000
        assert wf.getnframes() > 0


@pytest.mark.anyio
async def test_frames_arrive_in_drainer_queue(tmp_path: Path) -> None:
    """Frames put_nowait into the queue by the (simulated) C-callback reach the WAV."""
    fake_sd = _make_fake_sd()

    with patch.dict(sys.modules, {"sounddevice": fake_sd}):
        from frontprompt.voice.audio_capture import AudioCaptureManager

        wav_path = tmp_path / "recording-frames.wav"
        recording_id = "test-recording-frames"

        async with anyio.create_task_group() as tg:
            manager = AudioCaptureManager(tg)
            await manager.start(recording_id, device_id=0, wav_path=wav_path)

            # Feed 3 separate frame bursts (simulating multiple callback invocations)
            frame = b"\x10\x20" * 800  # 800 samples → 0.05 s per frame
            for _ in range(3):
                manager._queue.put_nowait(frame)  # type: ignore[union-attr]

            await anyio.sleep(0.05)
            await manager.stop(recording_id)
            tg.cancel_scope.cancel()

    with wave.open(str(wav_path), "rb") as wf:
        # 3 × 800 samples = 2400 frames total
        assert wf.getnframes() == 2400


# ---------------------------------------------------------------------------
# COL-5: drain_complete pattern — WAV header written AFTER all frames drained
# ---------------------------------------------------------------------------


@pytest.mark.anyio
async def test_drainer_join_via_drain_complete_event(tmp_path: Path) -> None:
    """stop() waits for drain_complete before closing WAV (COL-5).

    We put frames into the queue AFTER stream.stop() but BEFORE drain_complete
    is awaited, verifying they still reach the WAV file.
    """
    fake_sd = _make_fake_sd()

    with patch.dict(sys.modules, {"sounddevice": fake_sd}):
        from frontprompt.voice.audio_capture import AudioCaptureManager

        wav_path = tmp_path / "recording-drain.wav"
        recording_id = "test-drain"
        frame = b"\x00\x01" * 1000

        async with anyio.create_task_group() as tg:
            manager = AudioCaptureManager(tg)
            await manager.start(recording_id, device_id=None, wav_path=wav_path)

            # Enqueue a frame that hasn't been drained yet
            manager._queue.put_nowait(frame)  # type: ignore[union-attr]

            # stop() must drain the queue before closing WAV
            await manager.stop(recording_id)
            tg.cancel_scope.cancel()

    with wave.open(str(wav_path), "rb") as wf:
        assert wf.getnframes() == 1000, (
            "Frames enqueued before stop() must be drained (COL-5 drain_complete pattern)"
        )


# ---------------------------------------------------------------------------
# Duration correctness: 1000 samples / 16000 Hz = 62.5 ms → 1000 frames
# ---------------------------------------------------------------------------


@pytest.mark.anyio
async def test_wav_duration_matches_frames(tmp_path: Path) -> None:
    """WAV frame count matches exactly the number of samples fed to the queue."""
    fake_sd = _make_fake_sd()

    with patch.dict(sys.modules, {"sounddevice": fake_sd}):
        from frontprompt.voice.audio_capture import AudioCaptureManager

        wav_path = tmp_path / "recording-dur.wav"
        recording_id = "test-duration"
        n_samples = 1000
        frame_data = b"\x00\x01" * n_samples  # 1000 samples × 2 bytes (int16)

        async with anyio.create_task_group() as tg:
            manager = AudioCaptureManager(tg)
            await manager.start(recording_id, device_id=None, wav_path=wav_path)
            manager._queue.put_nowait(frame_data)  # type: ignore[union-attr]
            await anyio.sleep(0.05)
            await manager.stop(recording_id)
            tg.cancel_scope.cancel()

    with wave.open(str(wav_path), "rb") as wf:
        assert wf.getnframes() == n_samples


# ---------------------------------------------------------------------------
# Two independent instances — no shared global state
# ---------------------------------------------------------------------------


@pytest.mark.anyio
async def test_two_instances_are_independent(tmp_path: Path) -> None:
    """Two AudioCaptureManager instances capture independently (no shared queue/stream)."""
    fake_sd = _make_fake_sd()

    with patch.dict(sys.modules, {"sounddevice": fake_sd}):
        from frontprompt.voice.audio_capture import AudioCaptureManager

        wav_a = tmp_path / "recording-a.wav"
        wav_b = tmp_path / "recording-b.wav"

        async with anyio.create_task_group() as tg:
            mgr_a = AudioCaptureManager(tg)
            mgr_b = AudioCaptureManager(tg)

            await mgr_a.start("rec-a", device_id=0, wav_path=wav_a)
            await mgr_b.start("rec-b", device_id=1, wav_path=wav_b)

            # Feed different frame counts to each manager independently
            mgr_a._queue.put_nowait(b"\x01\x02" * 500)  # type: ignore[union-attr] — 500 samples
            mgr_b._queue.put_nowait(b"\x03\x04" * 300)  # type: ignore[union-attr] — 300 samples

            await anyio.sleep(0.05)

            await mgr_a.stop("rec-a")
            await mgr_b.stop("rec-b")
            tg.cancel_scope.cancel()

    with wave.open(str(wav_a), "rb") as wf_a:
        assert wf_a.getnframes() == 500

    with wave.open(str(wav_b), "rb") as wf_b:
        assert wf_b.getnframes() == 300


# ---------------------------------------------------------------------------
# COL-7: PortAudioError → degrade gracefully
# ---------------------------------------------------------------------------


@pytest.mark.anyio
async def test_portaudio_error_on_open_degrades_gracefully(tmp_path: Path) -> None:
    """When InputStream raises PortAudioError, start() must:
    - log a warning (not raise)
    - clean up any partial WAV file
    - call state_manager.set_has_voice_over(recording_id, False)
    - return False (not True)
    COL-7: degrade-gracefully path.
    """
    fake_sd = _make_fake_sd(raise_on_open=True)
    mock_sm = _make_mock_state_manager()

    with patch.dict(sys.modules, {"sounddevice": fake_sd}):
        from frontprompt.voice.audio_capture import AudioCaptureManager

        wav_path = tmp_path / "recording-fail.wav"
        recording_id = "test-portaudio-fail"

        async with anyio.create_task_group() as tg:
            manager = AudioCaptureManager(tg, state_manager=mock_sm)
            started = await manager.start(recording_id, device_id=99, wav_path=wav_path)
            tg.cancel_scope.cancel()

    assert started is False, "start() must return False on PortAudioError (COL-7)"
    assert not wav_path.exists(), "Partial WAV file must be cleaned up on PortAudioError (COL-7)"
    mock_sm.set_has_voice_over.assert_called_once_with(recording_id, False)


@pytest.mark.anyio
async def test_portaudio_error_does_not_propagate(tmp_path: Path) -> None:
    """PortAudioError must NOT propagate out of start() — test verifies no exception."""
    fake_sd = _make_fake_sd(raise_on_open=True)

    with patch.dict(sys.modules, {"sounddevice": fake_sd}):
        from frontprompt.voice.audio_capture import AudioCaptureManager

        wav_path = tmp_path / "recording-noprop.wav"

        async with anyio.create_task_group() as tg:
            manager = AudioCaptureManager(tg)
            # Must not raise
            result = await manager.start("test-id", device_id=0, wav_path=wav_path)
            tg.cancel_scope.cancel()

    assert result is False  # no exception raised, just returns False
