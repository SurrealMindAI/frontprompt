"""BridgeManager — typed bidirectional channel-owner zwischen Python + Overlay.

Two-way bridge (see ARCHITECTURE.md). Lifecycle:

    async with BrowserSessionManager() as browser:
        async with BridgeManager(browser) as bridge:           # MUST be before navigate
            bridge.on(OverlayReady, on_overlay_ready_handler)
            await OverlayInjector(browser, scaffold).install_init_script()
            await browser.navigate(url)
            await bridge.wait_until_ready()                    # waits for OverlayReady
            await bridge.send(Heartbeat(seq=1, ...))           # python → overlay

Window-namespace im Overlay:
    Playwright's expose_function erzeugt ``window.__fp`` (callable). Im
    overlay-bridge.svelte.ts werden zusätzliche properties direkt an die
    Function angehängt: ``window.__fp.dispatch``, ``window.__fp.version``.
    JS-Standard-Pattern (functions sind objects).
"""

from __future__ import annotations

import time
from collections.abc import Awaitable, Callable
from typing import TYPE_CHECKING, Any, Generic, TypeVar

import anyio
import structlog
from pydantic import BaseModel, TypeAdapter, ValidationError

from frontprompt.bridge.errors import (
    BridgeError,
    BridgeNotReadyError,
    OverlayValidationError,
)
from frontprompt.bridge.messages import (
    Heartbeat,
    HeartbeatAck,
    InboundMessage,
    OutboundMessage,
    OverlayReady,
)

if TYPE_CHECKING:
    from frontprompt.browser import BrowserSessionManager


_LOG = structlog.get_logger(__name__)

#: Name unter dem die expose_function im window-namespace landet.
#: Direct callable: window.__fp(msg). bridge.svelte.ts hängt zusätzliche
#: properties an: window.__fp.dispatch, window.__fp.version.
WINDOW_NAMESPACE: str = "__fp"


#: Type-adapter für inbound message json-serialization (Python → Overlay)
_INBOUND_ADAPTER: TypeAdapter[InboundMessage] = TypeAdapter(InboundMessage)

#: Type-adapter für outbound message validation (Overlay → Python)
_OUTBOUND_ADAPTER: TypeAdapter[OutboundMessage] = TypeAdapter(OutboundMessage)


T = TypeVar("T", bound=BaseModel)
Handler = Callable[[Any], Awaitable[None] | None]


