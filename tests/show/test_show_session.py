"""ShowSession unit tests — cli.py extraction + task-group routing.

Tests verify:
  1. ShowSession importability
  2. Constructor stores url + creates StateManager
  3. Handler registration count matches bridge surface (17 handler types)
  4. BridgeManager routes via tg.start_soon
  10. BridgeManager falls back to direct-await when no task group set
"""

from __future__ import annotations

from typing import Any
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

# ---------------------------------------------------------------------------
# Test 1 — ShowSession is importable
# ---------------------------------------------------------------------------


def test_show_session_is_importable() -> None:
    """Importing ShowSession from frontprompt.show_session does not raise."""
    from frontprompt.show_session import ShowSession  # noqa: F401


# ---------------------------------------------------------------------------
# Test 2 — Constructor stores url and creates StateManager
# ---------------------------------------------------------------------------


def test_show_session_stores_url() -> None:
    """ShowSession(url=...) has .url; state_manager is built later from the
    session_lifecycle SSoT (None until run() enters the lifecycle)."""
    from frontprompt.show_session import ShowSession

    s = ShowSession(url="https://example.com")
    assert s.url == "https://example.com"
    # No fabricated session id at construction — manager is built inside run()
    # once the authoritative session_id is available (SSoT).
    assert s.state_manager is None


def test_show_session_accepts_injected_state_manager() -> None:
    """ShowSession accepts optional state_manager for test injection."""
    from frontprompt.show_session import ShowSession
    from frontprompt.state import StateManager

    sm = StateManager(session_id="test-session")
    s = ShowSession(url="https://example.com", state_manager=sm)
    assert s.state_manager is sm


# ---------------------------------------------------------------------------
# Test 3 — Handler registration count
# ---------------------------------------------------------------------------


def test_show_session_registers_handlers_count() -> None:
    """ShowSession registers exactly 29 handler types (one per bridge message type)."""
    from frontprompt.show_session import ShowSession

    s = ShowSession(url="https://example.com")
    # Count: OverlayReady, PanelToggleRequested, PanelResizeRequested,
    # HideAllPanelsRequested, InspectorActivateRequested, InspectorCanceledRequested,
    # InspectorPickMadeRequested, PickSelectedRequested, PickCommentUpdatedRequested,
    # PickDeletedRequested, RelationCreatedRequested, RelationDeletedRequested,
    # RelationUpdatedRequested, RegionCreatedRequested, RegionDeletedRequested,
    # RegionUpdatedRequested, RegionSelectedRequested
    # + 5 recording handlers (recorder sub-plan 04):
    # RecordingStartRequested, RecordingStopRequested, RecordingRenameRequested,
    # RecordingSelectedRequested, RecordedEventCapturedRequested
    # + 3 assertion-authoring handlers (replay sub-plan 04):
    # AssertionAddedToRecordingRequested, AssertionDeletedRequested, AssertionUpdatedRequested
    # + 3 voice-over settings handlers (voice-over sub-plan 05):
    # SetMicDeviceRequested, SetTranscriptionBackendRequested, TriggerModelDownloadRequested
    # + 1 transcription model selection handler (voiceover-models sub-plan 06):
    # SetTranscriptionModelRequested
    # = 29 handler registrations
    expected_count = 29
    assert s.handler_count() == expected_count, (
        f"Expected {expected_count} handlers, got {s.handler_count()}. "
        "Did you add/remove a bridge message type without updating this test?"
    )


# ---------------------------------------------------------------------------
# Test 4 — BridgeManager routes via task group
# ---------------------------------------------------------------------------


@pytest.mark.anyio
async def test_bridge_manager_handler_routed_via_task_group_not_direct_await() -> None:
    """BridgeManager._on_overlay_send routes via tg.start_soon when task group injected."""
    from frontprompt.bridge.manager import BridgeManager
    from frontprompt.bridge.messages import PanelToggleRequested

    # Spy task group: records start_soon calls
    start_soon_calls: list[Any] = []

    class SpyTaskGroup:
        def start_soon(self, coro_fn: Any, *args: Any, **kwargs: Any) -> None:
            start_soon_calls.append((coro_fn, args, kwargs))

    spy_tg = SpyTaskGroup()

    # Minimal browser mock
    mock_page = AsyncMock()
    mock_page.expose_function = AsyncMock()
    mock_browser = MagicMock()
    mock_browser.page = mock_page

    bridge = BridgeManager(mock_browser)
    bridge._entered = True  # skip __aenter__ registration for isolation

    handler_called_directly = False

    async def _handler(msg: PanelToggleRequested) -> None:
        nonlocal handler_called_directly
        handler_called_directly = True

    bridge.on(PanelToggleRequested, _handler)
    bridge.set_task_group(spy_tg)  # type: ignore[arg-type]

    raw = {"kind": "panel_toggle_requested", "schema_version": "0.6.0", "panel_id": "left"}
    await bridge._on_overlay_send(raw)

    assert len(start_soon_calls) == 1, f"Expected start_soon called once, got {len(start_soon_calls)}"
    assert handler_called_directly is False, "Handler must NOT be directly awaited when task group is set"


