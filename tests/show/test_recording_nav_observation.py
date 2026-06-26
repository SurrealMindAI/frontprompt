"""ShowSession nav observation tests — sub-plan 04.

Covers:
  1. OverlayReady with same URL as last known: no NavigationEntry appended
  2. OverlayReady with NEW URL + active recording: NavigationEntry appended
  3. OverlayReady with NEW URL + no active recording: no NavigationEntry appended
  4. from_url is the previous URL (tracked in ShowSession state)
  5. to_url is the new URL (from browser.page.url)
  6. _last_url updated after every OverlayReady

Tests call the OverlayReady-aware inner closure directly by constructing a minimal
mock of the BridgeManager + BrowserSessionManager surface — no real Chromium.
"""

from __future__ import annotations

from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from frontprompt.state import StateManager
from frontprompt.state.state import NavigationEntry


# ---------------------------------------------------------------------------
# Test helpers
# ---------------------------------------------------------------------------


def _make_session_with_manager(session_id: str = "test-nav") -> tuple:
    """Return (ShowSession, StateManager) with InMemory persistence."""
    from frontprompt.show_session import ShowSession

    sm = StateManager(session_id=session_id)
    s = ShowSession(url="https://example.com", state_manager=sm)
    return s, sm


async def _invoke_overlay_ready_handler(
    session,
    sm: StateManager,
    *,
    current_url: str,
) -> None:
    """
    Run a minimal _run_browser() mock to invoke the OverlayReady handler.

    This stubs all heavy dependencies (BrowserSessionManager, BridgeManager, etc.)
    and invokes the OverlayReady handler directly by triggering the bridge mock.

    We do NOT run the full anyio TaskGroup because the handler logic we test
    (_last_url tracking + NavigationEntry append) lives in the inner closure and
    can be extracted via the bridge.on(OverlayReady, ...) registration capture.
    """
    from frontprompt.bridge.messages import OverlayReady

    # Capture the OverlayReady handler as registered inside _run_browser()
    captured_handler = None

    class _CapturingBridge:
        def on(self, msg_cls, handler):
            nonlocal captured_handler
            if msg_cls is OverlayReady:
                captured_handler = handler

        async def send(self, msg):
            pass  # no-op for snapshot sends

        def set_task_group(self, tg):
            pass

        def wait_until_ready(self):
            pass

    # Mock browser.page.url (synchronous str property)
    mock_page = MagicMock()
    type(mock_page).url = property(lambda self: current_url)
    mock_page.expose_function = AsyncMock()

    mock_browser = MagicMock()
    mock_browser.page = mock_page
    mock_browser.navigate = AsyncMock()
    mock_browser.wait_until_closed = AsyncMock(return_value=None)

    capturing_bridge = _CapturingBridge()

    import anyio

    with (
        patch("frontprompt.show_session.session_lifecycle") as mock_lifecycle,
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
        from frontprompt.ipc.session import SessionMetadata

        mock_meta = SessionMetadata.for_current_process(session_id="test-nav", url="https://example.com")

        class _FakeLifecycle:
            async def __aenter__(self):
                return mock_meta

            async def __aexit__(self, *args):
                pass

        mock_lifecycle.return_value = _FakeLifecycle()
        mock_manifest.return_value = MagicMock(build_session="bs", schema_version="0.8.0")

        mock_browser_cls.return_value.__aenter__ = AsyncMock(return_value=mock_browser)
        mock_browser_cls.return_value.__aexit__ = AsyncMock(return_value=None)

        # Make BridgeManager return our capturing bridge
        mock_bridge_cls.return_value.__aenter__ = AsyncMock(return_value=capturing_bridge)
        mock_bridge_cls.return_value.__aexit__ = AsyncMock(return_value=None)

        injector = MagicMock()
        injector.install_init_script = AsyncMock()
        injector.verify_mounted = AsyncMock()
        mock_injector_cls.return_value = injector

        # Cancel after the handlers are registered (before waiting for page close)
        async def _wait_until_closed_cancel():
            raise anyio.get_cancelled_exc_class()()

        mock_browser.wait_until_closed = AsyncMock(side_effect=_wait_until_closed_cancel)

        with anyio.fail_after(5):
            try:
                await session.run()
            except (anyio.get_cancelled_exc_class(), BaseException):
                pass  # expected — we cancel at wait_until_closed

    # At this point captured_handler is the inner OverlayReady handler
    # that has the nav observation logic + bridge closure
    assert captured_handler is not None, "OverlayReady handler was not registered"
    return captured_handler


# ---------------------------------------------------------------------------
# Tests
# ---------------------------------------------------------------------------


@pytest.mark.anyio
async def test_nav_observation_no_entry_on_same_url() -> None:
    """OverlayReady with same URL twice: no NavigationEntry appended."""
    from frontprompt.bridge.messages import OverlayReady
    from frontprompt.show_session import ShowSession

    sm = StateManager(session_id="test-nav-same")
    session = ShowSession(url="https://example.com", state_manager=sm)

    handler = await _invoke_overlay_ready_handler(session, sm, current_url="https://example.com/page1")

    # Fire OverlayReady at same URL again
    msg = OverlayReady(bundle_build_session="bs")
    await handler(msg)
    await handler(msg)

    # Both fires same URL: no entries appended
    assert sm._full_recordings == {} or all(
        len(r.entries) == 0 for r in sm._full_recordings.values()
    ), "No NavigationEntry should be appended when URL does not change"


@pytest.mark.anyio
async def test_nav_observation_entry_appended_on_url_change_with_active_recording() -> None:
    """OverlayReady with new URL + active recording: NavigationEntry appended."""
    from frontprompt.bridge.messages import OverlayReady, RecordingStartRequested
    from frontprompt.show_session import ShowSession

    sm = StateManager(session_id="test-nav-change")
    session = ShowSession(url="https://example.com", state_manager=sm)

    # First fire sets _last_url to "https://example.com/page1"
    handler1 = await _invoke_overlay_ready_handler(session, sm, current_url="https://example.com/page1")
    msg = OverlayReady(bundle_build_session="bs")
    await handler1(msg)

    # Start a recording
    await sm.start_recording(name="Nav Test")
    recording_id = sm._recordings_state.active_recording_id
    assert recording_id is not None

    # Now fire at a different URL
    handler2 = await _invoke_overlay_ready_handler(session, sm, current_url="https://example.com/page2")
    await handler2(msg)

    # A NavigationEntry should have been appended
    full_rec = sm._full_recordings.get(recording_id)
    nav_entries = [e for e in (full_rec.entries if full_rec else []) if isinstance(e, NavigationEntry)]
    assert len(nav_entries) >= 1, (
        f"Expected at least 1 NavigationEntry after URL change with active recording, "
        f"got entries: {full_rec.entries if full_rec else []}"
    )
    assert nav_entries[0].from_url == "https://example.com/page1"
    assert nav_entries[0].to_url == "https://example.com/page2"


@pytest.mark.anyio
async def test_nav_observation_no_entry_without_active_recording() -> None:
    """OverlayReady with new URL but no active recording: no NavigationEntry appended."""
    from frontprompt.bridge.messages import OverlayReady
    from frontprompt.show_session import ShowSession

    sm = StateManager(session_id="test-nav-no-rec")
    session = ShowSession(url="https://example.com", state_manager=sm)

    # Set up _last_url via first handler call
    handler1 = await _invoke_overlay_ready_handler(session, sm, current_url="https://example.com/page1")
    msg = OverlayReady(bundle_build_session="bs")
    await handler1(msg)

    # No recording active — URL changes but no entry should be appended
    handler2 = await _invoke_overlay_ready_handler(session, sm, current_url="https://example.com/page2")
    await handler2(msg)

    assert sm._full_recordings == {}, (
        "No NavigationEntry should be appended when no recording is active"
    )


@pytest.mark.anyio
async def test_last_url_updated_after_each_overlay_ready() -> None:
    """_last_url is updated after every OverlayReady, regardless of recording state."""
    from frontprompt.bridge.messages import OverlayReady
    from frontprompt.show_session import ShowSession

    sm = StateManager(session_id="test-nav-last-url")
    session = ShowSession(url="https://example.com", state_manager=sm)

    # _last_url starts at None
    assert session._last_url is None

    handler = await _invoke_overlay_ready_handler(session, sm, current_url="https://example.com/page1")
    msg = OverlayReady(bundle_build_session="bs")
    await handler(msg)

    # After first fire, _last_url should be updated
    assert session._last_url == "https://example.com/page1"
