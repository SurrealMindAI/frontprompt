"""Flat funcs that read DOM state from an ElementHandle. Pure I/O, no state-mutation."""

from __future__ import annotations

from typing import Any, cast

from playwright.async_api import ElementHandle


async def read_text(handle: ElementHandle) -> dict[str, Any]:
    result = await handle.evaluate(
        """(el) => ({
            text: (el.innerText || el.textContent || '').trim(),
            accessible_name: el.getAttribute('aria-label')
                || el.getAttribute('alt')
                || el.getAttribute('title')
                || null,
            role: el.getAttribute('role') || el.tagName.toLowerCase(),
            is_visible: (() => {
                const r = el.getBoundingClientRect();
                const s = window.getComputedStyle(el);
                return r.width > 0 && r.height > 0
                    && s.display !== 'none' && s.visibility !== 'hidden'
                    && parseFloat(s.opacity) > 0;
            })(),
            is_enabled: !el.disabled && el.getAttribute('aria-disabled') !== 'true',
            is_focused: el === document.activeElement,
        })"""
    )
    return cast(dict[str, Any], result)


async def read_html(handle: ElementHandle, max_chars: int) -> dict[str, Any]:
    full: str = cast(str, await handle.evaluate("(el) => el.outerHTML"))
    if len(full) <= max_chars:
        return {"html": full, "truncated": False}
    return {"html": full[:max_chars], "truncated": True}


async def read_attributes(handle: ElementHandle) -> dict[str, Any]:
    attrs: dict[str, str] = cast(
        dict[str, str],
        await handle.evaluate("(el) => Object.fromEntries(Array.from(el.attributes).map(a => [a.name, a.value]))"),
    )
    return {"attributes": attrs}


async def read_state(handle: ElementHandle) -> dict[str, Any]:
    result = await handle.evaluate(
        """(el) => {
            const r = el.getBoundingClientRect();
            const s = window.getComputedStyle(el);
            const visible = r.width > 0 && r.height > 0
                && s.display !== 'none' && s.visibility !== 'hidden'
                && parseFloat(s.opacity) > 0;
            const in_viewport = visible
                && r.top < window.innerHeight && r.bottom > 0
                && r.left < window.innerWidth && r.right > 0;
            const checked = (el.type === 'checkbox' || el.type === 'radio')
                ? el.checked : null;
            return {
                visible,
                enabled: !el.disabled && el.getAttribute('aria-disabled') !== 'true',
                checked,
                focused: el === document.activeElement,
                in_viewport,
            };
        }"""
    )
    return cast(dict[str, Any], result)


async def read_outline(
    handle: ElementHandle,
    max_depth: int,
    max_nodes: int,
) -> dict[str, Any]:
    js = """(el, [maxDepth, maxNodes]) => {
        let count = 0;
        let truncated = false;
        function walk(node, depth) {
            if (count >= maxNodes) { truncated = true; return null; }
            count += 1;
            const out = {
                tag: node.tagName.toLowerCase(),
                text: (node.childNodes.length === 1
                       && node.childNodes[0].nodeType === Node.TEXT_NODE)
                    ? node.textContent.trim().slice(0, 60) : null,
                children: [],
            };
            if (depth >= maxDepth) return out;
            for (const child of node.children) {
                const c = walk(child, depth + 1);
                if (c) out.children.push(c);
                if (truncated) break;
            }
            return out;
        }
        const root = walk(el, 0);
        return { outline: root, truncated };
    }"""
    result = await handle.evaluate(js, [max_depth, max_nodes])
    return cast(dict[str, Any], result)


__all__ = ["read_attributes", "read_html", "read_outline", "read_state", "read_text"]