# ---------------------------------------------------------------------------
# Test 10 — BridgeManager fallback when no task group set
# ---------------------------------------------------------------------------


@pytest.mark.anyio
async def test_bridge_manager_no_task_group_falls_back_to_direct_await() -> None:
    """BridgeManager with no task group falls back to direct-await; warning log emitted."""
    from frontprompt.bridge.manager import BridgeManager
    from frontprompt.bridge.messages import PanelToggleRequested

    mock_page = AsyncMock()
    mock_browser = MagicMock()
    mock_browser.page = mock_page

    bridge = BridgeManager(mock_browser)
    bridge._entered = True

    handler_called = False

    async def _handler(msg: PanelToggleRequested) -> None:
        nonlocal handler_called
        handler_called = True

    bridge.on(PanelToggleRequested, _handler)
    # NOTE: no set_task_group() call — fallback path

    raw = {"kind": "panel_toggle_requested", "schema_version": "0.6.0", "panel_id": "left"}

    with patch.object(bridge._log, "warning") as mock_warn:
        await bridge._on_overlay_send(raw)

    assert handler_called is True, "Handler must fire via direct-await fallback"
    # Check warning was logged
    log_events = [str(call) for call in mock_warn.call_args_list]
    assert any("handler_direct_await_fallback" in ev for ev in log_events), (
        f"Expected 'handler_direct_await_fallback' warning log, got: {log_events}"
    )


# ---------------------------------------------------------------------------
# heartbeat backoff on failure
# ---------------------------------------------------------------------------


# ---------------------------------------------------------------------------
# Task 7 — StateManager session_id sourced from session_lifecycle SSoT
# ---------------------------------------------------------------------------


def test_build_state_manager_sources_session_id_from_metadata() -> None:
    """_build_state_manager must take its session_id from the SessionMetadata
    (the SSoT) — never fabricate one — and inject a disk-backed persistence.

    This is the seam: given a SessionMetadata yielded by session_lifecycle,
    the StateManager it builds carries exactly that session_id and a real
    SqlitePersistence (from make_persistence()), not the InMemory stub.
    """
    from frontprompt.ipc.session import SessionMetadata
    from frontprompt.show_session import ShowSession
    from frontprompt.state import StateManager
    from frontprompt.state.persistence import SqlitePersistence

    s = ShowSession(url="https://example.com")
    meta = SessionMetadata.for_current_process(session_id="ssot-session-xyz", url="https://example.com")

    manager = s._build_state_manager(meta)

    assert isinstance(manager, StateManager)
    assert manager.session_id == "ssot-session-xyz", (
        f"StateManager.session_id must equal SessionMetadata.session_id (SSoT) — got {manager.session_id!r}"
    )
    # Real persistence, not the InMemory stub (make_persistence default).
    assert isinstance(manager.persistence, SqlitePersistence)


def test_no_default_session_placeholder_in_show_session_source() -> None:
    """The Task-6 placeholder literal must be gone — no fabricated id in src."""
    from pathlib import Path

    src = (Path(__file__).parent.parent.parent / "src" / "frontprompt" / "show_session.py").read_text(encoding="utf-8")
    assert "default-session" not in src, (
        "Task-6 placeholder 'default-session' must be removed — "
        "StateManager session_id must come from session_lifecycle (SSoT)."
    )


