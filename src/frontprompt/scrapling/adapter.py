"""ScraplingAdapter — typisierter Async-Wrapper für die drei Scrapling-Substrate.

Kapselt ``AsyncDynamicSession``, ``AsyncStealthySession`` und
``AsyncFetcher`` hinter einem stabilen Interface. Keine rohe
playwright-Exception verlässt dieses Modul — alle Fehler werden in
``ScraplingNavigateError``-Subklassen gewrapped.

Naming-Konvention:
    ``dns_domain`` (nie bare ``domain``),
    ``page_session_id`` (nie bare ``id`` / ``session``),
    ``scrapling_session`` (nie bare ``session``).

Scrapling ist das einzige Browser-Substrate.
Kein ``asyncio.create_task()`` — anyio ``task_group.start_soon()``
    wenn concurrent tasks gebraucht werden.
Single-writer: Dieser Adapter ist KEIN Aggregat-Root und enthält keine
    Ownership-Guards. Ownership liegt in ``PageSession.assert_owner()``
    — der Caller ist dafür verantwortlich, den Guard vor dem
    ``adapter.navigate()``-Call aufzurufen.
"""

from __future__ import annotations

import hashlib
from typing import TYPE_CHECKING

from pydantic import BaseModel, ConfigDict

if TYPE_CHECKING:
    from pathlib import Path

    from frontprompt.scrapling.substrate_router import SubstrateHint, SubstrateRouter
    from frontprompt.scrapling.user_data_dir import UserDataDirManager
    from frontprompt.types import PageSessionId


# ---- Typed Exception Hierarchy ----------------------------------------------


class ScraplingNavigateError(Exception):
    """Base-Klasse für alle Scrapling-Navigation-Fehler.

    MCP-tools-Bundle codiert gegen diese Hierarchie — keine
    raw playwright.TimeoutError oder OSError verlässt den Adapter.

    Alle Subklassen nehmen einen menschenlesbaren ``message``-Parameter
    und optionale ``cause`` (original Exception) für Audit-Log-Ketten.
    """

    def __init__(self, message: str, cause: BaseException | None = None) -> None:
        super().__init__(message)
        self.cause = cause


class BrowserLaunchError(ScraplingNavigateError):
    """Chromium konnte nicht starten.

    Typische Ursachen:
    - playwright-Binary fehlt (``playwright install chromium`` vergessen)
    - Chromium SingletonLock-Race (zwei PageSessions mit demselben user_data_dir)
    - OSError bei Disk-full oder fehlenden Permissions
    """


class PageLoadTimeoutError(ScraplingNavigateError):
    """Page-Load überschritt Timeout.

    Typische Ursachen:
    - URL nicht erreichbar (Netzwerk, DNS, unreachable file:// URI)
    - Server antwortet nicht innerhalb des Scrapling-Timeouts
    - Chromium-Crash während Navigation (selten)
    """


class SubstrateBlockedError(ScraplingNavigateError):
    """Cloudflare/Turnstile-Bypass schlug fehl.

    Tritt auf wenn ``AsyncStealthySession`` nach Ablauf der Turnstile-Solve-
    Zeit keinen erfolgreichen Bypass erreicht hat. Signaliert F-4
    (Substrate-Detection-Failure) an den Caller.

    Caller-Empfehlung: Audit-Event emittieren + PageSession schließen.
    """


# ---- NavigateResult ---------------------------------------------------------


class NavigateResult(BaseModel):
    """Ergebnis einer erfolgreichen ``ScraplingAdapter.navigate()``-Operation.

    Alle Felder sind aus der Scrapling-Response extrahiert. ``status_code``
    kann None sein wenn Scrapling keine HTTP-Statusinformation liefert
    (z.B. bei ``file://``-URIs über AsyncDynamicSession).

    ``dom_snapshot_hash`` ist ein SHA-256-Hex-Digest des HTML-Bodys nach
    vollständigem Page-Load. Wird als primitiver Drift-Indikator
    verwendet (spätere Drift-Gate-Implementierung baut darauf auf).
    """

    model_config = ConfigDict(frozen=True)

    url: str
    """Die tatsächliche URL nach Navigation (nach Redirect)."""

    status_code: int | None
    """HTTP-Statuscode der Antwort. None bei file://-URIs oder wenn
    Scrapling keine HTTP-Information zurückgibt."""

    dom_snapshot_hash: str = ""
    """SHA-256-Hex-Digest des HTML-Bodys. Leerstring wenn kein Body
    verfügbar (Fehler-Recovery-Path, sollte in der Praxis nicht auftreten
    wenn NavigateResult zurückgegeben wird).

    Default "" erlaubt Test-Mocks NavigateResult(url=..., status_code=200)
    ohne dom_snapshot_hash zu spezifizieren. Production-Code
    (_extract_result()) setzt es immer."""


# ---- ScraplingAdapter -------------------------------------------------------


