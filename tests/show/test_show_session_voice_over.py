"""ShowSession voice-over extension tests — sub-plan 03.

Tests verify the wiring between ShowSession lifecycle and AudioCaptureManager /
MicrophoneWatcher without running a real browser. Handler methods are called
directly with mock dependencies injected.

Coverage:
    - RecordingStartRequested{with_voice_over=True} → AudioCaptureManager.start() called
    - RecordingStartRequested{with_voice_over=False} → AudioCaptureManager NOT called
    - RecordingStopRequested for voice-over recording → stop() + set_audio_path()
    - RecordingStopRequested for non-voice-over recording → AudioCaptureManager NOT called
    - MicrophoneWatcher task started in run()
"""

from __future__ import annotations

from pathlib import Path
from typing import Any
from unittest.mock import AsyncMock, MagicMock, patch

import anyio
import pytest


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _build_show_session(session_id: str = "test-session") -> Any:
    """Build a ShowSession with an in-memory StateManager for unit testing."""
    from frontprompt.show_session import ShowSession
    from frontprompt.state import StateManager

    sm = StateManager(session_id=session_id)
    s = ShowSession(url="https://example.com", state_manager=sm)
    return s


def _make_mock_audio_capture(start_returns: bool = True) -> MagicMock:
    """Mock AudioCaptureManager — start() and stop() are AsyncMock."""
    mock = MagicMock()
    mock.start = AsyncMock(return_value=start_returns)
    # stop returns a Path when voice-over was active, None otherwise
    mock.stop = AsyncMock(return_value=None)
    return mock


# ---------------------------------------------------------------------------
# Test 1: handler_count() still returns 25 (no new handlers added in sub-plan 03)
# ---------------------------------------------------------------------------


def test_show_session_handler_count_is_28() -> None:
    """Sub-plan 05 adds 3 voice-over settings handlers — handler_count must be 28.

    +3 new handlers (SetMicDevice, SetTranscriptionBackend, TriggerModelDownload)
    land in sub-plan 05, bumping the count from 25 → 28.
    """
    from frontprompt.show_session import ShowSession

    s = ShowSession(url="https://example.com")
    assert s.handler_count() == 28


# ---------------------------------------------------------------------------
# Test 2: RecordingStartRequested with with_voice_over=True → start() called
# ---------------------------------------------------------------------------


@pytest.mark.anyio
async def test_recording_start_with_voice_over_calls_audio_capture(tmp_path: Path) -> None:
    """_on_recording_start with with_voice_over=True must call AudioCaptureManager.start()."""
    from frontprompt.bridge.messages import RecordingStartRequested

    s = _build_show_session()
    mock_audio = _make_mock_audio_capture(start_returns=True)
    s._audio_capture = mock_audio
    s._voice_over_recording_ids = set()

    msg = RecordingStartRequested(
        name="My Recording",
        description="",
        with_voice_over=True,
        mic_device_id=None,
    )

    with patch("frontprompt.ipc.paths.sessions_root", return_value=tmp_path):
        await s._on_recording_start(msg)

    mock_audio.start.assert_called_once()
    call_args = mock_audio.start.call_args
    # recording_id, device_id, wav_path
    assert call_args is not None
    recording_id_arg = call_args[0][0]
    assert isinstance(recording_id_arg, str) and len(recording_id_arg) > 0
    # recording_id must be in _voice_over_recording_ids after successful start
    assert recording_id_arg in s._voice_over_recording_ids


@pytest.mark.anyio
async def test_recording_start_voice_over_adds_to_tracking_set(tmp_path: Path) -> None:
    """Successfully started voice-over recording_id is added to _voice_over_recording_ids."""
    from frontprompt.bridge.messages import RecordingStartRequested

    s = _build_show_session()
    mock_audio = _make_mock_audio_capture(start_returns=True)
    s._audio_capture = mock_audio
    s._voice_over_recording_ids = set()

    msg = RecordingStartRequested(name="Test", description="", with_voice_over=True, mic_device_id=None)

    with patch("frontprompt.ipc.paths.sessions_root", return_value=tmp_path):
        await s._on_recording_start(msg)

    assert len(s._voice_over_recording_ids) == 1


