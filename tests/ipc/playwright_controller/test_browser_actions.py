"""browser_actions — navigate + scroll_to + eval_js + dom_patch."""

from __future__ import annotations

import pytest
from playwright.async_api import async_playwright

from frontprompt.ipc.playwright_controller.browser_actions import (
    dom_patch,
    eval_js,
    navigate,
    scroll_to,
)


@pytest.mark.anyio
async def test_navigate_returns_url_and_title() -> None:
    async with async_playwright() as pw:
        browser = await pw.chromium.launch(headless=True)
        page = await browser.new_page()
        result = await navigate(page, "data:text/html,<title>Test</title><h1>x</h1>")
        assert result["navigated_to"].startswith("data:")
        assert result["title"] == "Test"
        await browser.close()


@pytest.mark.anyio
async def test_scroll_to_moves_element_into_viewport() -> None:
    async with async_playwright() as pw:
        browser = await pw.chromium.launch(headless=True)
        page = await browser.new_page()
        await page.set_content('<div style="height: 3000px;"></div><button id="target">Bottom</button>')
        handle = await page.query_selector("#target")
        result = await scroll_to(page, handle)
        assert result["is_in_viewport"] is True
        assert isinstance(result["scroll_x"], (int, float))
        assert isinstance(result["scroll_y"], (int, float))
        await browser.close()


# ── eval_js tests ──────────────────────────────────────────────────────────────


@pytest.mark.anyio
async def test_eval_js_returns_scalar() -> None:
    async with async_playwright() as pw:
        browser = await pw.chromium.launch(headless=True)
        page = await browser.new_page()
        await page.set_content("<h1>X</h1>")
        result = await eval_js(page, "1 + 1", handle=None)
        assert result == {"result": 2, "ok": True}
        await browser.close()


@pytest.mark.anyio
async def test_eval_js_exception_returns_error_dict() -> None:
    async with async_playwright() as pw:
        browser = await pw.chromium.launch(headless=True)
        page = await browser.new_page()
        await page.set_content("<p>x</p>")
        result = await eval_js(page, "throw new Error('boom')", handle=None)
        assert result["ok"] is False
        assert "JavaScript error" in result["error"]
        await browser.close()


@pytest.mark.anyio
async def test_eval_js_with_handle_binds_element() -> None:
    """eval_js with ElementHandle passes handle as argument, accessible in JS."""
    async with async_playwright() as pw:
        browser = await pw.chromium.launch(headless=True)
        page = await browser.new_page()
        await page.set_content('<button id="x">Click</button>')
        handle = await page.query_selector("button#x")
        # When a handle is passed, playwright passes it as first arg
        result = await eval_js(page, "(el) => el.tagName", handle=handle)
        assert result["ok"] is True
        assert result["result"] == "BUTTON"
        await browser.close()


# ── dom_patch tests ────────────────────────────────────────────────────────────


@pytest.mark.anyio
async def test_dom_patch_set_attribute() -> None:
    async with async_playwright() as pw:
        browser = await pw.chromium.launch(headless=True)
        page = await browser.new_page()
        await page.set_content('<div id="x">hello</div>')
        handle = await page.query_selector("#x")
        result = await dom_patch(
            [{"op": "set_attribute", "name": "data-custom", "value": "42"}],
            handle,
        )
        assert result["ok"] is True
        assert result["results"][0] == {"op": "set_attribute", "ok": True}
        attr = await handle.evaluate("el => el.getAttribute('data-custom')")
        assert attr == "42"
        await browser.close()


@pytest.mark.anyio
async def test_dom_patch_remove_attribute() -> None:
    async with async_playwright() as pw:
        browser = await pw.chromium.launch(headless=True)
        page = await browser.new_page()
        await page.set_content('<div id="x" class="old-class">hello</div>')
        handle = await page.query_selector("#x")
        result = await dom_patch([{"op": "remove_attribute", "name": "class"}], handle)
        assert result["ok"] is True
        attr = await handle.evaluate("el => el.getAttribute('class')")
        assert attr is None
        await browser.close()


@pytest.mark.anyio
async def test_dom_patch_set_text() -> None:
    async with async_playwright() as pw:
        browser = await pw.chromium.launch(headless=True)
        page = await browser.new_page()
        await page.set_content('<div id="x">old text</div>')
        handle = await page.query_selector("#x")
        result = await dom_patch([{"op": "set_text", "text": "hello"}], handle)
        assert result["ok"] is True
        text = await handle.evaluate("el => el.textContent")
        assert text == "hello"
        await browser.close()


@pytest.mark.anyio
async def test_dom_patch_add_class() -> None:
    async with async_playwright() as pw:
        browser = await pw.chromium.launch(headless=True)
        page = await browser.new_page()
        await page.set_content('<div id="x">item</div>')
        handle = await page.query_selector("#x")
        result = await dom_patch([{"op": "add_class", "class_name": "active"}], handle)
        assert result["ok"] is True
        has_class = await handle.evaluate("el => el.classList.contains('active')")
        assert has_class is True
        await browser.close()


@pytest.mark.anyio
async def test_dom_patch_remove_class() -> None:
    async with async_playwright() as pw:
        browser = await pw.chromium.launch(headless=True)
        page = await browser.new_page()
        await page.set_content('<div id="x" class="old active">item</div>')
        handle = await page.query_selector("#x")
        result = await dom_patch([{"op": "remove_class", "class_name": "old"}], handle)
        assert result["ok"] is True
        has_class = await handle.evaluate("el => el.classList.contains('old')")
        assert has_class is False
        await browser.close()


@pytest.mark.anyio
async def test_dom_patch_remove_element() -> None:
    async with async_playwright() as pw:
        browser = await pw.chromium.launch(headless=True)
        page = await browser.new_page()
        await page.set_content('<div id="x">to remove</div><p>remains</p>')
        handle = await page.query_selector("#x")
        result = await dom_patch([{"op": "remove_element"}], handle)
        assert result["ok"] is True
        # element should no longer exist
        gone = await page.query_selector("#x")
        assert gone is None
        await browser.close()


@pytest.mark.anyio
async def test_dom_patch_unknown_op() -> None:
    async with async_playwright() as pw:
        browser = await pw.chromium.launch(headless=True)
        page = await browser.new_page()
        await page.set_content('<div id="x"></div>')
        handle = await page.query_selector("#x")
        result = await dom_patch([{"op": "explode"}], handle)
        assert result["ok"] is False
        assert result["results"][0]["error"] == "unknown operation kind"
        await browser.close()
