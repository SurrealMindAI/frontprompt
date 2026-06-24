"""pick_by_xpath — XPath-based element query helper."""

from __future__ import annotations

import pytest
from playwright.async_api import async_playwright

from frontprompt.ipc.playwright_controller.xpath_query import pick_by_xpath


@pytest.mark.anyio
async def test_pick_by_xpath_single_match() -> None:
    async with async_playwright() as pw:
        browser = await pw.chromium.launch(headless=True)
        page = await browser.new_page()
        await page.set_content('<button id="x">Click</button>')
        result = await pick_by_xpath(page, "//button[@id='x']", None, 10)
        assert result["total_matches"] == 1
        assert len(result["elements"]) == 1
        assert result["elements"][0]["fingerprint"]["tag"] == "button"
        await browser.close()


@pytest.mark.anyio
async def test_pick_by_xpath_zero_matches() -> None:
    async with async_playwright() as pw:
        browser = await pw.chromium.launch(headless=True)
        page = await browser.new_page()
        await page.set_content("<p>no buttons</p>")
        result = await pick_by_xpath(page, "//unicorn", None, 10)
        assert result == {"total_matches": 0, "elements": []}
        await browser.close()


@pytest.mark.anyio
async def test_pick_by_xpath_multi_match_capped_by_limit() -> None:
    async with async_playwright() as pw:
        browser = await pw.chromium.launch(headless=True)
        page = await browser.new_page()
        await page.set_content("<ul>" + "<li>x</li>" * 10 + "</ul>")
        result = await pick_by_xpath(page, "//li", None, 3)
        assert result["total_matches"] == 10
        assert len(result["elements"]) == 3
        await browser.close()


@pytest.mark.anyio
async def test_pick_by_xpath_invalid_xpath_raises_value_error() -> None:
    async with async_playwright() as pw:
        browser = await pw.chromium.launch(headless=True)
        page = await browser.new_page()
        await page.set_content("<p>x</p>")
        with pytest.raises(ValueError, match="Invalid XPath"):
            await pick_by_xpath(page, "//[@broken", None, 10)
        await browser.close()


@pytest.mark.anyio
async def test_pick_by_xpath_parent_scopes_results() -> None:
    """XPath scoped to parent_handle only returns elements inside parent subtree."""
    async with async_playwright() as pw:
        browser = await pw.chromium.launch(headless=True)
        page = await browser.new_page()
        await page.set_content("<nav><ul><li>a</li><li>b</li><li>c</li></ul></nav><ul><li>d</li><li>e</li></ul>")
        parent_handle = await page.query_selector("nav")
        result = await pick_by_xpath(page, "//li", parent_handle, 10)
        # Only the 3 li inside <nav> should match
        assert result["total_matches"] == 3
        assert len(result["elements"]) == 3
        await browser.close()
