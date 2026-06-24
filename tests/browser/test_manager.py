"""BrowserSessionManager — unit + integration tests.

Unit-Tests: keine Playwright-Binary nötig, prüfen Lifecycle-Invarianten,
Error-Pfade, ID-Generation.

Integration-Test: spawnt echtes Chromium (headless=True). Skipped automatisch
wenn Playwright-Binary nicht installiert.
"""

from __future__ import annotations

import shutil
from pathlib import Path

import pytest

from frontprompt.browser import (
    BrowserNotReadyError,
    BrowserSessionManager,
)

# ---- Unit tests (no browser binary needed) ----------------------------------


def test_browser_session_id_is_uuid_string() -> None:
    """Jeder Manager hat eine eigene UUID als browser_session_id."""
    mgr = BrowserSessionManager()
    bsid = mgr.browser_session_id
    assert isinstance(bsid, str)
    assert len(bsid) == 36  # uuid4 string form
    assert bsid.count("-") == 4


def test_two_managers_have_distinct_ids() -> None:
    """Pro Instanz eine eigene browser_session_id (kein Module-Singleton)."""
    a = BrowserSessionManager()
    b = BrowserSessionManager()
    assert a.browser_session_id != b.browser_session_id


def test_page_property_before_enter_raises_not_ready() -> None:
    """Zugriff auf .page vor ``async with`` → typed error, kein AttributeError."""
    mgr = BrowserSessionManager()
    with pytest.raises(BrowserNotReadyError):
        _ = mgr.page


@pytest.mark.anyio
async def test_navigate_before_enter_raises_not_ready() -> None:
    """``navigate()`` vor ``async with`` → typed error."""
    mgr = BrowserSessionManager()
    with pytest.raises(BrowserNotReadyError):
        await mgr.navigate("about:blank")


@pytest.mark.anyio
async def test_wait_until_closed_before_enter_raises_not_ready() -> None:
    """``wait_until_closed()`` vor ``async with`` → typed error."""
    mgr = BrowserSessionManager()
    with pytest.raises(BrowserNotReadyError):
        await mgr.wait_until_closed()


def test_repr_indicates_state() -> None:
    """``repr()`` zeigt entered/not-entered für Debug-Sichtbarkeit."""
    mgr = BrowserSessionManager()
    r = repr(mgr)
    assert "BrowserSessionManager" in r
    assert mgr.browser_session_id in r
    assert "not-entered" in r


def test_headless_default_is_false() -> None:
    """Phase-1-CLI braucht headless=False als default (UX = sichtbares Fenster)."""
    mgr = BrowserSessionManager()
    assert mgr._headless is False


def test_headless_can_be_overridden_for_tests() -> None:
    """Integration-Tests können headless=True wählen für CI."""
    mgr = BrowserSessionManager(headless=True)
    assert mgr._headless is True


# ---- Integration test (skipped if no playwright binary) ----------------------


def _chromium_binary_available() -> bool:
    """Check ob Playwright's Chromium-Binary installiert ist.

    Playwright cached Browsers in ~/Library/Caches/ms-playwright/ (macOS)
    oder ~/.cache/ms-playwright/ (Linux). Wenn das Cache-Dir nicht existiert
    oder kein chromium-* darin liegt, skippen wir den integration-test.
    """
    candidates = [
        Path.home() / "Library" / "Caches" / "ms-playwright",
        Path.home() / ".cache" / "ms-playwright",
    ]
    for cache in candidates:
        if cache.is_dir() and any(p.name.startswith("chromium-") for p in cache.iterdir()):
            return True
    return shutil.which("chromium") is not None  # fallback: system chromium


@pytest.mark.anyio
@pytest.mark.skipif(
    not _chromium_binary_available(),
    reason="Playwright Chromium binary not installed (run `playwright install chromium`).",
)
async def test_real_chromium_navigate_about_blank() -> None:
    """End-to-end smoke: launch headless Chromium, navigate to about:blank, close.

    Validiert dass die Manager-Lifecycle-Sequenz mit echtem Playwright funktioniert.
    headless=True für CI-Verträglichkeit.
    """
    async with BrowserSessionManager(headless=True) as mgr:
        assert mgr.page is not None
        await mgr.navigate("about:blank")
        # Don't call wait_until_closed — would block indefinitely. Just exit
        # the context and verify clean shutdown.


@pytest.mark.anyio
@pytest.mark.skipif(
    not _chromium_binary_available(),
    reason="Playwright Chromium binary not installed.",
)
async def test_real_chromium_browser_session_id_stable_across_navigate() -> None:
    """browser_session_id darf sich nicht durch Navigate ändern."""
    async with BrowserSessionManager(headless=True) as mgr:
        bsid_before = mgr.browser_session_id
        await mgr.navigate("about:blank")
        bsid_after = mgr.browser_session_id
        assert bsid_before == bsid_after
