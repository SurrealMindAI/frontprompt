"""XPath-based element querier — low-level escape-hatch.

Returns element descriptor dicts in the same shape as
PlaywrightPageController._ELEMENT_DATA_JS results so that
ProgrammaticPickService can build Picks from them without knowing
how they were found.
"""

from __future__ import annotations

import time
from typing import Any

import structlog
from playwright.async_api import ElementHandle, Page

_LOG = structlog.get_logger(__name__)

# Reuse the same JS fragment as controller.py to stay DRY.
# Deliberately duplicated here rather than importing from controller.py to
# avoid circular dependency (controller imports xpath_query in step 5).
# TODO: extract to shared _element_data.py if 3+ consumers emerge (YAGNI now).
_ELEMENT_DATA_JS = """(el, i) => {
    const r = el.getBoundingClientRect();
    const attrs = Object.fromEntries(
        Array.from(el.attributes).map(a => [a.name, a.value])
    );
    const nthIdx = Array.from(
        el.parentElement
            ? el.parentElement.querySelectorAll(el.tagName)
            : [el]
    ).indexOf(el) + 1;
    const idPart = el.id ? `#${el.id}` : '';
    const tag = el.tagName.toLowerCase();
    const nth = `:nth-of-type(${nthIdx})`;
    const generatedSel = idPart ? `${tag}${idPart}` : `${tag}${nth}`;
    return {
        selector: generatedSel,
        fingerprint: {
            tag,
            attributes: attrs,
            text: (el.textContent || '').trim().slice(0, 500),
            path: [],
            parent_name: el.parentElement
                ? el.parentElement.tagName.toLowerCase() : null,
            parent_attribs: el.parentElement
                ? Object.fromEntries(
                    Array.from(el.parentElement.attributes)
                        .map(a => [a.name, a.value])
                  ) : {},
            parent_text: el.parentElement
                ? (el.parentElement.textContent || '').trim().slice(0, 500)
                : '',
            siblings: Array.from(
                el.parentElement
                    ? el.parentElement.children : []
            ).filter(c => c !== el).map(c => c.tagName.toLowerCase()),
            children: Array.from(el.children).map(
                c => c.tagName.toLowerCase()
            ),
        },
        rect: { x: r.x, y: r.y, width: r.width, height: r.height },
        text_snippet: (el.innerText || el.textContent || '').trim().slice(0, 120),
        color_index: i % 32,
    };
}"""


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
        el_data: dict[str, Any] = await h.evaluate(_ELEMENT_DATA_JS, i)
        el_data["url"] = url
        el_data["timestamp_ms"] = ts
        elements.append(el_data)

    _LOG.info("pick_by_xpath.done", total_matches=total, captured=len(elements))
    return {"total_matches": total, "elements": elements}


__all__ = ["pick_by_xpath"]
