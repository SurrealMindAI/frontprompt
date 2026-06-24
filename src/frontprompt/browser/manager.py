"""BrowserSessionManager — headful Chromium-Lifecycle für Phase 1 (UI-Tool).

Ein BrowserSessionManager besitzt:
    - eine Playwright-Instance (via ``async_playwright()``)
    - einen Browser (Chromium, headful per default)
    - einen BrowserContext (kein persistent user_data_dir in Phase 1)
    - eine Page

Lifecycle als async-Context-Manager:

    async with BrowserSessionManager() as mgr:
        await mgr.navigate("https://example.com")
        await mgr.wait_until_closed()  # blockt bis User Tab schließt
    # browser.close() + Playwright.stop() im __aexit__

Logging:
    structlog Bound-Logger per ``browser_session_id`` — alle Lifecycle-
    Übergänge werden geloggt (``browser_session.launching``,
    ``browser_session.ready``, ``browser_session.navigate.{start,done}``,
    ``browser_session.closing``, ``browser_session.closed``).

Error-Handling:
    Keine raw playwright-Exception verlässt das Modul. Launch-Failures werden
    zu ``BrowserLaunchError``, Navigation-Failures zu ``NavigationError``,
    Operations-vor-Enter zu ``BrowserNotReadyError``.

Design notes:
    - Nutzt anyio (kein ``asyncio.create_task()``). Playwright's
      async_api läuft kompatibel im anyio-asyncio-Backend.
    - ``browser_session_id`` (nicht bare ``id``).
    - Phase 1 nutzt Playwright direkt; Scrapling ist Phase-2+ für
      Scraper-Workflows (Stealth, CF-Bypass).
"""

from __future__ import annotations

import uuid
from contextlib import AsyncExitStack
from types import TracebackType
from typing import TYPE_CHECKING, Any, Literal

import anyio
import structlog

from frontprompt.browser.errors import (
    BrowserLaunchError,
    BrowserNotReadyError,
    NavigationError,
    PageEvaluationError,
)

if TYPE_CHECKING:
    from playwright.async_api import Browser, BrowserContext, Page, Playwright


LoadState = Literal["load", "domcontentloaded", "networkidle"]

_LOG = structlog.get_logger(__name__)


