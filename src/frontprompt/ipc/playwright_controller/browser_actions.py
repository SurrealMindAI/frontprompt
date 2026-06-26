"""Browser-side actions — navigate, scroll_to, eval_js, dom_patch, click_selector, keyboard_type, keyboard_press. Pure I/O on Playwright Page.

All functions follow the "always return, never raise" contract: Playwright errors are
caught and returned as ``{"ok": False, "error": str(exc)}``.
"""

from __future__ import annotations

from typing import Any

import structlog
from playwright.async_api import ElementHandle, Error as PlaywrightError, Page

_LOG = structlog.get_logger(__name__)


async def navigate(page: Page, url: str) -> dict[str, Any]:
    """Navigate page to URL, wait for load, return {navigated_to, title}."""
    _LOG.info("navigate.start", url=url)
    await page.goto(url, wait_until="load")
    result = {
        "navigated_to": page.url,
        "title": await page.title(),
    }
    _LOG.info("navigate.done", navigated_to=result["navigated_to"])
    return result


async def scroll_to(page: Page, handle: ElementHandle) -> dict[str, Any]:
    """Scroll element into viewport (smooth), report final viewport-position."""
    _LOG.info("scroll_to.start")
    await handle.scroll_into_view_if_needed()
    state: dict[str, Any] = await page.evaluate("() => ({ scroll_x: window.scrollX, scroll_y: window.scrollY })")
    in_viewport: bool = await handle.is_visible()
    _LOG.info("scroll_to.done", is_in_viewport=in_viewport)
    return {
        "is_in_viewport": in_viewport,
        "scroll_x": state["scroll_x"],
        "scroll_y": state["scroll_y"],
    }


async def eval_js(
    page: Page,
    expression: str,
    handle: ElementHandle | None,
) -> dict[str, Any]:
    """Evaluate JS expression, optionally binding an ElementHandle as ``el``.

    When ``handle`` is provided, the expression is wrapped in a function so
    that it can reference the element as ``el``:
        ``"el.tagName"``  →  ``"(el) => { return (el.tagName); }"``

    If the expression already looks like a function (starts with ``(`` or
    ``function``), it is passed as-is.
    """
    _LOG.info("eval_js.start", has_handle=handle is not None)
    try:
        if handle is not None:
            stripped = expression.strip()
            looks_like_fn = stripped.startswith("(") or stripped.startswith("function")
            if looks_like_fn:
                js_fn = stripped
            else:
                js_fn = f"(el) => {{ return ({stripped}); }}"
            result = await page.evaluate(js_fn, handle)
        else:
            result = await page.evaluate(expression)
        _LOG.info("eval_js.done", ok=True)
        return {"result": result, "ok": True}
    except Exception as exc:  # playwright raises various Error subclasses
        _LOG.warning("eval_js.done", ok=False, error=str(exc))
        return {"ok": False, "error": f"JavaScript error: {exc}"}


# Supported op-discriminators for dom_patch
_DOM_PATCH_OPS = frozenset(
    {"set_attribute", "remove_attribute", "set_text", "add_class", "remove_class", "remove_element"}
)


async def dom_patch(
    operations: list[dict[str, Any]],
    handle: ElementHandle,
) -> dict[str, Any]:
    """Apply DOM patch operations to a live ElementHandle.

    Returns ``{ok, results}``. Each result has ``{op, ok}`` and optionally
    ``{error}``. Always returns — never raises.
    """
    _LOG.info("dom_patch.start", op_count=len(operations))
    results: list[dict[str, Any]] = []
    overall_ok = True
    for op_dict in operations:
        op_kind = op_dict.get("op", "")
        if op_kind not in _DOM_PATCH_OPS:
            results.append({"op": op_kind, "ok": False, "error": "unknown operation kind"})
            overall_ok = False
            continue
        try:
            await _apply_dom_op(handle, op_dict)
            results.append({"op": op_kind, "ok": True})
        except Exception as exc:
            results.append({"op": op_kind, "ok": False, "error": str(exc)})
            overall_ok = False
    _LOG.info("dom_patch.done", ok=overall_ok)
    return {"ok": overall_ok, "results": results}


async def _apply_dom_op(handle: ElementHandle, op: dict[str, Any]) -> None:
    op_kind = op["op"]
    if op_kind == "set_attribute":
        await handle.evaluate(
            "(el, [name, val]) => el.setAttribute(name, val)",
            [op["name"], op["value"]],
        )
    elif op_kind == "remove_attribute":
        await handle.evaluate("(el, name) => el.removeAttribute(name)", op["name"])
    elif op_kind == "set_text":
        await handle.evaluate("(el, text) => { el.textContent = text; }", op["text"])
    elif op_kind == "add_class":
        await handle.evaluate("(el, cls) => el.classList.add(cls)", op["class_name"])
    elif op_kind == "remove_class":
        await handle.evaluate("(el, cls) => el.classList.remove(cls)", op["class_name"])
    elif op_kind == "remove_element":
        await handle.evaluate("(el) => el.remove()")


async def click_selector(page: Page, selector: str) -> dict[str, Any]:
    """Click an element by CSS selector.

    Always returns — never raises. Returns ``{"ok": True}`` on success or
    ``{"ok": False, "error": str(exc)}`` on PlaywrightError.
    """
    _LOG.info("click_selector.start", selector=selector)
    try:
        await page.click(selector)
        _LOG.info("click_selector.done", ok=True)
        return {"ok": True}
    except PlaywrightError as exc:
        _LOG.warning("click_selector.done", ok=False, error=str(exc))
        return {"ok": False, "error": str(exc)}


async def keyboard_type(page: Page, text: str) -> dict[str, Any]:
    """Type text via the keyboard (page.keyboard.type).

    Always returns — never raises. Returns ``{"ok": True}`` on success or
    ``{"ok": False, "error": str(exc)}`` on PlaywrightError.
    """
    _LOG.info("keyboard_type.start", text_length=len(text))
    try:
        await page.keyboard.type(text)
        _LOG.info("keyboard_type.done", ok=True)
        return {"ok": True}
    except PlaywrightError as exc:
        _LOG.warning("keyboard_type.done", ok=False, error=str(exc))
        return {"ok": False, "error": str(exc)}


async def keyboard_press(page: Page, key: str) -> dict[str, Any]:
    """Press a named key (e.g. 'Enter', 'Escape', 'Tab') via page.keyboard.press.

    Always returns — never raises. Returns ``{"ok": True}`` on success or
    ``{"ok": False, "error": str(exc)}`` on PlaywrightError.
    """
    _LOG.info("keyboard_press.start", key=key)
    try:
        await page.keyboard.press(key)
        _LOG.info("keyboard_press.done", ok=True)
        return {"ok": True}
    except PlaywrightError as exc:
        _LOG.warning("keyboard_press.done", ok=False, error=str(exc))
        return {"ok": False, "error": str(exc)}


__all__ = ["click_selector", "dom_patch", "eval_js", "keyboard_press", "keyboard_type", "navigate", "scroll_to"]
