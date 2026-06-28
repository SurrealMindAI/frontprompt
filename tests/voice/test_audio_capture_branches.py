"""AudioCaptureManager branch coverage tests.

Covers paths NOT exercised by the main test_audio_capture.py:
- capture_source_override path (start + stop fast-path)
- OSError on wav.open() — degrade path
- stream close exception on stop() (swallowed)
- _callback direct invocation (frames → queue)
"""

from __future__ import annotations

import sys
import types
import wave
from pathlib import Path
from unittest.mock import AsyncMock, MagicMock, patch

import anyio
import pytest


def _make_fake_sd_normal() -> types.ModuleType:
    """Fake sounddevice with a working InputStream (no errors)."""
    fake = types.ModuleType("sounddevice")

    class FakePortAudioError(Exception):
        pass

    fake.PortAudioError = FakePortAudioError  # type: ignore[attr-defined]

    class FakeInputStream:
        def __init__(self, *args: object, callback: object = None, **kwargs: object) -> None:
            self._callback = callback

        def start(self) -> None:
            pass

        def stop(self) -> None:
            pass

        def close(self) -> None:
            pass

    fake.InputStream = FakeInputStream  # type: ignore[attr-defined]
    return fake


def _make_fake_sd_raise_on_close() -> types.ModuleType:
    """Fake sounddevice whose stream raises on stop() and close() — tests stream close exception path."""
    fake = types.ModuleType("sounddevice")

    class FakePortAudioError(Exception):
        pass

    fake.PortAudioError = FakePortAudioError  # type: ignore[attr-defined]

    class FakeInputStreamBadClose:
        def __init__(self, *args: object, callback: object = None, **kwargs: object) -> None:
            pass

        def start(self) -> None:
            pass

        def stop(self) -> None:
            raise RuntimeError("device disconnected")

        def close(self) -> None:
            raise RuntimeError("device disconnected")

    fake.InputStream = FakeInputStreamBadClose  # type: ignore[attr-defined]
    return fake


# ── capture_source_override: start + stop fast-path ──────────────────────────


@pytest.mark.anyio
async def test_capture_source_override_start_delegates(tmp_path: Path) -> None:
    """When capture_source_override is set, start() delegates to it instead of sounddevice."""
    wav_path = tmp_path / "override.wav"
    recording_id = "rec-override"
    calls: list[tuple] = []

    async def fake_source(rid: str, device_id: object, path: Path) -> bool:
        calls.append((rid, device_id, path))
        # Create a minimal WAV so stop() has a path to return
        with wave.open(str(path), "wb") as wf:
            wf.setnchannels(1)
            wf.setsampwidth(2)
            wf.setframerate(16000)
        return True

    import frontprompt.voice.audio_capture as capture_module

    original = capture_module.capture_source_override
    try:
        capture_module.capture_source_override = fake_source

        async with anyio.create_task_group() as tg:
            from frontprompt.voice.audio_capture import AudioCaptureManager

            mgr = AudioCaptureManager(tg)
            started = await mgr.start(recording_id, device_id=None, wav_path=wav_path)
            assert started is True
            assert mgr._alternative_source_active is True
            assert mgr._current_recording_id == recording_id

            result = await mgr.stop(recording_id)
            assert result == wav_path
            assert mgr._alternative_source_active is False
            tg.cancel_scope.cancel()
    finally:
        capture_module.capture_source_override = original

    assert len(calls) == 1
    assert calls[0][0] == recording_id


@pytest.mark.anyio
async def test_capture_source_override_start_returns_false(tmp_path: Path) -> None:
    """When capture_source_override returns False, start() returns False and sets no state."""
    wav_path = tmp_path / "override-false.wav"
    recording_id = "rec-override-false"

    async def fake_source_fail(rid: str, device_id: object, path: Path) -> bool:
        return False

    import frontprompt.voice.audio_capture as capture_module

    original = capture_module.capture_source_override
    try:
        capture_module.capture_source_override = fake_source_fail

        async with anyio.create_task_group() as tg:
            from frontprompt.voice.audio_capture import AudioCaptureManager

            mgr = AudioCaptureManager(tg)
            started = await mgr.start(recording_id, device_id=None, wav_path=wav_path)
            assert started is False
            assert mgr._alternative_source_active is False
            tg.cancel_scope.cancel()
    finally:
        capture_module.capture_source_override = original