class BrowserSessionManager:
    """Headful Chromium-Lifecycle — single browser, single context, single page.

    Phase 1 hat genau einen Tab pro Manager-Instance. Multi-Tab-Support kommt
    wenn Phase 2 mehrere PageSession-Aggregate parallel braucht.
    """

    def __init__(self, *, headless: bool = False) -> None:
        """Initialisiere BrowserSessionManager.

        Args:
            headless: ``False`` (default) = sichtbares Browser-Fenster. ``True``
                = headless mode (für CI-Tests). Phase-1-CLI nutzt always
                headless=False.
        """
        self._headless = headless
        self._browser_session_id = str(uuid.uuid4())
        self._log = _LOG.bind(browser_session_id=self._browser_session_id)
        self._exit_stack = AsyncExitStack()
        self._playwright: Playwright | None = None
        self._browser: Browser | None = None
        self._context: BrowserContext | None = None
        self._page: Page | None = None
        self._entered = False

    @property
    def browser_session_id(self) -> str:
        """Stable per-instance UUID, used als logger-binding key."""
        return self._browser_session_id

    @property
    def page(self) -> Page:
        """Returns the underlying playwright Page.

        Raises:
            BrowserNotReadyError: wenn vor ``__aenter__`` aufgerufen.
        """
        if self._page is None:
            raise BrowserNotReadyError("BrowserSessionManager nicht entered — call innerhalb `async with`.")
        return self._page

    async def __aenter__(self) -> BrowserSessionManager:
        """Spawne Playwright + Chromium + Context + Page.

        Bei Failure jeden Schritt rollback (Playwright-stop, partial-cleanup).
        Wrapped alle Exceptions in ``BrowserLaunchError``.
        """
        # Local import: playwright-import ist lazy weil import-time costly
        # (lädt Native-Library) und manche Test-Pfade ohne installation laufen
        from playwright.async_api import async_playwright

        self._log.info("browser_session.launching", headless=self._headless)

        try:
            self._playwright = await self._exit_stack.enter_async_context(async_playwright())
            # ``--disable-blink-features=AutomationControlled``: Chrome setzt sonst
            # ``navigator.webdriver = true`` (playwright-default). Manche pages
            # (Google, Cloudflare-challenges, ...) checken das und zeigen
            # captchas / extra-modals / blockieren content. Wir sind ein echter
            # user-tool, kein bot — flag entfernt das automation-signal.
            self._browser = await self._playwright.chromium.launch(
                headless=self._headless,
                args=["--disable-blink-features=AutomationControlled"],
            )
            # ``no_viewport=True``: Playwright's default ist viewport=1280x720
            # — die rendert sub-window-area und lässt rest des fensters leer.
            # Mit no_viewport managt Playwright das viewport NICHT, page rendert
            # auf voller window-fläche + folgt user-resize.
            self._context = await self._browser.new_context(no_viewport=True)
            self._page = await self._context.new_page()
            self._entered = True
            self._log.info("browser_session.ready")
            return self
        except Exception as exc:
            # Partial cleanup: alles was wir schon haben, sauber schließen
            self._log.exception("browser_session.launch_failed", error=str(exc))
            await self._exit_stack.aclose()
            raise BrowserLaunchError(
                f"Chromium-Start fehlgeschlagen: {exc}",
                cause=exc,
            ) from exc

    async def __aexit__(
        self,
        exc_type: type[BaseException] | None,
        exc_val: BaseException | None,
        exc_tb: TracebackType | None,
    ) -> None:
        """Cleanup: browser.close() + Playwright.stop().

        Wrapped in ``anyio.CancelScope(shield=True)`` damit Cleanup auch unter
        outer cancel (SIGINT) zu Ende läuft. Playwright-Errors beim Schließen
        werden nur geloggt, nicht propagiert (best-effort cleanup).
        """
        if not self._entered:
            # Wir sind in __aenter__ gestorben — exit_stack ist schon zu
            return

        self._log.info("browser_session.closing")
        with anyio.CancelScope(shield=True):
            if self._browser is not None:
                try:
                    await self._browser.close()
                except Exception as e:
                    self._log.warning("browser_session.close_browser_failed", error=str(e))
            try:
                await self._exit_stack.aclose()
            except Exception as e:
                self._log.warning("browser_session.close_playwright_failed", error=str(e))
        self._log.info("browser_session.closed")

    async def navigate(self, url: str) -> None:
        """Navigiere die Page zu ``url`` via ``page.goto()``.

        Args:
            url: Ziel-URL. Akzeptiert ``http://``, ``https://``, ``file://``,
                ``about:blank``, etc.

        Raises:
            BrowserNotReadyError: wenn vor ``__aenter__`` aufgerufen.
            NavigationError: wenn ``page.goto()`` failed (timeout, DNS, etc.).
        """
        if self._page is None:
            raise BrowserNotReadyError("BrowserSessionManager nicht entered — call innerhalb `async with`.")

        log = self._log.bind(url=url)
        log.info("browser_session.navigate.start")
        try:
            await self._page.goto(url)
            log.info("browser_session.navigate.done")
        except Exception as exc:
            log.exception("browser_session.navigate.failed", error=str(exc))
            raise NavigationError(
                f"Navigation zu {url!r} fehlgeschlagen: {exc}",
                cause=exc,
            ) from exc

    async def wait_until_closed(self) -> None:
        """Blockiere bis User die Page schließt (Tab-Close, ⌘W, Window-Close).

        Returnt sobald playwright's ``page.close``-Event feuert. Bei externem
        Cancel (SIGINT propagiert über anyio) raises ``anyio.get_cancelled_exc_class()``
        — das ist die normale anyio-Cancellation, kein Bug-Pfad.

        Raises:
            BrowserNotReadyError: wenn vor ``__aenter__`` aufgerufen.
        """
        if self._page is None:
            raise BrowserNotReadyError("BrowserSessionManager nicht entered — call innerhalb `async with`.")

        self._log.info("browser_session.wait_until_closed.start")
        # timeout=0 = no timeout, blocks indefinitely until close event
        await self._page.wait_for_event("close", timeout=0)
        self._log.info("browser_session.wait_until_closed.done")

    async def add_init_script(self, script: str) -> None:
        """Registriere ein Init-Script das bei JEDEM document_load in der Main World läuft.

        Wichtig — Race-Vermeidung:
            ``add_init_script`` muss **vor** dem ersten ``navigate()`` aufgerufen
            werden, damit das Script bei der initialen Navigation greift.
            Playwright queued Init-Scripts intern und re-injectet sie automatisch
            bei jeder neuen Navigation (auch Cross-Origin).

        Das Script läuft at ``document_start`` — vor jedem Page-Script, bevor
        ``<body>`` existiert. Code der mit DOM arbeitet muss auf ``DOMContentLoaded``
        deferren. Code im "Main World" Context (selber JS-Heap wie page-scripts),
        was für unser Overlay-Mount erwünscht ist (Shadow-DOM hosting, event-handlers).

        Args:
            script: JavaScript-Source als String. Idealerweise idempotent
                (re-execution auf navigation darf nicht doppel-mounten).

        Raises:
            BrowserNotReadyError: wenn vor ``__aenter__`` aufgerufen.
            BrowserError: wenn Playwright die Registrierung rejected.
        """
        if self._page is None:
            raise BrowserNotReadyError("BrowserSessionManager nicht entered — call innerhalb `async with`.")

        log = self._log.bind(script_length=len(script))
        log.info("browser_session.add_init_script.start")
        try:
            await self._page.add_init_script(script=script)
            log.info("browser_session.add_init_script.done")
        except Exception as exc:
            log.exception("browser_session.add_init_script.failed", error=str(exc))
            raise BrowserLaunchError(
                f"add_init_script fehlgeschlagen: {exc}",
                cause=exc,
            ) from exc

    async def evaluate(self, expression: str) -> Any:
        """Evaluiere eine JS-Expression in der Main World, gib JSON-serialisiertes Result zurück.

        Verwendung: Verifizierungs-Reads (z.B. ``"!!document.getElementById('x')"``,
        ``"window.__overlay_ready__"``). Nicht für Side-Effects gedacht.

        Args:
            expression: JavaScript-Expression als String. ``Page.evaluate`` von
                Playwright wrappt das automatisch in eine async function — also
                ``"() => 1+1"`` und ``"1+1"`` funktionieren beide.

        Returns:
            JSON-serialisierbares Result der Expression. ``None`` für ``undefined``.

        Raises:
            BrowserNotReadyError: wenn vor ``__aenter__`` aufgerufen.
            PageEvaluationError: wenn die Expression einen JS-Error wirft oder
                die Page währenddessen navigated/closed wird.
        """
        if self._page is None:
            raise BrowserNotReadyError("BrowserSessionManager nicht entered — call innerhalb `async with`.")

        try:
            result = await self._page.evaluate(expression)
        except Exception as exc:
            self._log.exception(
                "browser_session.evaluate.failed",
                expression_preview=expression[:80],
                error=str(exc),
            )
            raise PageEvaluationError(
                f"page.evaluate fehlgeschlagen ({expression[:80]!r}): {exc}",
                cause=exc,
            ) from exc
        return result

    async def wait_for_load_state(self, state: LoadState = "domcontentloaded") -> None:
        """Warte bis die Page den gegebenen Load-State erreicht hat.

        Args:
            state: Einer von ``"load"``, ``"domcontentloaded"``, ``"networkidle"``.
                Default: ``"domcontentloaded"`` (DOM ready, Sub-Resources noch ladend).

        Raises:
            BrowserNotReadyError: wenn vor ``__aenter__`` aufgerufen.
        """
        if self._page is None:
            raise BrowserNotReadyError("BrowserSessionManager nicht entered — call innerhalb `async with`.")

        log = self._log.bind(load_state=state)
        log.info("browser_session.wait_for_load_state.start")
        await self._page.wait_for_load_state(state)
        log.info("browser_session.wait_for_load_state.done")

    def __repr__(self) -> str:
        state = "ready" if self._entered else "not-entered"
        return f"BrowserSessionManager(browser_session_id={self._browser_session_id!r}, state={state})"


# Silence "unused" warnings for the imported Any (we may use it later)
_ = Any
