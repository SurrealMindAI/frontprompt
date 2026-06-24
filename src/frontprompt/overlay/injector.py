"""OverlayInjector — installiert + verifiziert Overlay-Script in Main World.

Lifecycle:

    injector = OverlayInjector(browser, scaffold_script=...)
    await injector.install_init_script()    # MUST be before first navigate
    await browser.navigate(url)
    await injector.verify_mounted()         # polls DOM bis marker da

Vertrag mit dem ``scaffold_script``:

    1. **Idempotent**: prüft ob ``#__frontprompt_overlay_host__`` schon existiert
       und no-ops wenn ja (Playwright re-injectet auf jeder Navigation).
    2. **Setzt Ready-Flag**: ``window.__frontprompt_overlay_ready__ = true`` nach
       erfolgreichem Mount. ``false`` bei Exception im Mount-Code.
    3. **Erzeugt Marker**: Element mit ``id="__frontprompt_overlay_host__"`` im DOM.
    4. **Deferred Mount**: wenn ``document.body`` noch nicht existiert, register
       DOMContentLoaded-Listener (siehe adhoc-scaffold).

Design notes:
    - Anyio (``anyio.sleep``, ``anyio.fail_after``)
    - ``injector_id`` als ID-Term
    - Inject in Main World via ``page.add_init_script`` (Phase 1)
"""

from __future__ import annotations

import uuid
from typing import TYPE_CHECKING, Final

import anyio
import structlog

from frontprompt.overlay.errors import (
    OverlayAlreadyInstalledError,
    OverlayInstallationError,
    OverlayNotInstalledError,
    OverlayNotMountedError,
)

if TYPE_CHECKING:
    from frontprompt.browser import BrowserSessionManager

_LOG = structlog.get_logger(__name__)

DEFAULT_MARKER_ID: Final[str] = "__frontprompt_overlay_host__"
"""DOM-Element-ID die das Scaffold setzen MUSS für Verify-Detection."""

DEFAULT_READY_FLAG: Final[str] = "__frontprompt_overlay_ready__"
"""``window``-Property die das Scaffold auf ``true`` setzt nach Mount."""