# ── OSError on wav.open() ─────────────────────────────────────────────────────


@pytest.mark.anyio
async def test_wav_open_oserror_degrades_gracefully(tmp_path: Path) -> None:
    """OSError on wave.open() causes start() to return False without propagating."""
    fake_sd = _make_fake_sd_normal()
    mock_sm = MagicMock()
    mock_sm.set_has_voice_over = AsyncMock()

    wav_path = tmp_path / "bad.wav"

    with (
        patch.dict(sys.modules, {"sounddevice": fake_sd}),
        patch("wave.open", side_effect=OSError("permission denied")),
    ):
        from frontprompt.voice.audio_capture import AudioCaptureManager

        async with anyio.create_task_group() as tg:
            mgr = AudioCaptureManager(tg, state_manager=mock_sm)
            started = await mgr.start("rec-oserror", device_id=None, wav_path=wav_path)
            tg.cancel_scope.cancel()

    assert started is False
    mock_sm.set_has_voice_over.assert_called_once_with("rec-oserror", False)


# ── stream close exception swallowed on stop() ───────────────────────────────


@pytest.mark.anyio
async def test_stop_stream_close_exception_is_swallowed(tmp_path: Path) -> None:
    """If stream.stop()/close() raises, stop() swallows the exception and continues."""
    fake_sd = _make_fake_sd_raise_on_close()
    wav_path = tmp_path / "close-exc.wav"

    with patch.dict(sys.modules, {"sounddevice": fake_sd}):
        from frontprompt.voice.audio_capture import AudioCaptureManager

        async with anyio.create_task_group() as tg:
            mgr = AudioCaptureManager(tg)
            started = await mgr.start("rec-close-exc", device_id=None, wav_path=wav_path)
            assert started is True
            # stop() must not raise even though stream.stop() and close() raise
            result = await mgr.stop("rec-close-exc")
            tg.cancel_scope.cancel()

    # WAV should still be finalized
    assert result == wav_path


# ── _callback direct invocation ───────────────────────────────────────────────


@pytest.mark.anyio
async def test_callback_puts_frames_in_queue(tmp_path: Path) -> None:
    """The registered sounddevice callback puts bytes into the queue via put_nowait.

    This test directly exercises the _callback closure (line 175 of audio_capture.py)
    by extracting it from the FakeInputStream after start().
    """
    wav_path = tmp_path / "callback-test.wav"
    recorded_callback = [None]

    fake = types.ModuleType("sounddevice")

    class FakePortAudioError(Exception):
        pass

    fake.PortAudioError = FakePortAudioError  # type: ignore[attr-defined]

    class FakeInputStreamCapture:
        def __init__(self, *args: object, callback: object = None, **kwargs: object) -> None:
            # Store the callback so we can call it directly in the test
            recorded_callback[0] = callback

        def start(self) -> None:
            pass

        def stop(self) -> None:
            pass

        def close(self) -> None:
            pass

    fake.InputStream = FakeInputStreamCapture  # type: ignore[attr-defined]

    with patch.dict(sys.modules, {"sounddevice": fake}):
        from frontprompt.voice.audio_capture import AudioCaptureManager

        async with anyio.create_task_group() as tg:
            mgr = AudioCaptureManager(tg)
            await mgr.start("rec-cb", device_id=None, wav_path=wav_path)

            # Directly invoke the registered C-callback with fake audio data
            assert recorded_callback[0] is not None
            fake_indata = bytearray(b"\x01\x02" * 100)  # 100 int16 samples
            recorded_callback[0](fake_indata, 100, None, None)

            # Queue should now contain the bytes
            assert mgr._queue is not None
            assert not mgr._queue.empty()
            chunk = mgr._queue.get_nowait()
            assert chunk == bytes(fake_indata)

            await mgr.stop("rec-cb")
            tg.cancel_scope.cancel()
