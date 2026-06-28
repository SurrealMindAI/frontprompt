"""BridgeManager coverage tests — error paths and branch coverage.

Covers:
- _on_overlay_send: Pydantic ValidationError path
- _on_overlay_send: task_group routing branch
- _on_overlay_send: direct-await fallback exception
- _on_overlay_send: build_session mismatch warning
- send: BridgeNotReadyError before __aenter__
- wait_until_ready: timeout (BridgeError)
"""

from __future__ import annotations

from typing import Any
from unittest.mock import AsyncMock, MagicMock

import anyio
import pytest

from frontprompt.bridge.errors import BridgeError, BridgeNotReadyError
from frontprompt.bridge.manager import BridgeManager
from frontprompt.bridge.messages import HeartbeatAck, OverlayReady


class _FakeBrowser:
    """Minimal BrowserSessionManager stub."""

    def __init__(self) -> None:
        self._page = _FakePage()

    @property
    def page(self) -> _FakePage:
        return self._page


class _FakePage:
    """Minimal Playwright Page stub for unit tests."""

    async def expose_function(self, name: str, fn: Any) -> None:
        pass

    async def evaluate(self, expr: str, arg: Any = None) -> Any:
        return None


def _make_bridge() -> BridgeManager:
    return BridgeManager(_FakeBrowser())


# ── send before entered (BridgeNotReadyError) ─────────────────────────────────


@pytest.mark.anyio
async def test_send_before_aenter_raises_bridge_not_ready() -> None:
    """send() before __aenter__ raises BridgeNotReadyError."""
    bridge = _make_bridge()
    from frontprompt.bridge.messages import Heartbeat

    with pytest.raises(BridgeNotReadyError, match="nicht entered"):
        await bridge.send(Heartbeat(seq=1, server_send_time_ns=0))


# ── wait_until_ready timeout ──────────────────────────────────────────────────


@pytest.mark.anyio
async def test_wait_until_ready_timeout_raises_bridge_error() -> None:
    """wait_until_ready() raises BridgeError on timeout."""
    bridge = _make_bridge()
    # Enter the bridge (registers expose_function) but never send OverlayReady
    async with bridge:
        with pytest.raises(BridgeError, match="OverlayReady"):
            await bridge.wait_until_ready(timeout_seconds=0.01)


# ── _on_overlay_send: validation failure ──────────────────────────────────────


@pytest.mark.anyio
async def test_on_overlay_send_invalid_message_returns_error() -> None:
    """_on_overlay_send with an unrecognized payload returns validation_failed."""
    bridge = _make_bridge()
    async with bridge:
        result = await bridge._on_overlay_send({"kind": "DoesNotExist", "garbage": True})
    assert result is not None
    assert result["error"] == "validation_failed"


# ── _on_overlay_send: OverlayReady + build_session mismatch ──────────────────


@pytest.mark.anyio
async def test_on_overlay_send_overlay_ready_sets_ready_event() -> None:
    """_on_overlay_send with OverlayReady sets _ready_event."""
    bridge = _make_bridge()
    async with bridge:
        await bridge._on_overlay_send(
            {
                "kind": "overlay_ready",
                "overlay_version": "1.0.0",
                "schema_version": "1.0.0",
                "bundle_build_session": "bld-abc",
            }
        )
        assert bridge.is_ready


@pytest.mark.anyio
async def test_on_overlay_send_overlay_ready_build_session_mismatch() -> None:
    """_on_overlay_send logs warning when bundle_build_session doesn't match expected."""
    bridge = BridgeManager(_FakeBrowser(), bundle_build_session="expected-session")
    async with bridge:
        await bridge._on_overlay_send(
            {
                "kind": "overlay_ready",
                "overlay_version": "1.0.0",
                "schema_version": "1.0.0",
                "bundle_build_session": "different-session",
            }
        )
    assert bridge.overlay_ready_message is not None


# ── _on_overlay_send: handler via task_group ──────────────────────────────────


@pytest.mark.anyio
async def test_on_overlay_send_routes_handler_via_task_group() -> None:
    """When set_task_group is called, handlers are dispatched via tg.start_soon()."""
    bridge = _make_bridge()
    received: list[Any] = []

    async def on_ready(msg: OverlayReady) -> None:
        received.append(msg)

    bridge.on(OverlayReady, on_ready)

    # Inject a fake task group that captures start_soon calls
    fake_tg = MagicMock()
    fake_tg.start_soon = MagicMock()
    bridge.set_task_group(fake_tg)

    async with bridge:
        await bridge._on_overlay_send(
            {
                "kind": "overlay_ready",
                "overlay_version": "1.0.0",
                "schema_version": "1.0.0",
                "bundle_build_session": "bld",
            }
        )
    # The handler must have been dispatched via task_group.start_soon
    assert fake_tg.start_soon.called