@pytest.mark.anyio
async def test_run_sources_state_manager_session_id_from_lifecycle() -> None:
    """Driving ShowSession.run() (browser fully mocked) constructs StateManager
    with the session_id from the active session_lifecycle metadata, and the
    metadata file exists on disk for that id while the run is in flight.

    Seam-test: no real chromium — all browser/bridge/overlay bits are stubbed.
    """
    import anyio

    from frontprompt.ipc import session as session_mod
    from frontprompt.ipc.session import SessionMetadata
    from frontprompt.show_session import ShowSession

    captured: dict[str, object] = {}

    real_lifecycle = session_mod.session_lifecycle

    def _spy_lifecycle(*, url: str) -> _SpyLifecycle:
        return _SpyLifecycle(real_lifecycle(url=url), captured)

    class _SpyLifecycle:
        """Wraps the real session_lifecycle CM, recording the yielded id + file state."""

        def __init__(self, cm: Any, sink: dict[str, object]) -> None:
            self._cm = cm
            self._sink = sink

        async def __aenter__(self) -> SessionMetadata:
            meta: SessionMetadata = await self._cm.__aenter__()
            from frontprompt.ipc.paths import metadata_path_for

            self._sink["session_id"] = meta.session_id
            self._sink["metadata_exists"] = metadata_path_for(meta.session_id).exists()
            return meta

        async def __aexit__(self, *exc: object) -> object:
            return await self._cm.__aexit__(*exc)

    s = ShowSession(url="https://example.com")

    # Stub the heavy lifecycle bits so run() never opens chromium.
    with (
        patch("frontprompt.show_session.session_lifecycle", _spy_lifecycle),
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
        mock_manifest.return_value = MagicMock(build_session="bs", schema_version="0.7.0")

        # Browser context manager: page.expose_function async, wait_until_closed
        # returns immediately so run() unwinds.
        browser = AsyncMock()
        browser.page = AsyncMock()
        browser.wait_until_closed = AsyncMock()
        browser.navigate = AsyncMock()
        mock_browser_cls.return_value.__aenter__ = AsyncMock(return_value=browser)
        mock_browser_cls.return_value.__aexit__ = AsyncMock(return_value=None)

        bridge = AsyncMock()
        bridge.set_task_group = MagicMock()
        bridge.on = MagicMock()
        bridge.wait_until_ready = AsyncMock(return_value=MagicMock(bundle_build_session="bs", schema_version="0.7.0"))
        mock_bridge_cls.return_value.__aenter__ = AsyncMock(return_value=bridge)
        mock_bridge_cls.return_value.__aexit__ = AsyncMock(return_value=None)

        injector = AsyncMock()
        injector.install_init_script = AsyncMock()
        injector.verify_mounted = AsyncMock()
        mock_injector_cls.return_value = injector

        with anyio.fail_after(5):
            await s.run()

    assert s.state_manager is not None
    assert captured["session_id"] is not None
    assert s.state_manager.session_id == captured["session_id"], (
        "StateManager session_id must equal the active session_lifecycle id (SSoT)"
    )
    assert captured["metadata_exists"] is True, (
        "session_lifecycle must have written session.json for the run's id (ShowSession enters the lifecycle, the SSoT)"
    )


# ---------------------------------------------------------------------------
# Task 1 — initial-state seed carries current_session_id
# ---------------------------------------------------------------------------


@pytest.mark.anyio
async def test_initial_state_seed_carries_current_session_id() -> None:
    """The dict returned by the initial-state provider (_provide_initial_state) must
    contain key 'current_session_id' equal to the session's session_id — the same id
    injected into StateManager (sourced from session_lifecycle SSoT).

    Seam-test: no real chromium — browser/bridge/overlay are stubbed. We capture the
    callable registered via page.expose_function and invoke it directly to read the seed.
    """
    import anyio

    from frontprompt.ipc import session as session_mod
    from frontprompt.show_session import ShowSession

    # Intercept page.expose_function to grab the _provide_initial_state callable
    expose_call_args: list[tuple[str, object]] = []

    class _CapturingPage(AsyncMock):
        async def expose_function(self, name: str, fn: object) -> None:  # type: ignore[override]
            expose_call_args.append((name, fn))

    real_lifecycle = session_mod.session_lifecycle

    def _spy_lifecycle(*, url: str) -> Any:
        return real_lifecycle(url=url)

    s = ShowSession(url="https://example.com")

    with (
        patch("frontprompt.show_session.session_lifecycle", _spy_lifecycle),
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
        mock_manifest.return_value = MagicMock(build_session="bs", schema_version="0.7.0")

        capturing_page = _CapturingPage()
        capturing_page.navigate = AsyncMock()

        browser = AsyncMock()
        browser.page = capturing_page
        browser.wait_until_closed = AsyncMock()
        browser.navigate = AsyncMock()
        mock_browser_cls.return_value.__aenter__ = AsyncMock(return_value=browser)
        mock_browser_cls.return_value.__aexit__ = AsyncMock(return_value=None)

        bridge = AsyncMock()
        bridge.set_task_group = MagicMock()
        bridge.on = MagicMock()
        bridge.wait_until_ready = AsyncMock(return_value=MagicMock(bundle_build_session="bs", schema_version="0.7.0"))
        mock_bridge_cls.return_value.__aenter__ = AsyncMock(return_value=bridge)
        mock_bridge_cls.return_value.__aexit__ = AsyncMock(return_value=None)

        injector = AsyncMock()
        injector.install_init_script = AsyncMock()
        injector.verify_mounted = AsyncMock()
        mock_injector_cls.return_value = injector

        with anyio.fail_after(5):
            await s.run()

    # Locate the __fp_internal_state_getter provider
    getter_entries = [(name, fn) for name, fn in expose_call_args if name == "__fp_internal_state_getter"]
    assert len(getter_entries) == 1, (
        f"Expected expose_function to be called once with '__fp_internal_state_getter', got: {expose_call_args}"
    )
    _name, seed_provider = getter_entries[0]

    # Invoke the provider to get the seed dict
    seed = await seed_provider()  # type: ignore[operator]

    assert "current_session_id" in seed, f"Seed dict must contain 'current_session_id'. Got keys: {list(seed.keys())}"
    assert seed["current_session_id"] == s.state_manager.session_id, (  # type: ignore[union-attr]
        f"current_session_id in seed ({seed['current_session_id']!r}) must equal "
        f"StateManager.session_id ({s.state_manager.session_id!r})"  # type: ignore[union-attr]
    )


@pytest.mark.anyio
async def test_heartbeat_logs_warning_only_on_first_failure() -> None:
    """_heartbeat_sender must emit warning on first failure only, not on every failure."""
    import anyio
    import structlog.testing

    from frontprompt.show_session import ShowSession

    s = ShowSession(url="https://example.com")

    # A bridge mock whose send always fails
    class _FailBridge:
        async def send(self, msg: object) -> None:
            raise RuntimeError("bridge closed")

    bridge = _FailBridge()

    # Run 3 iterations by patching anyio.sleep to count iterations and cancel after 3
    iteration = 0

    async def _counting_sleep(secs: float) -> None:
        nonlocal iteration
        if secs == 5.0:
            # normal inter-heartbeat sleep — start of a new iteration
            iteration += 1
            if iteration >= 3:
                raise anyio.get_cancelled_exc_class()()
        # For backoff sleeps (< 5s) we return immediately

    with structlog.testing.capture_logs() as logs:
        with patch("frontprompt.show_session.anyio.sleep", _counting_sleep):
            try:
                await s._heartbeat_sender(bridge)  # type: ignore[arg-type]
            except BaseException:
                pass  # cancelled after 3 iterations

    warning_events = [e for e in logs if e.get("log_level") == "warning"]
    assert len(warning_events) == 1, (
        f"Expected exactly 1 warning (first failure), got {len(warning_events)}: {warning_events}"
    )
    assert "first_failure" in warning_events[0].get("event", ""), (
        f"Expected 'first_failure' in warning event, got: {warning_events[0]}"
    )


@pytest.mark.anyio
async def test_heartbeat_logs_recovery_after_success() -> None:
    """_heartbeat_sender must log recovery when send succeeds after failures."""
    import anyio
    import structlog.testing

    from frontprompt.show_session import ShowSession

    s = ShowSession(url="https://example.com")

    call_count = 0

    class _RecoveringBridge:
        async def send(self, msg: object) -> None:
            nonlocal call_count
            call_count += 1
            if call_count <= 2:
                raise RuntimeError("bridge closed")
            # 3rd call succeeds

    bridge = _RecoveringBridge()

    iteration = 0

    async def _counting_sleep(secs: float) -> None:
        nonlocal iteration
        if secs == 5.0:
            iteration += 1
            if iteration >= 4:
                raise anyio.get_cancelled_exc_class()()

    with structlog.testing.capture_logs() as logs:
        with patch("frontprompt.show_session.anyio.sleep", _counting_sleep):
            try:
                await s._heartbeat_sender(bridge)  # type: ignore[arg-type]
            except BaseException:
                pass

    warning_events = [e for e in logs if e.get("log_level") == "warning"]
    recovery_events = [e for e in logs if "recovered" in str(e.get("event", ""))]
    assert len(warning_events) == 1, f"Expected 1 warning (first failure), got: {warning_events}"
    assert len(recovery_events) >= 1, f"Expected at least 1 recovery log, got: {logs}"
