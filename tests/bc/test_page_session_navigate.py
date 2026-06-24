"""PageSession.navigate() — anyio Integration-Tests.

Testet:
- navigate() gibt NavigateResult mit gesetztem url-Feld zurück
- assert_owner() wird als erste Aktion in navigate() aufgerufen
- navigate() wirft PermissionError bei falschem Task (assert_owner-Path)
- __aenter__ ruft UserDataDirManager.allocate() auf
- __aexit__ ruft UserDataDirManager.release() auf (LRU-Trigger)
- navigate() wirft PageLoadTimeoutError (typed ScraplingNavigateError-Subklasse) bei unreachable URI
- navigate() propagiert BrowserLaunchError typed (kein Wrapping in weitere Schicht)
- navigate() verwendet substrate_hint wenn angegeben
- navigate() wählt "dynamic" als Default-Substrate ohne hint

Alle Mocks verwenden unittest.mock.AsyncMock / MagicMock.
anyio-Backend: asyncio (via conftest.py anyio_backend fixture).
Playwright-Binary NICHT benötigt — ScraplingAdapter ist vollständig gemockt.
"""

from __future__ import annotations

from pathlib import Path
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from frontprompt.bc.programmatic_executor.aggregates.page_session import PageSession
from frontprompt.scrapling.adapter import (
    BrowserLaunchError,
    NavigateResult,
    PageLoadTimeoutError,
    ScraplingAdapter,
)
from frontprompt.scrapling.substrate_router import SubstrateRouter
from frontprompt.scrapling.user_data_dir import UserDataDirManager
from frontprompt.types import PageSessionId, TaskId

_OWNER = TaskId("task-owner-sp04")
_INTRUDER = TaskId("task-intruder-sp04")
_PS_ID = PageSessionId("ps-sp04-001")
_FAKE_DIR = Path("/tmp/fake-user-data/nowsecure.nl/ps-sp04-001")


def _make_page_session(
    udm: UserDataDirManager | None = None,
    adapter: ScraplingAdapter | None = None,
    router: SubstrateRouter | None = None,
) -> PageSession:
    """Hilfs-Factory: PageSession mit Mocks, Owner gesetzt."""
    ps = PageSession(
        page_session_id=_PS_ID,
        user_data_dir_manager=udm or MagicMock(spec=UserDataDirManager),
        scrapling_adapter=adapter or MagicMock(spec=ScraplingAdapter),
        substrate_router=router or MagicMock(spec=SubstrateRouter),
    )
    ps._owner_task_id = _OWNER
    return ps


# ---------------------------------------------------------------------------
# Test 1 — navigate() gibt NavigateResult mit url-Feld zurück
# ---------------------------------------------------------------------------


@pytest.mark.anyio
async def test_navigate_returns_navigate_result_with_url() -> None:
    """navigate() gibt NavigateResult zurück, url-Feld entspricht navigierter URL."""
    target_url = "https://example.com/"
    expected_result = NavigateResult(url=target_url, status_code=200)

    adapter = AsyncMock(spec=ScraplingAdapter)
    adapter.navigate.return_value = expected_result

    router = MagicMock(spec=SubstrateRouter)
    router.choose.return_value = "dynamic"

    udm = MagicMock(spec=UserDataDirManager)
    udm.allocate.return_value = _FAKE_DIR

    ps = _make_page_session(udm=udm, adapter=adapter, router=router)

    async with ps as ctx:
        result = await ctx.navigate(target_url)

    assert result.url == target_url
    assert result.status_code == 200


# ---------------------------------------------------------------------------
# Test 2 — navigate() ruft assert_owner() als erste Aktion auf (Mock + verify)
# ---------------------------------------------------------------------------