class BridgeManager:
    """Owns: expose_function registration, outbound message routing, send-API.

    Single instance pro :class:`BrowserSessionManager`. MUSS vor dem ersten
    ``navigate()`` instanziiert + entered werden, sonst greift die
    expose_function-registrierung nicht für die initiale Page-Load.
    """

    def __init__(
        self,
        browser: BrowserSessionManager,
        *,
        bundle_build_session: str | None = None,
    ) -> None:
        """Initialisiere BridgeManager.

        Args:
            browser: Bereits gestarteter BrowserSessionManager (entered).
            bundle_build_session: Build-session-id des installed overlay-bundles
                (aus ``frontend/dist/build-manifest.json``). Used für drift-detection
                gegen den ``OverlayReady.bundle_build_session`` field.
        """
        self._browser = browser
        self._expected_build_session = bundle_build_session
        self._log = _LOG.bind(window_namespace=WINDOW_NAMESPACE)
        self._handlers: dict[type, Handler] = {}
        self._ready_event = anyio.Event()
        self._overlay_ready: OverlayReady | None = None
        self._entered = False
        self._task_group: Any | None = None  # anyio.abc.TaskGroup when set via set_task_group()

    @property
    def is_ready(self) -> bool:
        """True nachdem das Overlay ``OverlayReady`` gesendet hat."""
        return self._overlay_ready is not None

    @property
    def overlay_ready_message(self) -> OverlayReady | None:
        """Die ``OverlayReady``-message wenn empfangen, sonst ``None``."""
        return self._overlay_ready

    def on(self, message_type: type[T], handler: Callable[[T], Awaitable[None] | None]) -> None:
        """Register handler für eine spezifische outbound message-type.

        Args:
            message_type: Concrete Pydantic class (z.B. ``OverlayReady``, ``HeartbeatAck``).
            handler: async oder sync callable, takes message instance.
        """
        self._handlers[message_type] = handler

    def set_task_group(self, tg: Any) -> None:
        """Inject an anyio TaskGroup for handler routing via tg.start_soon().

        When set, _on_overlay_send routes handler coroutines via tg.start_soon()
        instead of direct await inside the Playwright CDP callback. This prevents
        the cancellation-scope hazard of awaiting inside the CDP callback.

        Args:
            tg: An anyio TaskGroup (or any object with a start_soon() method for testing).
                Pass None to revert to direct-await fallback.
        """
        self._task_group = tg

    async def __aenter__(self) -> BridgeManager:
        """Register ``expose_function`` callback unter ``window.__fp``.

        MUSS vor dem ersten ``page.goto()`` aufgerufen werden, sonst greift die
        binding-registrierung erst auf der nächsten navigation.

        Raises:
            BridgeError: wenn ``expose_function`` failed.
        """
        page = self._browser.page  # raises BrowserNotReadyError wenn browser nicht entered
        self._log.info("bridge.aenter.start")
        try:
            await page.expose_function(WINDOW_NAMESPACE, self._on_overlay_send)
        except Exception as exc:
            self._log.exception("bridge.aenter.expose_function.failed", error=str(exc))
            raise BridgeError(
                f"page.expose_function({WINDOW_NAMESPACE!r}) failed: {exc}",
                cause=exc,
            ) from exc
        self._entered = True
        self._log.info("bridge.aenter.done")
        return self

    async def __aexit__(self, *_args: object) -> None:
        """No-op cleanup. Playwright cleans up expose_function on page close."""
        self._log.info("bridge.aexit")

    async def _on_overlay_send(self, raw: dict[str, object]) -> dict[str, object] | None:
        """Called by Playwright wenn overlay ``window.__fp(msg)`` ruft.

        Validiert via Pydantic, routet zu registered handler, returnt
        json-serializable response (oder None für fire-and-forget).
        """
        try:
            message = _OUTBOUND_ADAPTER.validate_python(raw)
        except ValidationError as exc:
            self._log.error(
                "bridge.outbound.validation_failed",
                errors=exc.errors(),
                raw_preview=str(raw)[:200],
            )
            return {"error": "validation_failed", "details": exc.errors()}

        kind = type(message).__name__
        self._log.info("bridge.outbound.received", kind=kind)

        # Spezial-handling für OverlayReady (lifecycle signal)
        if isinstance(message, OverlayReady):
            self._overlay_ready = message
            self._ready_event.set()
            if self._expected_build_session and message.bundle_build_session != self._expected_build_session:
                self._log.warning(
                    "bridge.outbound.build_session_mismatch",
                    expected=self._expected_build_session,
                    actual=message.bundle_build_session,
                )

        handler = self._handlers.get(type(message))
        if handler is not None:
            if self._task_group is not None:
                # route via supervised anyio task — prevents cancellation-scope
                # hazard when handler coroutine runs inside Playwright CDP callback.
                # tg.start_soon() schedules the handler as a supervised task outside
                # the CDP callback's implicit cancel-scope.
                self._task_group.start_soon(handler, message)
            else:
                # Fallback: direct await (backward compat for tests without injected tg).
                # Emits a warning to surface accidental use in production paths.
                self._log.warning(
                    "bridge.outbound.handler_direct_await_fallback",
                    kind=kind,
                    reason="no task group injected — call set_task_group(tg) in ShowSession.run()",
                )
                try:
                    result = handler(message)
                    if hasattr(result, "__await__"):
                        await result  # type: ignore[misc]
                except Exception as exc:
                    self._log.exception(
                        "bridge.outbound.handler_failed",
                        kind=kind,
                        error=str(exc),
                    )
                    return {"error": "handler_failed", "kind": kind}

        return None

    async def send(self, message: InboundMessage) -> None:
        """Send a typed inbound message to the overlay via ``page.evaluate``.

        Marshalls via Pydantic JSON, dispatches via
        ``window.__fp.dispatch(parsedJson)`` im overlay.

        Raises:
            BridgeNotReadyError: wenn vor ``__aenter__`` aufgerufen.
            OverlayValidationError: wenn message-shape gegen Pydantic-Schema verstößt
                (catches dev-bugs vor wire-send).
        """
        if not self._entered:
            raise BridgeNotReadyError("BridgeManager nicht entered — call innerhalb `async with`.")

        # Pydantic-validate locally before wire-send (defense in depth gegen dev-bugs)
        try:
            json_payload = _INBOUND_ADAPTER.dump_json(message).decode("utf-8")
        except ValidationError as exc:
            raise OverlayValidationError(
                f"Inbound message failed local Pydantic validation: {exc}",
                cause=exc,
            ) from exc

        kind = type(message).__name__
        self._log.info("bridge.inbound.send.start", kind=kind)
        # JSON payload als string-literal — Playwright marshals + Overlay dispatches.
        # Single argument-passing: page.evaluate('(p) => window.__fp.dispatch(p)', payload_dict)
        await self._browser.page.evaluate(
            "(payload) => window.__fp.dispatch(payload)",
            _INBOUND_ADAPTER.dump_python(message, mode="json"),
        )
        self._log.info("bridge.inbound.send.done", kind=kind, json_length=len(json_payload))

    async def wait_until_ready(self, *, timeout_seconds: float = 10.0) -> OverlayReady:
        """Blockiere bis ``OverlayReady`` empfangen, oder timeout.

        Raises:
            BridgeError: wenn timeout erreicht.
        """
        try:
            with anyio.fail_after(timeout_seconds):
                await self._ready_event.wait()
        except TimeoutError as exc:
            raise BridgeError(
                f"OverlayReady nicht innerhalb {timeout_seconds}s empfangen — "
                "overlay bundle didn't mount? Check browser console.",
                cause=exc,
            ) from exc
        assert self._overlay_ready is not None
        return self._overlay_ready

    def __repr__(self) -> str:
        state = "ready" if self.is_ready else ("entered" if self._entered else "not-entered")
        return f"BridgeManager(state={state})"


__all__ = ["WINDOW_NAMESPACE", "BridgeManager"]

# Unused suppression for Generic + HeartbeatAck (re-exported via __init__ path):
_ = (Generic, HeartbeatAck, Heartbeat, time)
