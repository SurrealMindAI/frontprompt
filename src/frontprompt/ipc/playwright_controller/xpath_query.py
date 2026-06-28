"""XPath-based element querier — low-level escape-hatch.

Returns element descriptor dicts in the same shape as the shared
``ELEMENT_DESCRIPTOR_FN`` (see :mod:`_element_data`) so that
ProgrammaticPickService can build Picks from them without knowing
how they were found.
"""

from __future__ import annotations

import time
from typing import Any

import structlog
from playwright.async_api import ElementHandle, Page

from frontprompt.ipc.playwright_controller._element_data import ELEMENT_DESCRIPTOR_FN

_LOG = structlog.get_logger(__name__)


async def pick_by_xpath(
    page: Page,
    xpath: str,
    parent_handle: ElementHandle | None,
    limit: int,
) -> dict[str, Any]:
    """Query the live DOM with an XPath expression.

    ``parent_handle``: when given, uses the parent element as the context node
    by filtering results to only those that are descendants of the parent.

    Returns ``{total_matches: int, elements: list[dict]}``.  Raises
    ``ValueError`` for syntactically invalid XPath.
    """
    _LOG.info("pick_by_xpath.start", xpath=xpath, limit=limit)
    url: str = page.url
    ts: int = int(time.time() * 1000)

    try:
        locator = page.locator(f"xpath={xpath}")
        all_handles: list[ElementHandle] = await locator.element_handles()
    except Exception as exc:
        # Playwright raises a playwright._impl._errors.Error for invalid XPath
        raise ValueError(f"Invalid XPath expression: {exc}") from exc

    # Scope to parent subtree if given
    if parent_handle is not None:
        filtered: list[ElementHandle] = []
        for h in all_handles:
            is_desc: bool = await parent_handle.evaluate("(parent, child) => parent.contains(child)", h)
            if is_desc:
                filtered.append(h)
        all_handles = filtered

    total = len(all_handles)
    capped = all_handles[:limit]
    elements: list[dict[str, Any]] = []
    for i, h in enumerate(capped):
        el_data: dict[str, Any] = await h.evaluate(ELEMENT_DESCRIPTOR_FN, i)
        el_data["url"] = url
        el_data["timestamp_ms"] = ts
        elements.append(el_data)

    _LOG.info("pick_by_xpath.done", total_matches=total, captured=len(elements))
    return {"total_matches": total, "elements": elements}


__all__ = ["pick_by_xpath"]
