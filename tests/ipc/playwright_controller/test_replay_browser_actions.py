"""browser_actions replay extensions — click_selector, keyboard_type, keyboard_press.

Unit-mock tests (no real Chromium needed for CI). Tests the new replay-support
functions using AsyncMock/MagicMock for the Playwright Page.
"""

from __future__ import annotations

from unittest.mock import AsyncMock, MagicMock, patch

import pytest


@pytest.mark.anyio
async def test_click_selector_calls_page_click_once() -> None:
    """click_selector(page, selector) calls page.click(selector) exactly once."""
    from frontprompt.ipc.playwright_controller.browser_actions import click_selector

    page = AsyncMock()
    page.click = AsyncMock(return_value=None)

    result = await click_selector(page, "button#submit")

    page.click.assert_called_once_with("button#submit")
    assert result == {"ok": True}


@pytest.mark.anyio
async def test_click_selector_returns_error_on_playwright_error() -> None:
    """click_selector returns {ok: False, error: ...} when page.click raises."""
    from playwright.async_api import Error as PlaywrightError

    from frontprompt.ipc.playwright_controller.browser_actions import click_selector

    page = AsyncMock()
    page.click = AsyncMock(side_effect=PlaywrightError("element not found"))

    result = await click_selector(page, "button#missing")

    assert result["ok"] is False
    assert "error" in result
    assert "element not found" in result["error"]


@pytest.mark.anyio
async def test_keyboard_type_calls_keyboard_type() -> None:
    """keyboard_type(page, text) calls page.keyboard.type(text)."""
    from frontprompt.ipc.playwright_controller.browser_actions import keyboard_type

    page = MagicMock()
    page.keyboard = MagicMock()
    page.keyboard.type = AsyncMock(return_value=None)

    result = await keyboard_type(page, "hello world")

    page.keyboard.type.assert_called_once_with("hello world")
    assert result == {"ok": True}


@pytest.mark.anyio
async def test_keyboard_type_returns_error_on_playwright_error() -> None:
    """keyboard_type returns {ok: False, error: ...} when page.keyboard.type raises."""
    from playwright.async_api import Error as PlaywrightError

    from frontprompt.ipc.playwright_controller.browser_actions import keyboard_type

    page = MagicMock()
    page.keyboard = MagicMock()
    page.keyboard.type = AsyncMock(side_effect=PlaywrightError("keyboard error"))

    result = await keyboard_type(page, "text")

    assert result["ok"] is False
    assert "error" in result


@pytest.mark.anyio
async def test_keyboard_press_enter() -> None:
    """keyboard_press(page, 'Enter') calls page.keyboard.press('Enter')."""
    from frontprompt.ipc.playwright_controller.browser_actions import keyboard_press

    page = MagicMock()
    page.keyboard = MagicMock()
    page.keyboard.press = AsyncMock(return_value=None)

    result = await keyboard_press(page, "Enter")

    page.keyboard.press.assert_called_once_with("Enter")
    assert result == {"ok": True}


@pytest.mark.anyio
async def test_keyboard_press_escape() -> None:
    """keyboard_press(page, 'Escape') calls page.keyboard.press('Escape')."""
    from frontprompt.ipc.playwright_controller.browser_actions import keyboard_press

    page = MagicMock()
    page.keyboard = MagicMock()
    page.keyboard.press = AsyncMock(return_value=None)

    result = await keyboard_press(page, "Escape")

    page.keyboard.press.assert_called_once_with("Escape")
    assert result == {"ok": True}


@pytest.mark.anyio
async def test_keyboard_press_returns_error_on_playwright_error() -> None:
    """keyboard_press returns {ok: False, error: ...} when page.keyboard.press raises."""
    from playwright.async_api import Error as PlaywrightError

    from frontprompt.ipc.playwright_controller.browser_actions import keyboard_press

    page = MagicMock()
    page.keyboard = MagicMock()
    page.keyboard.press = AsyncMock(side_effect=PlaywrightError("key error"))

    result = await keyboard_press(page, "Tab")

    assert result["ok"] is False
    assert "error" in result