# ── _on_overlay_send: direct-await fallback ───────────────────────────────────


@pytest.mark.anyio
async def test_on_overlay_send_direct_await_fallback_when_no_task_group() -> None:
    """Without injected task group, handler is called via direct await (fallback)."""
    bridge = _make_bridge()
    received: list[Any] = []

    async def on_ready(msg: OverlayReady) -> None:
        received.append(msg)

    bridge.on(OverlayReady, on_ready)
    # No set_task_group — uses direct-await fallback

    async with bridge:
        await bridge._on_overlay_send(
            {
                "kind": "overlay_ready",
                "overlay_version": "1.0.0",
                "schema_version": "1.0.0",
                "bundle_build_session": "bld",
            }
        )
    assert len(received) == 1
    assert isinstance(received[0], OverlayReady)


@pytest.mark.anyio
async def test_on_overlay_send_direct_await_handler_exception_returns_handler_failed() -> None:
    """Handler exception in direct-await fallback returns handler_failed dict."""
    bridge = _make_bridge()

    async def failing_handler(msg: OverlayReady) -> None:
        raise RuntimeError("handler boom")

    bridge.on(OverlayReady, failing_handler)

    async with bridge:
        result = await bridge._on_overlay_send(
            {
                "kind": "overlay_ready",
                "overlay_version": "1.0.0",
                "schema_version": "1.0.0",
                "bundle_build_session": "bld",
            }
        )
    assert result is not None
    assert result["error"] == "handler_failed"


@pytest.mark.anyio
async def test_on_overlay_send_sync_handler_is_called() -> None:
    """sync (non-async) handler in direct-await fallback is called without awaiting."""
    bridge = _make_bridge()
    called: list[Any] = []

    def sync_handler(msg: OverlayReady) -> None:
        called.append(msg)

    bridge.on(OverlayReady, sync_handler)

    async with bridge:
        await bridge._on_overlay_send(
            {
                "kind": "overlay_ready",
                "overlay_version": "1.0.0",
                "schema_version": "1.0.0",
                "bundle_build_session": "bld",
            }
        )
    assert len(called) == 1


# ── __aenter__ BridgeError when expose_function raises ───────────────────────


@pytest.mark.anyio
async def test_aenter_raises_bridge_error_when_expose_function_fails() -> None:
    """__aenter__ wraps expose_function exceptions in BridgeError (lines 142-144)."""

    class _FailingPage:
        async def expose_function(self, name: str, fn: Any) -> None:
            raise RuntimeError("expose_function rejected")

        async def evaluate(self, expr: str, arg: Any = None) -> Any:
            return None

    class _FailingBrowser:
        @property
        def page(self) -> _FailingPage:
            return _FailingPage()

    bridge = BridgeManager(_FailingBrowser())  # type: ignore[arg-type]
    with pytest.raises(BridgeError, match="expose_function"):
        async with bridge:
            pass


# ── send() success path (lines 231-247) ──────────────────────────────────────


@pytest.mark.anyio
async def test_send_success_path_calls_page_evaluate() -> None:
    """send() after __aenter__ calls page.evaluate and logs success (lines 231-247)."""
    evaluate_calls: list[tuple[str, Any]] = []

    class _TrackingPage:
        async def expose_function(self, name: str, fn: Any) -> None:
            pass

        async def evaluate(self, expr: str, arg: Any = None) -> Any:
            evaluate_calls.append((expr, arg))
            return None

    class _TrackingBrowser:
        @property
        def page(self) -> _TrackingPage:
            return _TrackingPage()

    bridge = BridgeManager(_TrackingBrowser())  # type: ignore[arg-type]
    from frontprompt.bridge.messages import Heartbeat

    async with bridge:
        await bridge.send(Heartbeat(seq=1, server_send_time_ns=0))

    assert len(evaluate_calls) == 1
    expr, arg = evaluate_calls[0]
    assert "dispatch" in expr
    assert arg is not None


# ── wait_until_ready success path (lines 264-265) ────────────────────────────


@pytest.mark.anyio
async def test_wait_until_ready_success_returns_overlay_ready() -> None:
    """wait_until_ready returns OverlayReady once the event fires (lines 264-265)."""
    bridge = _make_bridge()
    async with bridge:
        # Inject OverlayReady message before waiting
        await bridge._on_overlay_send(
            {
                "kind": "overlay_ready",
                "overlay_version": "1.0.0",
                "schema_version": "1.0.0",
                "bundle_build_session": "bld-test",
            }
        )
        ready_msg = await bridge.wait_until_ready(timeout_seconds=1.0)

    assert isinstance(ready_msg, OverlayReady)
    assert ready_msg.bundle_build_session == "bld-test"
