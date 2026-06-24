"""DOM-reader funcs — read_text/_html/_attributes/_state/_outline."""

from __future__ import annotations

import pytest
from playwright.async_api import async_playwright

from frontprompt.ipc.playwright_controller.dom_readers import (
    read_attributes,
    read_html,
    read_outline,
    read_state,
    read_text,
)


@pytest.mark.anyio
async def test_read_text_basic() -> None:
    async with async_playwright() as pw:
        browser = await pw.chromium.launch(headless=True)
        page = await browser.new_page()
        await page.set_content('<button aria-label="Submit Form" role="button">Submit</button>')
        handle = await page.query_selector("button")
        result = await read_text(handle)
        assert result["text"] == "Submit"
        assert result["accessible_name"] == "Submit Form"
        assert result["role"] == "button"
        assert result["is_visible"] is True
        assert result["is_enabled"] is True
        assert result["is_focused"] is False
        await browser.close()


@pytest.mark.anyio
async def test_read_html_no_truncation() -> None:
    async with async_playwright() as pw:
        browser = await pw.chromium.launch(headless=True)
        page = await browser.new_page()
        await page.set_content("<p>hello</p>")
        handle = await page.query_selector("p")
        result = await read_html(handle, max_chars=10_000)
        assert "<p>hello</p>" in result["html"]
        assert result["truncated"] is False
        await browser.close()


@pytest.mark.anyio
async def test_read_html_truncation() -> None:
    async with async_playwright() as pw:
        browser = await pw.chromium.launch(headless=True)
        page = await browser.new_page()
        big = "<p>" + ("x" * 200) + "</p>"
        await page.set_content(big)
        handle = await page.query_selector("p")
        result = await read_html(handle, max_chars=20)
        assert len(result["html"]) <= 20
        assert result["truncated"] is True
        await browser.close()


@pytest.mark.anyio
async def test_read_attributes_returns_all() -> None:
    async with async_playwright() as pw:
        browser = await pw.chromium.launch(headless=True)
        page = await browser.new_page()
        await page.set_content('<a href="/foo" data-x="1" class="link">Foo</a>')
        handle = await page.query_selector("a")
        result = await read_attributes(handle)
        assert result["attributes"]["href"] == "/foo"
        assert result["attributes"]["data-x"] == "1"
        assert result["attributes"]["class"] == "link"
        await browser.close()


@pytest.mark.anyio
async def test_read_state_disabled_button() -> None:
    async with async_playwright() as pw:
        browser = await pw.chromium.launch(headless=True)
        page = await browser.new_page()
        await page.set_content("<button disabled>x</button>")
        handle = await page.query_selector("button")
        result = await read_state(handle)
        assert result["visible"] is True
        assert result["enabled"] is False
        assert result["focused"] is False
        await browser.close()


@pytest.mark.anyio
async def test_read_outline_capped_depth() -> None:
    async with async_playwright() as pw:
        browser = await pw.chromium.launch(headless=True)
        page = await browser.new_page()
        await page.set_content("<div><span>A</span><span>B</span><div><span>nested</span></div></div>")
        handle = await page.query_selector("div")
        result = await read_outline(handle, max_depth=1, max_nodes=100)
        assert result["outline"]["tag"] == "div"
        # depth=1 → children present, but grandchildren empty
        for child in result["outline"]["children"]:
            assert child["children"] == []
        await browser.close()
