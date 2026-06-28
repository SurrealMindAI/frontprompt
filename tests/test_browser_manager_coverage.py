"""BrowserSessionManager coverage tests — error paths and branch coverage.

Covers:
- _chromium_present() with PLAYWRIGHT_BROWSERS_PATH env var
- page property before __aenter__
- navigate() before __aenter__
- navigate() exception path
- wait_until_closed() before __aenter__
- add_init_script() before __aenter__
- evaluate() before __aenter__
- evaluate() exception path
- __aexit__ when not entered (skip cleanup)
"""

from __future__ import annotations

import os
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from frontprompt.browser.errors import BrowserNotReadyError, NavigationError, PageEvaluationError
from frontprompt.browser.manager import BrowserSessionManager, _chromium_present


# ── _chromium_present ─────────────────────────────────────────────────────────


def test_chromium_present_with_env_var(tmp_path: pytest.TempPath) -> None:
    """_chromium_present returns True when PLAYWRIGHT_BROWSERS_PATH has a chromium dir."""
    # Create a fake chromium dir
    chromium_dir = tmp_path / "chromium-123"
    chromium_dir.mkdir()
    with patch.dict(os.environ, {"PLAYWRIGHT_BROWSERS_PATH": str(tmp_path)}):
        assert _chromium_present() is True


def test_chromium_present_with_no_chromium_dirs(tmp_path: pytest.TempPath) -> None:
    """_chromium_present returns False when all known locations have no chromium-* directories.

    Patches os.path.expanduser so the default macOS/Linux cache dirs resolve to
    empty tmp directories — isolates the test from real installed playwright.
    """
    empty_dir = str(tmp_path / "empty-playwright")
    (tmp_path / "empty-playwright").mkdir()

    def fake_expanduser(path: str) -> str:
        # Redirect both default cache dirs to a non-existent sub-path
        return str(tmp_path / "no-such-cache")

    env_without_pw = {k: v for k, v in os.environ.items() if k != "PLAYWRIGHT_BROWSERS_PATH"}
    with (
        patch.dict(os.environ, env_without_pw, clear=True),
        patch("os.path.expanduser", side_effect=fake_expanduser),
    ):
        assert _chromium_present() is False


def test_chromium_present_with_unset_env_var() -> None:
    """_chromium_present checks default locations when PLAYWRIGHT_BROWSERS_PATH not set."""
    env_without_var = {k: v for k, v in os.environ.items() if k != "PLAYWRIGHT_BROWSERS_PATH"}
    with patch.dict(os.environ, env_without_var, clear=True):
        # Result depends on the host — just verify it doesn't raise
        result = _chromium_present()
        assert isinstance(result, bool)


# ── BrowserNotReadyError before __aenter__ ────────────────────────────────────


def test_page_property_before_enter_raises() -> None:
    """Accessing .page before __aenter__ raises BrowserNotReadyError."""
    mgr = BrowserSessionManager()
    with pytest.raises(BrowserNotReadyError):
        _ = mgr.page


@pytest.mark.anyio
async def test_navigate_before_enter_raises() -> None:
    """navigate() before __aenter__ raises BrowserNotReadyError."""
    mgr = BrowserSessionManager()
    with pytest.raises(BrowserNotReadyError):
        await mgr.navigate("https://example.com")


@pytest.mark.anyio
async def test_wait_until_closed_before_enter_raises() -> None:
    """wait_until_closed() before __aenter__ raises BrowserNotReadyError."""
    mgr = BrowserSessionManager()
    with pytest.raises(BrowserNotReadyError):
        await mgr.wait_until_closed()


@pytest.mark.anyio
async def test_add_init_script_before_enter_raises() -> None:
    """add_init_script() before __aenter__ raises BrowserNotReadyError."""
    mgr = BrowserSessionManager()
    with pytest.raises(BrowserNotReadyError):
        await mgr.add_init_script("console.log('x')")


@pytest.mark.anyio
async def test_evaluate_before_enter_raises() -> None:
    """evaluate() before __aenter__ raises BrowserNotReadyError."""
    mgr = BrowserSessionManager()
    with pytest.raises(BrowserNotReadyError):
        await mgr.evaluate("1 + 1")


@pytest.mark.anyio
async def test_wait_for_load_state_before_enter_raises() -> None:
    """wait_for_load_state() before __aenter__ raises BrowserNotReadyError."""
    mgr = BrowserSessionManager()
    with pytest.raises(BrowserNotReadyError):
        await mgr.wait_for_load_state()


# ── __aexit__ when not entered ────────────────────────────────────────────────


@pytest.mark.anyio
async def test_aexit_when_not_entered_is_noop() -> None:
    """__aexit__ is a no-op when __aenter__ was never called (skip cleanup)."""
    mgr = BrowserSessionManager()
    # Should not raise — just returns because _entered is False
    await mgr.__aexit__(None, None, None)


# ── navigate() exception path ─────────────────────────────────────────────────


@pytest.mark.anyio
async def test_navigate_exception_raises_navigation_error() -> None:
    """navigate() wraps page.goto() exceptions in NavigationError."""
    mgr = BrowserSessionManager()
    # Manually set _entered and a fake _page
    mgr._entered = True
    fake_page = MagicMock()
    fake_page.goto = AsyncMock(side_effect=RuntimeError("network error"))
    mgr._page = fake_page

    with pytest.raises(NavigationError, match="network error"):
        await mgr.navigate("https://example.com")


# ── add_init_script() exception path ─────────────────────────────────────────


@pytest.mark.anyio
async def test_add_init_script_exception_raises_browser_launch_error() -> None:
    """add_init_script() wraps Playwright exceptions in BrowserLaunchError."""
    from frontprompt.browser.errors import BrowserLaunchError

    mgr = BrowserSessionManager()
    mgr._entered = True
    fake_page = MagicMock()
    fake_page.add_init_script = AsyncMock(side_effect=RuntimeError("init script rejected"))
    mgr._page = fake_page

    with pytest.raises(BrowserLaunchError, match="init script rejected"):
        await mgr.add_init_script("bad script")


# ── evaluate() exception path ─────────────────────────────────────────────────


@pytest.mark.anyio
async def test_evaluate_exception_raises_page_evaluation_error() -> None:
    """evaluate() wraps page.evaluate() exceptions in PageEvaluationError."""
    mgr = BrowserSessionManager()
    mgr._entered = True
    fake_page = MagicMock()
    fake_page.evaluate = AsyncMock(side_effect=RuntimeError("JS error"))
    mgr._page = fake_page

    with pytest.raises(PageEvaluationError, match="JS error"):
        await mgr.evaluate("throw new Error('boom')")


# ── repr ──────────────────────────────────────────────────────────────────────


def test_repr_not_entered() -> None:
    """repr shows not-entered state."""
    mgr = BrowserSessionManager()
    r = repr(mgr)
    assert "not-entered" in r
    assert "BrowserSessionManager" in r


def test_repr_entered() -> None:
    """repr shows ready state after _entered=True."""
    mgr = BrowserSessionManager()
    mgr._entered = True
    r = repr(mgr)
    assert "ready" in r
