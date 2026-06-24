"""PlaywrightPageController — thin orchestrator over ElementResolver + flat helpers.

Each tool-method:
  1. resolves pick → ElementHandle via ElementResolver
  2. on stale: returns {error: 'stale_pick', pick_id: ...} in the list position
  3. delegates to dom_readers / browser_actions / screenshots / page_meta

query_selector_all is used exclusively by ProgrammaticPickService (sub-plan 02).
"""

from __future__ import annotations

import time
from typing import TYPE_CHECKING, Any

import structlog
from playwright.async_api import Page

from frontprompt.ipc.page_controller import PageController
from frontprompt.ipc.playwright_controller import browser_actions, dom_readers, page_meta, xpath_query
from frontprompt.ipc.playwright_controller.element_resolver import (
    ElementResolver,
    StalePickError,
)
from frontprompt.ipc.playwright_controller.screenshots import (
    ScreenshotTooLargeError,
    shoot_element,
    shoot_page,
)
from frontprompt.state.state import Pick

if TYPE_CHECKING:
    from frontprompt.analysis.analyzer import PageAnalyzer

_LOG = structlog.get_logger(__name__)


class PlaywrightPageController(PageController):
    def __init__(
        self,
        page: Page,
        resolver: ElementResolver,
        analyzer: PageAnalyzer | None = None,
    ) -> None:
        self._page = page
        self._resolver = resolver
        self._analyzer = analyzer

    # expose page + resolver as public read-only properties
    # so socket_server.run_socket_server can construct PageAnalyzer at boot.
    @property
    def page(self) -> Page:
        return self._page

    @property
    def resolver(self) -> ElementResolver:
        return self._resolver

    # ── Write-side ─────────────────────────────────────────────────────────

    async def navigate(self, url: str) -> dict[str, Any]:
        return await browser_actions.navigate(self._page, url)

    async def scroll_to(self, pick: Pick) -> dict[str, Any]:
        handle = await self._resolver.resolve(pick)
        if handle is None:
            return {
                "error": "stale_pick",
                "pick_id": pick.pick_id,
                "is_in_viewport": False,
                "scroll_x": 0.0,
                "scroll_y": 0.0,
            }
        return await browser_actions.scroll_to(self._page, handle)

    # ── Read-side helpers ───────────────────────────────────────────────────

    async def _read_per_pick(self, picks: list[Pick], reader: Any, *args: Any) -> list[dict[str, Any]]:
        reader_name = getattr(reader, "__name__", str(reader))
        _LOG.info("read_per_pick.start", reader=reader_name, pick_count=len(picks))
        results: list[dict[str, Any]] = []
        for pick in picks:
            handle = await self._resolver.resolve(pick)
            if handle is None:
                results.append({"error": "stale_pick", "pick_id": pick.pick_id})
                continue
            data = await reader(handle, *args)
            results.append({"pick_id": pick.pick_id, **data})
        _LOG.info("read_per_pick.done", reader=reader_name, result_count=len(results))
        return results

    async def get_text(self, picks: list[Pick]) -> list[dict[str, Any]]:
        return await self._read_per_pick(picks, dom_readers.read_text)

    async def get_html(self, picks: list[Pick], max_chars: int) -> list[dict[str, Any]]:
        return await self._read_per_pick(picks, dom_readers.read_html, max_chars)

    async def get_attributes(self, picks: list[Pick]) -> list[dict[str, Any]]:
        return await self._read_per_pick(picks, dom_readers.read_attributes)

    async def get_state(self, picks: list[Pick]) -> list[dict[str, Any]]:
        return await self._read_per_pick(picks, dom_readers.read_state)

    async def get_outline(self, picks: list[Pick], max_depth: int, max_nodes: int) -> list[dict[str, Any]]:
        return await self._read_per_pick(picks, dom_readers.read_outline, max_depth, max_nodes)

    async def screenshot_element(self, picks: list[Pick], padding: int) -> list[dict[str, Any]]:
        results: list[dict[str, Any]] = []
        for pick in picks:
            handle = await self._resolver.resolve(pick)
            if handle is None:
                results.append({"error": "stale_pick", "pick_id": pick.pick_id})
                continue
            try:
                data = await shoot_element(handle, padding, session_id="default")
                results.append({"pick_id": pick.pick_id, **data})
            except ScreenshotTooLargeError as exc:
                results.append(
                    {
                        "pick_id": pick.pick_id,
                        "error": "screenshot_too_large",
                        "size_bytes": exc.size_bytes,
                    }
                )
        return results

    async def screenshot_page(self, full_page: bool) -> dict[str, Any]:
        try:
            return await shoot_page(self._page, full_page, session_id="default")
        except ScreenshotTooLargeError as exc:
            return {"error": "screenshot_too_large", "size_bytes": exc.size_bytes}

    async def get_page_info(self) -> dict[str, Any]:
        return await page_meta.page_info(self._page)

    # ── ProgrammaticPickService helper ──────────────────────────────────────

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

    async def _handle_to_element_data(self, handle: Any, color_idx: int) -> dict[str, Any]:
        """Convert a Playwright ElementHandle to the element descriptor dict."""
        result: dict[str, Any] = await handle.evaluate(self._ELEMENT_DATA_JS, color_idx)
        return result

    async def query_selector_all(
        self,
        selector: str,
        parent_pick: Pick | None,
        limit: int,
    ) -> dict[str, Any]:
        """Query DOM for selector matches.

        Takes a pre-resolved ``Pick`` (not pick_id-string). When
        ``parent_pick`` is given, resolve it to an ElementHandle via
        ElementResolver and scope the query to that subtree using
        ``parent_handle.evaluate(...)`` instead of ``page.evaluate(...)``.
        Stale parent (fingerprint mismatch) → raises StalePickError.

        Intercepts ``__text__:<text>`` and ``__text_role__:<text>|<role>``
        pseudo-selectors from :func:`programmatic_picks._text_pseudo_selector` and
        routes them to Playwright's ``get_by_text`` / ``get_by_role`` APIs for
        proper AND-semantics. Regular CSS selectors use ``querySelectorAll``.
        """
        url: str = self._page.url
        ts: int = int(time.time() * 1000)

        # --- pseudo-selector routing ---
        if selector.startswith("__text__:") or selector.startswith("__text_role__:"):
            return await self._query_by_text_pseudo(selector, parent_pick, limit, url, ts)

        # --- CSS querySelectorAll path ---
        if parent_pick is not None:
            parent_handle = await self._resolver.resolve(parent_pick)
            if parent_handle is None:
                raise StalePickError(f"parent pick {parent_pick.pick_id} no longer matches the DOM")
            scope_target = parent_handle
            # Query is now scoped: `el.querySelectorAll(sel)` instead of `document...`
            scope_query = "(el, [sel, lim]) => { const all = Array.from(el.querySelectorAll(sel));"
        else:
            scope_target = None
            scope_query = "([sel, lim]) => { const all = Array.from(document.querySelectorAll(sel));"

        js = (
            scope_query
            + """
            const total = all.length;
            const capped = all.slice(0, lim);
            return {
                total,
                elements: capped.map((el, _i) => {
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
                        color_index: _i % 32,
                    };
                }),
            };
        }"""
        )

        # dispatch to either parent-scoped or page-global evaluate
        if scope_target is not None:
            raw: dict[str, Any] = await scope_target.evaluate(js, [selector, limit])
        else:
            raw = await self._page.evaluate(js, [selector, limit])
        for el in raw["elements"]:
            el["url"] = url
            el["timestamp_ms"] = ts

        return {
            "total_matches": raw["total"],
            "elements": raw["elements"],
        }

    async def _query_by_text_pseudo(
        self,
        selector: str,
        parent_pick: Pick | None,
        limit: int,
        url: str,
        ts: int,
    ) -> dict[str, Any]:
        """Handle __text__:<text> and __text_role__:<text>|<role> pseudo-selectors.

        Routes to Playwright get_by_text / get_by_role for AND-semantics.
        parent_pick scoping: get all handles from page, then filter to those that
        are descendants of the parent element handle.
        """
        from playwright.async_api import Locator

        if selector.startswith("__text_role__:"):
            rest = selector[len("__text_role__:") :]
            text, role = rest.split("|", 1)
            locator: Locator = self._page.get_by_role(role, name=text, exact=True)  # type: ignore[arg-type]
        else:
            text = selector[len("__text__:") :]
            locator = self._page.get_by_text(text, exact=True)

        # Get all matching element handles
        all_handles = await locator.element_handles()
        total = len(all_handles)

        # Scope to parent subtree if needed
        if parent_pick is not None:
            parent_handle = await self._resolver.resolve(parent_pick)
            if parent_handle is None:
                raise StalePickError(f"parent pick {parent_pick.pick_id} no longer matches the DOM")
            # Filter: keep only handles that are descendants of parent_handle
            filtered = []
            for h in all_handles:
                is_descendant: bool = await parent_handle.evaluate("(parent, child) => parent.contains(child)", h)
                if is_descendant:
                    filtered.append(h)
            all_handles = filtered
            total = len(all_handles)

        capped = all_handles[:limit]
        elements: list[dict[str, Any]] = []
        for i, h in enumerate(capped):
            el_data = await self._handle_to_element_data(h, i)
            el_data["url"] = url
            el_data["timestamp_ms"] = ts
            elements.append(el_data)

        return {"total_matches": total, "elements": elements}

    # ── Dynamic field evaluation (for Inspector) ────────────────────────────

    async def evaluate_pick_dynamic_fields(
        self,
        pick: Pick,
        fields: list[str],
    ) -> dict[str, Any]:
        """Evaluate live dynamic fields for a single pick.

        Returns a dict with the requested fields populated from the live DOM.
        If the element is stale, returns ``{'error': 'stale_pick'}``.

        Requested fields are a subset of:
          visible, enabled, focused, checked, in_viewport
        """
        handle = await self._resolver.resolve(pick)
        if handle is None:
            return {"error": "stale_pick"}
        state = await dom_readers.read_state(handle)
        return {f: state.get(f) for f in fields if f in state}

    # ── Low-level escape-hatch (Schema 0.4.0) ──────────────────────────────

    async def eval_js(
        self,
        expression: str,
        pick_id_arg: Pick | None,
        mutating: bool,
    ) -> dict[str, Any]:
        handle = None
        if pick_id_arg is not None:
            handle = await self._resolver.resolve(pick_id_arg)
            if handle is None:
                return {"ok": False, "error": "stale_pick"}
        result = await browser_actions.eval_js(self._page, expression, handle)
        if result.get("ok") and mutating and self._analyzer is not None:
            self._analyzer.invalidate_snapshot()
        return result

    async def dom_patch(
        self,
        pick: Pick,
        operations: list[dict[str, Any]],
    ) -> dict[str, Any]:
        handle = await self._resolver.resolve(pick)
        if handle is None:
            return {"ok": False, "error": "stale_pick"}
        result = await browser_actions.dom_patch(operations, handle)
        # Always invalidate snapshot after dom_patch (spec: even if partial failure)
        if self._analyzer is not None:
            self._analyzer.invalidate_snapshot()
        return result

    async def pick_by_xpath_raw(
        self,
        xpath: str,
        parent_pick: Pick | None,
        limit: int,
    ) -> dict[str, Any]:
        parent_handle = None
        if parent_pick is not None:
            parent_handle = await self._resolver.resolve(parent_pick)
            if parent_handle is None:
                raise StalePickError(f"parent pick {parent_pick.pick_id} no longer matches the DOM")
        return await xpath_query.pick_by_xpath(self._page, xpath, parent_handle, limit)


__all__ = ["PlaywrightPageController"]
