"""page_meta — page_info reader func."""

from __future__ import annotations

import anyio
import pytest
from playwright.async_api import async_playwright

from frontprompt.ipc.playwright_controller.page_meta import page_info
from frontprompt.ipc.playwright_controller.timeouts import PageOpTimeoutError


@pytest.mark.anyio
async def test_page_info_raises_typed_timeout_when_evaluate_hangs() -> None:
    """A wedged page (page.evaluate never resolves) must raise PageOpTimeoutError
    within the bound, not hang forever."""

    class _WedgedPage:
        async def evaluate(self, *args: object, **kwargs: object) -> object:
            await anyio.sleep_forever()

    with pytest.raises(PageOpTimeoutError) as exc_info:
        await page_info(_WedgedPage(), timeout=0.05)  # type: ignore[arg-type]

    assert exc_info.value.op == "page_info"


@pytest.mark.anyio
async def test_page_info_returns_state() -> None:
    async with async_playwright() as pw:
        browser = await pw.chromium.launch(headless=True)
        page = await browser.new_page(viewport={"width": 800, "height": 600})
        await page.set_content("<title>Hi</title><p>hello</p>")
        result = await page_info(page)
        assert result["title"] == "Hi"
        assert result["viewport_w"] == 800
        assert result["viewport_h"] == 600
        assert result["scroll_x"] == 0.0
        assert result["scroll_y"] == 0.0
        assert result["ready_state"] in ("interactive", "complete")
        assert isinstance(result["url"], str)
        await browser.close()
