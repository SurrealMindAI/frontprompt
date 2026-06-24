"""Screenshot ↔ overlay hide/restore integration tests.

Spawns a real headless Chromium with a fake frontprompt overlay-host injected
via add_init_script, then exercises the _hide_overlay / _restore_overlay
helpers and the shoot_page/shoot_element wrappers to assert:

  1. _hide_overlay sets style.display='none' on the overlay-host
  2. _hide_overlay returns False when the overlay-host is absent
  3. _restore_overlay puts the display value back to its pre-hide state
  4. shoot_page restores the overlay after a successful screenshot
  5. shoot_page restores the overlay even when the screenshot itself raises
  6. shoot_element restores the overlay after a successful element screenshot

Skipped automatically if Playwright's chromium binary is not installed.
"""

from __future__ import annotations

import shutil
from collections.abc import AsyncIterator, Awaitable, Callable
from pathlib import Path
from typing import Any

import pytest
from playwright.async_api import Browser, Page, async_playwright

from frontprompt.ipc.playwright_controller.screenshots import (
    _hide_overlay,
    _restore_overlay,
    shoot_element,
    shoot_page,
)
from frontprompt.overlay.injector import DEFAULT_MARKER_ID

_INJECT_OVERLAY_JS = f"""() => {{
    if (document.getElementById('{DEFAULT_MARKER_ID}')) return;
    const host = document.createElement('div');
    host.id = '{DEFAULT_MARKER_ID}';
    host.style.cssText = (
        'position:fixed;inset:0;background:red;z-index:99999;pointer-events:none;'
    );
    document.body.appendChild(host);
}}"""

_PAGE_HTML = "<!DOCTYPE html><html><body><h1 id='hdr'>Page Content</h1><button id='btn'>Click</button></body></html>"


def _chromium_binary_available() -> bool:
    candidates = [
        Path.home() / "Library" / "Caches" / "ms-playwright",
        Path.home() / ".cache" / "ms-playwright",
    ]
    for cache in candidates:
        if cache.is_dir() and any(p.name.startswith("chromium-") for p in cache.iterdir()):
            return True
    return shutil.which("chromium") is not None


pytestmark = [
    pytest.mark.anyio,
    pytest.mark.skipif(
        not _chromium_binary_available(),
        reason="Playwright Chromium binary not installed.",
    ),
]


async def _display_of_overlay(page: Page) -> str:
    """Return overlay-host element.style.display, or 'MISSING' if absent."""
    return await page.evaluate(
        f"""() => {{
            const el = document.getElementById('{DEFAULT_MARKER_ID}');
            return el ? el.style.display : 'MISSING';
        }}"""
    )


@pytest.fixture
async def page_with_overlay() -> AsyncIterator[Page]:
    async with async_playwright() as pw:
        browser: Browser = await pw.chromium.launch(headless=True)
        try:
            ctx = await browser.new_context(viewport={"width": 400, "height": 300})
            page = await ctx.new_page()
            await page.set_content(_PAGE_HTML)
            # Inject overlay-host directly via evaluate — avoids init-script lifecycle
            # timing race with set_content (DOMContentLoaded does not always fire).
            await page.evaluate(_INJECT_OVERLAY_JS)
            await page.wait_for_selector(f"#{DEFAULT_MARKER_ID}", state="attached", timeout=2000)
            yield page
        finally:
            await browser.close()


@pytest.fixture
async def page_without_overlay() -> AsyncIterator[Page]:
    async with async_playwright() as pw:
        browser = await pw.chromium.launch(headless=True)
        try:
            ctx = await browser.new_context()
            page = await ctx.new_page()
            await page.set_content(_PAGE_HTML)
            yield page
        finally:
            await browser.close()


async def test_hide_overlay_sets_display_none(page_with_overlay: Page) -> None:
    assert await _display_of_overlay(page_with_overlay) == ""  # pre-hide default
    result = await _hide_overlay(page_with_overlay)
    assert result is True
    assert await _display_of_overlay(page_with_overlay) == "none"


async def test_hide_overlay_returns_false_when_absent(page_without_overlay: Page) -> None:
    result = await _hide_overlay(page_without_overlay)
    assert result is False


async def test_restore_overlay_brings_display_back(page_with_overlay: Page) -> None:
    await _hide_overlay(page_with_overlay)
    assert await _display_of_overlay(page_with_overlay) == "none"
    await _restore_overlay(page_with_overlay)
    assert await _display_of_overlay(page_with_overlay) == ""


async def test_shoot_page_restores_overlay_after_success(page_with_overlay: Page) -> None:
    result = await shoot_page(page_with_overlay, full_page=False, return_mode="inline")
    assert "image_base64" in result
    assert await _display_of_overlay(page_with_overlay) == ""


async def test_shoot_page_restores_overlay_on_screenshot_error(
    page_with_overlay: Page,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    async def fail_screenshot(**_kwargs: Any) -> bytes:
        raise RuntimeError("synthetic screenshot failure")

    monkeypatch.setattr(page_with_overlay, "screenshot", fail_screenshot)
    with pytest.raises(RuntimeError, match="synthetic screenshot failure"):
        await shoot_page(page_with_overlay, full_page=False, return_mode="inline")
    assert await _display_of_overlay(page_with_overlay) == ""


async def test_shoot_element_restores_overlay_after_success(page_with_overlay: Page) -> None:
    handle = await page_with_overlay.query_selector("#btn")
    assert handle is not None
    result = await shoot_element(handle, padding=0, return_mode="inline")
    assert "image_base64" in result
    assert await _display_of_overlay(page_with_overlay) == ""


# Suppress unused-import warning on optional typing aliases — keeps mypy happy
# when stricter modes don't see Callable/Awaitable usage in the future.
_ = (Callable, Awaitable)
