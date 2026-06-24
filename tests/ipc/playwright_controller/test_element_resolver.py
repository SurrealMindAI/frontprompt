"""ElementResolver tests — fingerprint-rehydrate + stale-detection.

Uses real Playwright per existing convention (headless=True).
pytest-anyio via anyio_backend fixture in conftest.py.
"""

from __future__ import annotations

import time

import pytest
from playwright.async_api import async_playwright

from frontprompt.ipc.playwright_controller.element_resolver import (
    ElementResolver,
    StalePickError,
)
from frontprompt.state.state import ElementFingerprint, ElementRect, Pick, PickElement


def _make_pick(selector: str, tag: str, classes: list[str], text: str) -> Pick:
    fp = ElementFingerprint(
        tag=tag,
        attributes={"class": " ".join(classes)} if classes else {},
        text=text,
    )
    rect = ElementRect(x=0.0, y=0.0, width=100.0, height=40.0)
    element = PickElement(
        selector=selector,
        fingerprint=fp,
        text_snippet=text[:120],
        rect=rect,
    )
    return Pick(
        pick_id="test-pick-1",
        url="about:blank",
        timestamp_ms=int(time.time() * 1000),
        element=element,
        comment="test",
        color_index=0,
    )


@pytest.mark.anyio
async def test_resolve_existing_element_returns_handle() -> None:
    async with async_playwright() as pw:
        browser = await pw.chromium.launch(headless=True)
        page = await browser.new_page()
        await page.set_content('<button id="x" class="primary">Submit</button>')
        pick = _make_pick(
            selector="button#x",
            tag="button",
            classes=["primary"],
            text="Submit",
        )
        resolver = ElementResolver(page)
        handle = await resolver.resolve(pick)
        assert handle is not None
        await browser.close()


@pytest.mark.anyio
async def test_resolve_missing_selector_returns_none() -> None:
    """When CSS selector doesn't match anything, return None (stale)."""
    async with async_playwright() as pw:
        browser = await pw.chromium.launch(headless=True)
        page = await browser.new_page()
        await page.set_content("<p>no buttons here</p>")
        pick = _make_pick(selector="button.gone", tag="button", classes=["gone"], text="")
        resolver = ElementResolver(page)
        assert await resolver.resolve(pick) is None
        await browser.close()


@pytest.mark.anyio
async def test_resolve_fingerprint_mismatch_returns_none() -> None:
    """When CSS resolves but text changed (different element), return None."""
    async with async_playwright() as pw:
        browser = await pw.chromium.launch(headless=True)
        page = await browser.new_page()
        # pick records "Original" text
        pick = _make_pick(
            selector="button#x",
            tag="button",
            classes=[],
            text="Original",
        )
        # page now has "Replaced" — fingerprint mismatch
        await page.set_content('<button id="x">Replaced</button>')
        resolver = ElementResolver(page)
        assert await resolver.resolve(pick) is None
        await browser.close()


@pytest.mark.anyio
async def test_stale_pick_error_raised_by_caller() -> None:
    """StalePickError is importable and is-a Exception (used by pick-creators)."""
    with pytest.raises(StalePickError):
        raise StalePickError("test")


# ── analyzer fallback tests (sub-plan 03) ─────────────────────────────────────


@pytest.mark.anyio
async def test_resolve_without_analyzer_returns_none_on_missing() -> None:
    """Without analyzer: CSS miss → returns None (behaviour unchanged)."""
    async with async_playwright() as pw:
        browser = await pw.chromium.launch(headless=True)
        page = await browser.new_page()
        await page.set_content("<p>no buttons here</p>")
        pick = _make_pick(selector="button.gone", tag="button", classes=["gone"], text="")
        resolver = ElementResolver(page)  # no analyzer
        assert await resolver.resolve(pick) is None
        await browser.close()


@pytest.mark.anyio
async def test_resolve_with_analyzer_fallback_recovers_pick() -> None:
    """When CSS fails but analyzer.relocate returns 'recovered' status, handle is returned."""
    from unittest.mock import AsyncMock, MagicMock

    async with async_playwright() as pw:
        browser = await pw.chromium.launch(headless=True)
        page = await browser.new_page()
        await page.set_content('<button id="y">Submit</button>')

        # Build a pick with stale selector (points to #x, but page has #y)
        pick = _make_pick(selector="button#x", tag="button", classes=[], text="Submit")

        # Mock analyzer.relocate: returns status="recovered" with updated pick
        recovered_pick = _make_pick(selector="button#y", tag="button", classes=[], text="Submit")
        relocation_result = MagicMock()
        relocation_result.status = "recovered"
        relocation_result.pick = recovered_pick

        mock_analyzer = MagicMock()
        mock_analyzer.relocate = AsyncMock(return_value=[relocation_result])

        resolver = ElementResolver(page, analyzer=mock_analyzer)
        handle = await resolver.resolve(pick)
        # Should return a handle via the recovered selector
        assert handle is not None
        await browser.close()


@pytest.mark.anyio
async def test_resolve_with_analyzer_fallback_gives_up_on_not_found() -> None:
    """When analyzer.relocate returns status other than alive/recovered, returns None."""
    from unittest.mock import AsyncMock, MagicMock

    async with async_playwright() as pw:
        browser = await pw.chromium.launch(headless=True)
        page = await browser.new_page()
        await page.set_content("<p>nothing here</p>")

        pick = _make_pick(selector="button.gone", tag="button", classes=["gone"], text="")

        relocation_result = MagicMock()
        relocation_result.status = "not_found"

        mock_analyzer = MagicMock()
        mock_analyzer.relocate = AsyncMock(return_value=[relocation_result])

        resolver = ElementResolver(page, analyzer=mock_analyzer)
        assert await resolver.resolve(pick) is None
        await browser.close()