@pytest.mark.anyio
async def test_navigate_calls_assert_owner_first() -> None:
    """navigate() ruft assert_owner() als allererste Zeile auf (single-writer-Invariante)."""
    call_order: list[str] = []

    adapter = AsyncMock(spec=ScraplingAdapter)

    async def _spy_navigate(*args: object, **kwargs: object) -> NavigateResult:
        call_order.append("adapter.navigate")
        return NavigateResult(url="https://example.com/", status_code=200)

    adapter.navigate.side_effect = _spy_navigate

    router = MagicMock(spec=SubstrateRouter)

    def _spy_choose(*args: object, **kwargs: object) -> str:
        call_order.append("router.choose")
        return "dynamic"

    router.choose.side_effect = _spy_choose

    udm = MagicMock(spec=UserDataDirManager)
    udm.allocate.return_value = _FAKE_DIR

    ps = _make_page_session(udm=udm, adapter=adapter, router=router)

    original_assert_owner = ps.assert_owner

    def _spy_assert_owner(current: TaskId) -> None:
        call_order.append("assert_owner")
        original_assert_owner(current)

    # Pydantic rejects __setattr__ for non-field names — patch via unittest.mock.patch.object
    with patch.object(type(ps), "assert_owner", wraps=None, side_effect=_spy_assert_owner):
        async with ps as ctx:
            await ctx.navigate("https://example.com/", current_task_id=_OWNER)

    assert call_order[0] == "assert_owner", f"assert_owner() muss erste Aktion sein, aber Reihenfolge war: {call_order}"


# ---------------------------------------------------------------------------
# Test 3 — navigate() wirft PermissionError bei falschem Task
# ---------------------------------------------------------------------------


@pytest.mark.anyio
async def test_navigate_raises_when_called_by_wrong_task() -> None:
    """navigate() wirft PermissionError wenn current_task_id != _owner_task_id."""
    udm = MagicMock(spec=UserDataDirManager)
    udm.allocate.return_value = _FAKE_DIR

    ps = _make_page_session(udm=udm)

    async with ps as ctx:
        with pytest.raises(PermissionError, match="Owner-Task-Mismatch"):
            await ctx.navigate("https://example.com/", current_task_id=_INTRUDER)


# ---------------------------------------------------------------------------
# Test 4 — __aenter__ + navigate() rufen allocate() auf
# ---------------------------------------------------------------------------


@pytest.mark.anyio
async def test_navigate_allocates_user_data_dir_on_aenter() -> None:
    """navigate() ruft UserDataDirManager.allocate(dns_domain, page_session_id) auf."""
    udm = MagicMock(spec=UserDataDirManager)
    udm.allocate.return_value = _FAKE_DIR

    adapter = AsyncMock(spec=ScraplingAdapter)
    adapter.navigate.return_value = NavigateResult(url="https://nowsecure.nl/", status_code=200)

    router = MagicMock(spec=SubstrateRouter)
    router.choose.return_value = "dynamic"

    ps = _make_page_session(udm=udm, adapter=adapter, router=router)

    async with ps as ctx:
        await ctx.navigate("https://nowsecure.nl/")

    udm.allocate.assert_called_once_with("nowsecure.nl", _PS_ID)


# ---------------------------------------------------------------------------
# Test 5 — __aexit__ ruft release() auf (LRU-Trigger)
# ---------------------------------------------------------------------------


@pytest.mark.anyio
async def test_navigate_releases_user_data_dir_on_aexit_triggers_lru() -> None:
    """__aexit__ ruft UserDataDirManager.release(dns_domain, page_session_id) auf."""
    udm = MagicMock(spec=UserDataDirManager)
    udm.allocate.return_value = _FAKE_DIR

    adapter = AsyncMock(spec=ScraplingAdapter)
    adapter.navigate.return_value = NavigateResult(url="https://nowsecure.nl/", status_code=200)

    router = MagicMock(spec=SubstrateRouter)
    router.choose.return_value = "dynamic"

    ps = _make_page_session(udm=udm, adapter=adapter, router=router)

    async with ps as ctx:
        await ctx.navigate("https://nowsecure.nl/")

    udm.release.assert_called_once_with("nowsecure.nl", _PS_ID)


# ---------------------------------------------------------------------------
# Test 6 — navigate() wirft PageLoadTimeoutError (typed) bei unreachable URI
# ---------------------------------------------------------------------------