class ScraplingAdapter:
    """Typisierter Async-Wrapper für die drei Scrapling-Substrate.

    Eine ScraplingAdapter-Instanz wird pro Daemon-Boot erzeugt und von
    allen PageSession-Aggregaten geteilt (stateless — kein Mutable-State
    pro PageSession in dieser Klasse). Die scrapling_session-Instanz wird
    per ``navigate()``-Call erzeugt und zerstört (kein Pool-Sharing zwischen
    PageSessions — Nursery-per-PageSession).

    Single-writer: Ownership-Guards liegen in ``PageSession``, nicht hier.
    """

    def __init__(
        self,
        user_data_dir_manager: UserDataDirManager,
        substrate_router: SubstrateRouter,
        *,
        navigate_timeout_ms: int = 30_000,
    ) -> None:
        """Initialisiere den ScraplingAdapter.

        Args:
            user_data_dir_manager: Manager für per-(dns_domain, page_session_id)
                user_data_dir-Isolation (chromium user_data_dir thread-safety mitigation).
            substrate_router: Router der das Scrapling-Substrate für eine
                (dns_domain, substrate_hint)-Kombination wählt.
            navigate_timeout_ms: Scrapling-Timeout für Navigation in Millisekunden.
                Default: 30 000ms (30s). Für AsyncStealthySession auf CF-Tier-3
                kann 60 000ms - 180 000ms nötig sein (189s für Turnstile-Solve
                in einem Substrate-Probe-Lauf).
        """
        self._user_data_dir_manager = user_data_dir_manager
        self._substrate_router = substrate_router
        self._navigate_timeout_ms = navigate_timeout_ms

    async def navigate(
        self,
        url: str,
        dns_domain: str,
        page_session_id: PageSessionId,
        substrate_hint: SubstrateHint | None = None,
    ) -> NavigateResult:
        """Navigiere zu ``url`` via dem gewählten Scrapling-Substrate.

        Holt den ``user_data_dir``-Pfad von ``UserDataDirManager.allocate()``,
        wählt das Substrate via ``SubstrateRouter``, öffnet eine
        ``scrapling_session``, navigiert, extrahiert ``NavigateResult``.

        Die ``scrapling_session`` wird für die Dauer dieses Calls geöffnet
        und geschlossen — kein Session-Sharing zwischen PageSessions
        (Nursery-per-PageSession: Cross-Session-Browser-Pool ist
        nicht implementiert).

        Args:
            url: Ziel-URL. Akzeptiert ``https://``, ``http://``, ``file://``.
            dns_domain: DNS-Hostname des Targets. Z.B. ``"google.com"``.
                Wird für ``UserDataDirManager.allocate()`` und
                ``SubstrateRouter.choose()`` verwendet.
            page_session_id: ID der aufrufenden PageSession.
                Wird für den isolierten ``user_data_dir``-Pfad verwendet.
            substrate_hint: Optionaler Substrate-Wunsch. ``None`` → Router-Default.

        Returns:
            NavigateResult mit URL, status_code, dom_snapshot_hash.

        Raises:
            BrowserLaunchError: Chromium konnte nicht starten (OSError, Binary-
                fehlt, SingletonLock).
            PageLoadTimeoutError: Timeout oder nicht-erreichbare URL.
            SubstrateBlockedError: Cloudflare-Bypass gescheitert
                (stealthy-Substrate-spezifisch).
        """
        substrate_name = self._substrate_router.choose(
            dns_domain=dns_domain,
            substrate_hint=substrate_hint,
        )

        user_data_dir_path: Path = self._user_data_dir_manager.allocate(
            dns_domain=dns_domain,
            page_session_id=page_session_id,
        )

        return await self._navigate_with_substrate(
            url=url,
            substrate_name=substrate_name,
            user_data_dir_path=user_data_dir_path,
        )

    async def _navigate_with_substrate(
        self,
        url: str,
        substrate_name: str,
        user_data_dir_path: Path,
    ) -> NavigateResult:
        """Interne Dispatch-Methode — wählt die Scrapling-Klasse und führt navigate durch."""
        from frontprompt.scrapling.substrate_router import (
            SUBSTRATE_FETCHER,
            SUBSTRATE_STEALTHY,
        )

        if substrate_name == SUBSTRATE_STEALTHY:
            return await self._navigate_stealthy(url=url, user_data_dir_path=user_data_dir_path)
        elif substrate_name == SUBSTRATE_FETCHER:
            return await self._navigate_fetcher(url=url)
        else:
            # Default: DYNAMIC
            return await self._navigate_dynamic(url=url, user_data_dir_path=user_data_dir_path)

    async def _navigate_dynamic(self, url: str, user_data_dir_path: Path) -> NavigateResult:
        """Navigation via AsyncDynamicSession (Playwright-drunter, Standard-Substrate)."""
        try:
            from scrapling.fetchers import AsyncDynamicSession
        except ImportError as exc:
            raise BrowserLaunchError(
                f"scrapling nicht installiert oder AsyncDynamicSession fehlt: {exc}",
                cause=exc,
            ) from exc

        try:
            async with AsyncDynamicSession(
                headless=True,
                user_data_dir=str(user_data_dir_path),
                timeout=self._navigate_timeout_ms,
            ) as scrapling_session:
                response = await scrapling_session.fetch(url, timeout=self._navigate_timeout_ms)
                return self._extract_result(url=url, response=response)
        except BrowserLaunchError:
            raise
        except Exception as exc:
            raise self._classify_exception(exc, url=url) from exc

    async def _navigate_stealthy(self, url: str, user_data_dir_path: Path) -> NavigateResult:
        """Navigation via AsyncStealthySession (Patchright + CDP-Patches, CF-Bypass)."""
        try:
            from scrapling.fetchers import AsyncStealthySession
        except ImportError as exc:
            raise BrowserLaunchError(
                f"scrapling nicht installiert oder AsyncStealthySession fehlt: {exc}",
                cause=exc,
            ) from exc

        try:
            # AsyncStealthySession (scrapling 0.4.8) akzeptiert NUR die Felder
            # aus PlaywrightSession + StealthSession-TypedDict:
            # headless, solve_cloudflare, block_webrtc, hide_canvas, allow_webgl, user_data_dir, timeout.
            # `humanize` und `os_randomize` sind patchright-Optionen die scrapling NICHT
            # exponiert — würden msgspec ValidationError "Object contains unknown field(s)" werfen.
            async with AsyncStealthySession(
                headless=True,
                solve_cloudflare=True,
                block_webrtc=True,
                hide_canvas=True,
                user_data_dir=str(user_data_dir_path),
                timeout=self._navigate_timeout_ms,
            ) as scrapling_session:
                response = await scrapling_session.fetch(url, timeout=self._navigate_timeout_ms)
                return self._extract_result(url=url, response=response)
        except BrowserLaunchError:
            raise
        except Exception as exc:
            raise self._classify_exception(exc, url=url) from exc

    async def _navigate_fetcher(self, url: str) -> NavigateResult:
        """Navigation via AsyncFetcher (curl-cffi-drunter, kein Chromium).

        AsyncFetcher benötigt kein user_data_dir (kein Browser-Context).
        AsyncFetcher in scrapling 0.4.8 ist eine REINE Classmethod-API
        (kein instance constructor benötigt).
        AsyncFetcher.fetch() existiert NICHT — die korrekte Methode ist
        AsyncFetcher.get(url) (oder .post / .put / .delete) als classmethod.
        """
        try:
            from scrapling.fetchers import AsyncFetcher
        except ImportError as exc:
            raise BrowserLaunchError(
                f"scrapling nicht installiert oder AsyncFetcher fehlt: {exc}",
                cause=exc,
            ) from exc

        try:
            response = await AsyncFetcher.get(url)
            return self._extract_result(url=url, response=response)
        except BrowserLaunchError:
            raise
        except Exception as exc:
            raise self._classify_exception(exc, url=url) from exc

    def _extract_result(self, url: str, response: object) -> NavigateResult:
        """Extrahiere NavigateResult aus der Scrapling-Response.

        Scrapling's Response-API ist nicht strikt typisiert (kein py.typed).
        Wir greifen defensiv auf Attribute zu.
        """
        status_code: int | None = getattr(response, "status", None)

        # body ist bytes in der scrapling Response-Klasse
        raw_body: object = getattr(response, "body", None) or b""
        if isinstance(raw_body, (bytes, bytearray)):
            body_str = raw_body.decode("utf-8", errors="replace")
        else:
            body_str = str(raw_body)

        dom_snapshot_hash = hashlib.sha256(body_str.encode("utf-8")).hexdigest()

        return NavigateResult(
            url=url,
            status_code=status_code,
            dom_snapshot_hash=dom_snapshot_hash,
        )

    def _classify_exception(self, exc: BaseException, url: str) -> ScraplingNavigateError:
        """Mappe raw Scrapling/playwright-Exception auf typisierte Subklasse.

        Mapping-Logik:
        - OSError / ValueError mit Keyword "SingletonLock" / "executable" / "binary"
          → BrowserLaunchError
        - playwright.errors.TimeoutError / TimeoutError → PageLoadTimeoutError
        - Cloudflare-Erkennungsmarker im Exception-String → SubstrateBlockedError
        - Alles andere → PageLoadTimeoutError (sicherer Default für MCP-tools-Contract)
        """
        exc_type = type(exc).__name__
        exc_msg = str(exc).lower()

        # Browser-Launch-Fehler
        if isinstance(exc, OSError) or any(
            kw in exc_msg for kw in ("executable doesn't exist", "singleton", "singletonlock", "profile is locked")
        ):
            return BrowserLaunchError(
                f"Browser-Start fehlgeschlagen bei {url!r}: {exc}",
                cause=exc,
            )

        # Cloudflare-Block
        if any(kw in exc_msg for kw in ("cloudflare", "turnstile", "just a moment", "cf-mitigated")):
            return SubstrateBlockedError(
                f"Cloudflare-Bypass fehlgeschlagen bei {url!r}: {exc}",
                cause=exc,
            )

        # Timeout + alle anderen Netzwerk-/Playwright-Fehler → PageLoadTimeoutError
        return PageLoadTimeoutError(
            f"Navigation zu {url!r} fehlgeschlagen ({exc_type}): {exc}",
            cause=exc,
        )
