# Phase-2: Two-BC nursery code, dormant since the architecture reset (see ARCHITECTURE.md).
"""PageSession — Aggregate Root der Programmatic-Executor-BC.

Single-Writer-Invariante: Nur der Task, dessen ID in
``_owner_task_id`` hinterlegt ist, darf dieses Aggregat mutieren.
Jede Mutations-Methode MUSS als erste Zeile
``self.assert_owner(current_task_id)`` aufrufen.

Lifecycle: Caller verwendet ``async with PageSession(...) as ps:`` —
``__aenter__`` gibt ``self`` zurück, ``navigate()`` allokiert den user_data_dir
lazily beim ersten Aufruf, ``__aexit__`` gibt ihn frei
(triggert LRU-Cleanup via UserDataDirManager.release()).

dns_domain-Extraktion: ``urllib.parse.urlparse(url).hostname`` — gibt bei
``file://``-URIs ``None`` zurück, Sentinel ``"_LOCAL"`` wird verwendet.
"""

from __future__ import annotations

from pathlib import Path
from typing import TYPE_CHECKING
from urllib.parse import urlparse

from pydantic import BaseModel, ConfigDict, PrivateAttr

from frontprompt.scrapling.adapter import NavigateResult
from frontprompt.scrapling.substrate_router import SubstrateHint
from frontprompt.types import PageSessionId, TaskId

if TYPE_CHECKING:
    from frontprompt.scrapling.adapter import ScraplingAdapter
    from frontprompt.scrapling.substrate_router import SubstrateRouter
    from frontprompt.scrapling.user_data_dir import UserDataDirManager

_LOCAL_DNS_DOMAIN = "_LOCAL"


def _extract_dns_domain(url: str) -> str:
    """Extrahiert den DNS-Hostname aus einer URL.

    Gibt ``_LOCAL`` zurück wenn kein Hostname vorhanden ist (z.B. ``file://``-URIs).
    """
    hostname = urlparse(url).hostname
    return hostname if hostname is not None else _LOCAL_DNS_DOMAIN