@pytest.mark.anyio
async def test_navigate_raises_typed_PageLoadTimeoutError_on_unreachable_uri() -> None:
    """navigate() propagiert PageLoadTimeoutError (ScraplingNavigateError-Subklasse) unverändert."""
    adapter = AsyncMock(spec=ScraplingAdapter)
    adapter.navigate.side_effect = PageLoadTimeoutError("page load timed out")

    udm = MagicMock(spec=UserDataDirManager)
    udm.allocate.return_value = _FAKE_DIR

    router = MagicMock(spec=SubstrateRouter)
    router.choose.return_value = "dynamic"

    ps = _make_page_session(udm=udm, adapter=adapter, router=router)

    async with ps as ctx:
        with pytest.raises(PageLoadTimeoutError):
            await ctx.navigate("https://does-not-exist.invalid/")


# ---------------------------------------------------------------------------
# Test 7 — navigate() propagiert BrowserLaunchError typed (kein Wrapping)
# ---------------------------------------------------------------------------


@pytest.mark.anyio
async def test_navigate_propagates_browser_launch_error_typed() -> None:
    """navigate() wraps ScraplingNavigateError-Subklassen NICHT — propagiert direkt."""
    adapter = AsyncMock(spec=ScraplingAdapter)
    original_exc = BrowserLaunchError("chromium failed to start")
    adapter.navigate.side_effect = original_exc

    udm = MagicMock(spec=UserDataDirManager)
    udm.allocate.return_value = _FAKE_DIR

    router = MagicMock(spec=SubstrateRouter)
    router.choose.return_value = "dynamic"

    ps = _make_page_session(udm=udm, adapter=adapter, router=router)

    async with ps as ctx:
        with pytest.raises(BrowserLaunchError) as exc_info:
            await ctx.navigate("https://example.com/")

    # Gleiches Objekt — kein Re-Wrapping in ScraplingNavigateError
    assert exc_info.value is original_exc


# ---------------------------------------------------------------------------
# Test 8 — navigate() verwendet substrate_hint wenn angegeben
# ---------------------------------------------------------------------------


@pytest.mark.anyio
async def test_navigate_uses_substrate_hint_when_provided() -> None:
    """navigate() gibt substrate_hint an SubstrateRouter.choose() weiter."""
    router = MagicMock(spec=SubstrateRouter)
    router.choose.return_value = "stealthy"

    adapter = AsyncMock(spec=ScraplingAdapter)
    adapter.navigate.return_value = NavigateResult(url="https://example.com/", status_code=200)

    udm = MagicMock(spec=UserDataDirManager)
    udm.allocate.return_value = _FAKE_DIR

    ps = _make_page_session(udm=udm, adapter=adapter, router=router)

    async with ps as ctx:
        await ctx.navigate("https://example.com/", substrate_hint="stealthy")

    router.choose.assert_called_once_with(dns_domain="example.com", substrate_hint="stealthy")
    adapter.navigate.assert_called_once()
    call_kwargs = adapter.navigate.call_args.kwargs
    assert call_kwargs.get("substrate_hint") == "stealthy"


# ---------------------------------------------------------------------------
# Test 9 — navigate() wählt "dynamic" als Default ohne hint
# ---------------------------------------------------------------------------


@pytest.mark.anyio
async def test_navigate_defaults_to_dynamic_substrate() -> None:
    """navigate() ohne substrate_hint wählt 'dynamic' via SubstrateRouter."""
    router = MagicMock(spec=SubstrateRouter)
    router.choose.return_value = "dynamic"

    adapter = AsyncMock(spec=ScraplingAdapter)
    adapter.navigate.return_value = NavigateResult(url="https://example.com/", status_code=200)

    udm = MagicMock(spec=UserDataDirManager)
    udm.allocate.return_value = _FAKE_DIR

    ps = _make_page_session(udm=udm, adapter=adapter, router=router)

    async with ps as ctx:
        await ctx.navigate("https://example.com/")

    router.choose.assert_called_once_with(dns_domain="example.com", substrate_hint=None)
