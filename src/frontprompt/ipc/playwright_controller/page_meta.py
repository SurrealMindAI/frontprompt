"""Page-level metadata reader."""

from __future__ import annotations

from typing import Any, cast

import structlog
from playwright.async_api import Page

from frontprompt.ipc.playwright_controller.timeouts import (
    PAGE_OP_TIMEOUT_S,
    with_page_op_timeout,
)

_LOG = structlog.get_logger(__name__)


async def page_info(page: Page, *, timeout: float = PAGE_OP_TIMEOUT_S) -> dict[str, Any]:
    # Entry/exit tracing around the page.evaluate roundtrip: a hang inside
    # Playwright leaves ``page_info.start`` as the last line with no ``.done``.
    # The page.evaluate is bounded — a wedged page raises PageOpTimeoutError
    # (caught by the IPC dispatcher) instead of hanging the daemon forever.
    _LOG.info("page_info.start")

    async def _evaluate() -> Any:
        return await page.evaluate(
            """() => ({
                url: window.location.href,
                title: document.title,
                viewport_w: window.innerWidth,
                viewport_h: window.innerHeight,
                scroll_x: window.scrollX,
                scroll_y: window.scrollY,
                ready_state: document.readyState,
            })"""
        )

    result = await with_page_op_timeout("page_info", _evaluate, timeout=timeout)
    _LOG.info("page_info.done")
    return cast(dict[str, Any], result)


__all__ = ["page_info"]