# ---------------------------------------------------------------------------
# Test 3: RecordingStartRequested with with_voice_over=False → NOT called
# ---------------------------------------------------------------------------


@pytest.mark.anyio
async def test_recording_start_no_voice_over_does_not_call_audio_capture() -> None:
    """_on_recording_start with with_voice_over=False must NOT call AudioCaptureManager."""
    from frontprompt.bridge.messages import RecordingStartRequested

    s = _build_show_session()
    mock_audio = _make_mock_audio_capture()
    s._audio_capture = mock_audio
    s._voice_over_recording_ids = set()

    msg = RecordingStartRequested(
        name="My Recording",
        description="",
        with_voice_over=False,
        mic_device_id=None,
    )
    await s._on_recording_start(msg)

    mock_audio.start.assert_not_called()
    assert len(s._voice_over_recording_ids) == 0


# ---------------------------------------------------------------------------
# Test 4: audio_capture is None (not initialized) — does not crash
# ---------------------------------------------------------------------------


@pytest.mark.anyio
async def test_recording_start_with_voice_over_no_capture_manager_is_safe(tmp_path: Path) -> None:
    """If _audio_capture is None (not yet initialized), start with voice_over=True is a no-op."""
    from frontprompt.bridge.messages import RecordingStartRequested

    s = _build_show_session()
    s._audio_capture = None
    s._voice_over_recording_ids = set()

    msg = RecordingStartRequested(name="Test", description="", with_voice_over=True, mic_device_id=None)
    # Must not raise
    with patch("frontprompt.ipc.paths.sessions_root", return_value=tmp_path):
        await s._on_recording_start(msg)

    assert len(s._voice_over_recording_ids) == 0


# ---------------------------------------------------------------------------
# Test 5: RecordingStopRequested for voice-over recording → stop + set_audio_path
# ---------------------------------------------------------------------------


@pytest.mark.anyio
async def test_recording_stop_voice_over_calls_stop_and_set_audio_path(tmp_path: Path) -> None:
    """_on_recording_stop for a voice-over recording calls stop() and set_audio_path()."""
    from frontprompt.bridge.messages import RecordingStartRequested, RecordingStopRequested

    s = _build_show_session()
    wav_path = tmp_path / "recording-test.wav"
    wav_path.touch()  # simulate a WAV file that was written

    mock_audio = _make_mock_audio_capture(start_returns=True)
    mock_audio.stop = AsyncMock(return_value=wav_path)
    s._audio_capture = mock_audio
    s._voice_over_recording_ids = set()

    # Start a voice-over recording first to get recording_id
    start_msg = RecordingStartRequested(name="Test", description="", with_voice_over=True, mic_device_id=None)
    with patch("frontprompt.ipc.paths.sessions_root", return_value=tmp_path):
        await s._on_recording_start(start_msg)

    assert len(s._voice_over_recording_ids) == 1
    recording_id = next(iter(s._voice_over_recording_ids))

    # Spy on set_audio_path
    original_set_audio_path = s._sm.set_audio_path
    set_audio_path_calls: list[tuple[str, str]] = []

    async def _spy_set_audio_path(rec_id: str, path: str) -> Any:
        set_audio_path_calls.append((rec_id, path))
        return await original_set_audio_path(rec_id, path)

    s._sm.set_audio_path = _spy_set_audio_path  # type: ignore[method-assign]

    # Stop the voice-over recording
    stop_msg = RecordingStopRequested(recording_id=recording_id)
    await s._on_recording_stop(stop_msg)

    mock_audio.stop.assert_called_once_with(recording_id)
    assert len(set_audio_path_calls) == 1
    assert set_audio_path_calls[0][0] == recording_id
    assert set_audio_path_calls[0][1] == str(wav_path)
    # recording_id removed from tracking set
    assert recording_id not in s._voice_over_recording_ids


# ---------------------------------------------------------------------------
# Test 6: RecordingStopRequested for non-voice-over recording → NOT called
# ---------------------------------------------------------------------------