class PageSession(BaseModel):
    """Aggregate Root: eine Browser-Tab-Session in der Programmatic-Executor-BC.

    Lebenszyklus: ``async with PageSession(...) as ps: await ps.navigate(url)``.
    Alle Mutationen laufen ausschließlich im Single-Writer-Task dieser Session.

    Konstruktion: PageSession(...) mit drei injected Dependencies.
    Die Dependencies sind PrivateAttrs — nicht serialisiert, nicht im JSON-Schema.
    """

    model_config = ConfigDict(frozen=False, arbitrary_types_allowed=True)

    page_session_id: PageSessionId
    """Stabile ULID-Identity dieser Session. Unveränderlich nach Konstruktion.

    Naming-Konvention: Feld heißt ``page_session_id``, nicht bare ``id``.
    """

    # ---- Framework-interne PrivateAttrs (nicht serialisiert) -----------------

    _owner_task_id: TaskId | None = PrivateAttr(default=None)
    """anyio-Task-ID des Single-Writers. Wird vom Nursery-Spawn gesetzt.

    ``None`` bis der besitzende Task gestartet wird. Unveränderlich danach.
    """

    _user_data_dir_manager: UserDataDirManager = PrivateAttr()
    """Allokiert und gibt user_data_dirs frei (LRU)."""

    _scrapling_adapter: ScraplingAdapter = PrivateAttr()
    """Typisierter Wrapper um die drei Scrapling-Substrate."""

    _substrate_router: SubstrateRouter = PrivateAttr()
    """Wählt das Scrapling-Substrate pro navigate()-Call."""

    _allocated_user_data_dir: Path | None = PrivateAttr(default=None)
    """Pfad des allokierten user_data_dirs — gesetzt beim ersten navigate(), cleared in __aexit__."""

    _current_dns_domain: str | None = PrivateAttr(default=None)
    """DNS-Domain des letzten allocate()-Calls — benötigt in __aexit__ für release()."""

    def __init__(
        self,
        *,
        page_session_id: PageSessionId,
        user_data_dir_manager: UserDataDirManager,
        scrapling_adapter: ScraplingAdapter,
        substrate_router: SubstrateRouter,
    ) -> None:
        super().__init__(page_session_id=page_session_id)
        self._user_data_dir_manager = user_data_dir_manager
        self._scrapling_adapter = scrapling_adapter
        self._substrate_router = substrate_router

    # ---- Backward-kompatibler Owner-Guard (aus daemon-skeleton, unverändert) --

    def assert_owner(self, current_task_id: TaskId) -> None:
        """Wirft ``PermissionError`` wenn ``current_task_id`` nicht der Owner ist.

        Jede Mutations-Methode MUSS ``self.assert_owner(current_task_id)`` als
        erste Zeile aufrufen.

        Raises:
            PermissionError: wenn ``_owner_task_id`` nicht gesetzt ist oder
                nicht mit ``current_task_id`` übereinstimmt.
        """
        if self._owner_task_id is None:
            raise PermissionError(
                f"PageSession {self.page_session_id}: kein Owner-Task gesetzt — "
                "assert_owner() vor Nursery-Spawn aufgerufen?"
            )
        if self._owner_task_id != current_task_id:
            raise PermissionError(
                f"PageSession {self.page_session_id}: Owner-Task-Mismatch — "
                f"erwartet {self._owner_task_id!r}, got {current_task_id!r}"
            )

    # ---- Lifecycle -----------------------------------------------------------

    async def __aenter__(self) -> PageSession:
        """Initialisiert den Context — Allocation geschieht lazily in navigate()."""
        return self

    async def __aexit__(
        self,
        exc_type: type[BaseException] | None,
        exc_val: BaseException | None,
        exc_tb: object,
    ) -> None:
        """Gibt den user_data_dir frei (triggert LRU-Cleanup).

        Wird auch bei Exceptions aufgerufen — LRU-Cleanup ist immer gewollt.
        UserDataDirManager.release() ist synchron by design.
        """
        if self._current_dns_domain is not None and self._allocated_user_data_dir is not None:
            self._user_data_dir_manager.release(self._current_dns_domain, self.page_session_id)
            self._allocated_user_data_dir = None
            self._current_dns_domain = None

    # ---- Mutations-Methoden --------------------------------------------------

    async def navigate(
        self,
        url: str,
        substrate_hint: SubstrateHint | None = None,
        current_task_id: TaskId | None = None,
    ) -> NavigateResult:
        """Navigiert den Browser zu ``url`` und gibt ``NavigateResult`` zurück.

        Single-writer: ``assert_owner()`` ist die erste Zeile — kein Code darf
        davor ausgeführt werden.

        Args:
            url: Ziel-URL. Muss ein HTTP/HTTPS-Schema haben für echte Navigation.
                ``file://``-URIs sind für Tests erlaubt.
            substrate_hint: Optionaler Substrate-Override (``"dynamic"``,
                ``"stealthy"``, ``"fetcher"``). ``None`` → SubstrateRouter wählt
                (Default: ``"dynamic"``).
            current_task_id: Task-ID des Aufrufers. Wenn ``None``, wird
                ``_owner_task_id`` verwendet (kompatibel mit Nursery-Pattern wo
                der Owner sich selbst aufruft).

        Returns:
            NavigateResult mit gesetztem ``url``-Feld und ``status_code``.

        Raises:
            PermissionError: wenn ``current_task_id`` nicht der Owner ist
                (single-writer).
            BrowserLaunchError: wenn Chromium nicht starten konnte.
            PageLoadTimeoutError: wenn Page-Load das Timeout überschritt.
            SubstrateBlockedError: wenn Cloudflare/Turnstile-Bypass fehlschlug.
        """
        # Single-writer: assert_owner() als ERSTE Zeile — kein Code davor.
        effective_task_id = current_task_id if current_task_id is not None else self._owner_task_id
        if effective_task_id is None:
            raise PermissionError(
                f"PageSession {self.page_session_id}: kein current_task_id angegeben und kein _owner_task_id gesetzt"
            )
        self.assert_owner(effective_task_id)

        dns_domain = _extract_dns_domain(url)

        # Lazy-Allocation: user_data_dir beim ersten navigate()-Call allokieren.
        # allocate() ist synchron — kein await nötig.
        if self._allocated_user_data_dir is None:
            self._allocated_user_data_dir = self._user_data_dir_manager.allocate(dns_domain, self.page_session_id)
            self._current_dns_domain = dns_domain

        # SubstrateRouter.choose() ist keyword-only by design.
        self._substrate_router.choose(
            dns_domain=dns_domain,
            substrate_hint=substrate_hint,
        )

        # Delegate vollständig an ScraplingAdapter.
        # raise-through: ScraplingNavigateError-Subklassen werden nicht gewrapped.
        return await self._scrapling_adapter.navigate(
            url=url,
            dns_domain=dns_domain,
            page_session_id=self.page_session_id,
            substrate_hint=substrate_hint,
        )