class OverlayInjector:
    """Owns: install + verify lifecycle für genau ein Overlay-Scaffold.

    Nicht thread-safe; ein OverlayInjector pro Browser-Session-Manager.
    """

    def __init__(
        self,
        browser: BrowserSessionManager,
        *,
        scaffold_script: str,
        marker_id: str = DEFAULT_MARKER_ID,
        ready_flag: str = DEFAULT_READY_FLAG,
    ) -> None:
        """Initialisiere den Injector.

        Args:
            browser: Bereits gestartete (entered) BrowserSessionManager-Instance.
            scaffold_script: JavaScript-Source der das Overlay mountet. Muss
                den Marker mit ``id=marker_id`` erzeugen und ``window[ready_flag]``
                auf ``true`` setzen. Siehe Modul-Docstring für vollen Vertrag.
            marker_id: DOM-Element-ID die verify_mounted sucht. Default:
                ``__frontprompt_overlay_host__``.
            ready_flag: window-Property die das Scaffold setzt. Default:
                ``__frontprompt_overlay_ready__``.
        """
        self._browser = browser
        self._scaffold_script = scaffold_script
        self._marker_id = marker_id
        self._ready_flag = ready_flag
        self._injector_id = str(uuid.uuid4())
        self._log = _LOG.bind(injector_id=self._injector_id, marker_id=marker_id)
        self._installed = False

    @property
    def injector_id(self) -> str:
        """Stable per-instance UUID, used als logger-binding key."""
        return self._injector_id

    @property
    def marker_id(self) -> str:
        """DOM-ID die nach Mount im DOM-Tree existieren muss."""
        return self._marker_id

    @property
    def ready_flag(self) -> str:
        """window-Property die das Scaffold setzt."""
        return self._ready_flag

    @property
    def is_installed(self) -> bool:
        """``True`` wenn ``install_init_script()`` schon erfolgreich gelaufen ist."""
        return self._installed

    async def install_init_script(self) -> None:
        """Registriere das Scaffold-Script via ``page.add_init_script``.

        MUSS vor dem ersten ``browser.navigate()`` aufgerufen werden, sonst
        greift das Script erst beim *nächsten* document_load.

        Raises:
            OverlayAlreadyInstalledError: wenn bereits installed.
            OverlayInstallationError: wenn Playwright die Registrierung rejected.
        """
        if self._installed:
            raise OverlayAlreadyInstalledError(
                f"OverlayInjector {self._injector_id} ist bereits installed — "
                "doppelter install_init_script-Call ist ein Logik-Bug."
            )

        self._log.info(
            "overlay_injector.install_init_script.start",
            script_length=len(self._scaffold_script),
        )
        try:
            await self._browser.add_init_script(self._scaffold_script)
        except Exception as exc:
            self._log.exception(
                "overlay_injector.install_init_script.failed",
                error=str(exc),
            )
            raise OverlayInstallationError(
                f"add_init_script via browser fehlgeschlagen: {exc}",
                cause=exc,
            ) from exc
        self._installed = True
        self._log.info("overlay_injector.install_init_script.done")

    async def verify_mounted(
        self,
        *,
        timeout_seconds: float = 5.0,
        poll_interval_seconds: float = 0.05,
    ) -> None:
        """Pollt die Page bis ``#marker_id`` im DOM existiert + Ready-Flag true.

        Cancel-safe: bei outer Cancel (SIGINT) propagiert anyio.CancelledError
        ohne dass das Poll-Loop hängenbleibt.

        Args:
            timeout_seconds: Wartezeit bevor ``OverlayNotMountedError`` geworfen
                wird. Default: 5s.
            poll_interval_seconds: Polling-Intervall. Default: 50ms (responsiv
                ohne CPU-Spam).

        Raises:
            OverlayNotInstalledError: wenn ``install_init_script`` noch nicht
                aufgerufen wurde.
            OverlayNotMountedError: wenn Timeout erreicht ohne Marker.
            OverlayInstallationError: wenn Scaffold-Mount eine JS-Exception
                geworfen hat (Ready-Flag ist auf ``false``).
        """
        if not self._installed:
            raise OverlayNotInstalledError(
                "verify_mounted() ohne vorheriges install_init_script() aufgerufen — "
                "install muss VOR der ersten Navigation passieren."
            )

        log = self._log.bind(
            timeout_seconds=timeout_seconds,
            poll_interval_seconds=poll_interval_seconds,
        )
        log.info("overlay_injector.verify_mounted.start")

        polls = 0
        # Expressions: müssen JSON-serialisierbare Werte zurückgeben. `!!` cast
        # explizit zu bool damit JS-DOM-Element-Object nicht versucht wird zu
        # serialisieren (Playwright wirft sonst SerializationError).
        marker_expr = f"!!document.getElementById({self._marker_id!r})"
        ready_expr = f"window[{self._ready_flag!r}]"

        async def _poll_until_marker() -> None:
            nonlocal polls
            while True:
                polls += 1
                exists = await self._browser.evaluate(marker_expr)
                if exists:
                    return
                await anyio.sleep(poll_interval_seconds)

        try:
            with anyio.fail_after(timeout_seconds):
                await _poll_until_marker()
        except TimeoutError as exc:
            log.warning(
                "overlay_injector.verify_mounted.timeout",
                polls=polls,
            )
            raise OverlayNotMountedError(
                f"DOM-Marker '#{self._marker_id}' nach {timeout_seconds}s nicht im DOM gefunden ({polls} polls).",
                cause=exc,
            ) from exc

        # Marker is there. Check ready_flag — wenn explizit `false`, hat das
        # Scaffold während Mount eine Exception geworfen (Vertrag).
        ready_value = await self._browser.evaluate(ready_expr)
        if ready_value is False:
            log.error(
                "overlay_injector.verify_mounted.scaffold_threw",
                ready_value=ready_value,
            )
            raise OverlayInstallationError(
                f"Marker '#{self._marker_id}' existiert, aber Ready-Flag "
                f"'{self._ready_flag}' ist false — Scaffold hat während Mount "
                "eine Exception geworfen. Check browser console."
            )

        log.info(
            "overlay_injector.verify_mounted.done",
            polls=polls,
            ready_value=ready_value,
        )

    def __repr__(self) -> str:
        state = "installed" if self._installed else "not-installed"
        return f"OverlayInjector(injector_id={self._injector_id!r}, marker_id={self._marker_id!r}, state={state})"