@pytest.mark.anyio
async def test_recording_stop_non_voice_over_does_not_call_audio_capture() -> None:
    """_on_recording_stop for a non-voice-over recording must NOT call audio_capture.stop()."""
    from frontprompt.bridge.messages import RecordingStartRequested, RecordingStopRequested

    s = _build_show_session()
    mock_audio = _make_mock_audio_capture()
    s._audio_capture = mock_audio
    s._voice_over_recording_ids = set()

    # Start a NON-voice-over recording
    start_msg = RecordingStartRequested(name="Test", description="", with_voice_over=False, mic_device_id=None)
    await s._on_recording_start(start_msg)

    # Get the recording_id from state
    recording_id = s._sm._recordings_state.active_recording_id
    assert recording_id is not None

    stop_msg = RecordingStopRequested(recording_id=recording_id)
    await s._on_recording_stop(stop_msg)

    mock_audio.stop.assert_not_called()


# ---------------------------------------------------------------------------
# Test 7: MicrophoneWatcher task started in run()
# ---------------------------------------------------------------------------


@pytest.mark.anyio
async def test_mic_watcher_task_started_in_run() -> None:
    """ShowSession.run() starts the MicrophoneWatcher background task."""
    import sys

    from frontprompt.show_session import ShowSession

    mic_watcher_run_called = False

    # Build fake sounddevice for the lazy imports in audio_capture + mic_watcher
    import types

    fake_sd = types.ModuleType("sounddevice")

    class FakePortAudioError(Exception):
        pass

    fake_sd.PortAudioError = FakePortAudioError  # type: ignore[attr-defined]
    fake_sd.InputStream = MagicMock()  # type: ignore[attr-defined]
    fake_sd.query_devices = MagicMock(return_value=[])  # type: ignore[attr-defined]

    s = ShowSession(url="https://example.com")

    with patch.dict(sys.modules, {"sounddevice": fake_sd}):
        with (
            patch("frontprompt.show_session.session_lifecycle") as mock_lifecycle_cm,
            patch("frontprompt.show_session.load_overlay_bundle", return_value="/*bundle*/"),
            patch("frontprompt.show_session.load_build_manifest") as mock_manifest,
            patch("frontprompt.show_session.BrowserSessionManager") as mock_browser_cls,
            patch("frontprompt.show_session.BridgeManager") as mock_bridge_cls,
            patch("frontprompt.show_session.OverlayInjector") as mock_injector_cls,
            patch("frontprompt.show_session.ElementResolver"),
            patch("frontprompt.show_session.PlaywrightPageController"),
            patch("frontprompt.show_session.run_socket_server", new=AsyncMock()),
            patch("frontprompt.cli._wait_for_socket_listening", new=AsyncMock()),
        ):
            mock_manifest.return_value = MagicMock(build_session="bs", schema_version="0.10.0")

            # Wire lifecycle CM
            from frontprompt.ipc import session as session_mod
            real_lifecycle = session_mod.session_lifecycle

            class _LifecycleCM:
                async def __aenter__(self) -> Any:
                    async for meta in real_lifecycle(url="https://example.com"):
                        return meta

                async def __aexit__(self, *args: object) -> None:
                    pass

            mock_lifecycle_cm.return_value = real_lifecycle(url="https://example.com")

            # Browser
            browser = AsyncMock()
            browser.page = AsyncMock()
            browser.wait_until_closed = AsyncMock()
            browser.navigate = AsyncMock()
            mock_browser_cls.return_value.__aenter__ = AsyncMock(return_value=browser)
            mock_browser_cls.return_value.__aexit__ = AsyncMock(return_value=None)

            # Bridge
            bridge = AsyncMock()
            bridge.set_task_group = MagicMock()
            bridge.on = MagicMock()
            bridge.wait_until_ready = AsyncMock(
                return_value=MagicMock(bundle_build_session="bs", schema_version="0.10.0")
            )
            mock_bridge_cls.return_value.__aenter__ = AsyncMock(return_value=bridge)
            mock_bridge_cls.return_value.__aexit__ = AsyncMock(return_value=None)

            injector = AsyncMock()
            injector.install_init_script = AsyncMock()
            injector.verify_mounted = AsyncMock()
            mock_injector_cls.return_value = injector

            with anyio.fail_after(5):
                await s.run()

    # Verify that _mic_watcher was constructed (it exists on the session after run())
    assert s._mic_watcher is not None, "MicrophoneWatcher must be constructed in run()"
    assert s._audio_capture is not None, "AudioCaptureManager must be constructed in run()"
