"""FakePageController + FakePageAnalyzer — in-memory test doubles.

Implements the full PageController Protocol (as extended by sub-plan 01).
Deterministic, no Playwright dependency, safe for unit tests.
"""

from __future__ import annotations

from typing import Any

from frontprompt.ipc.playwright_controller.element_resolver import StalePickError
from frontprompt.state.state import Pick


class FakePageController:
    """In-memory PageController test double.

    Attributes:
        selector_matches: Maps CSS selector strings to lists of element descriptor
            dicts. ``query_selector_all`` looks up the selector here.
        stale_picks: Set of pick_ids to treat as stale. Reader methods return
            ``{"error": "stale_pick", "pick_id": pid}`` for these picks.
            ``query_selector_all`` raises ``StalePickError`` when
            ``parent_pick.pick_id`` is in this set.
        text_responses: Per pick_id overrides for ``get_text``.
        navigations: Records all ``navigate(url)`` calls.
        scrolls: Records all ``scroll_to(pick)`` calls.
    """

    def __init__(self) -> None:
        self.selector_matches: dict[str, list[dict[str, Any]]] = {}
        self.stale_picks: set[str] = set()
        self.text_responses: dict[str, dict[str, Any]] = {}
        self.navigations: list[str] = []
        self.scrolls: list[str] = []
        self.eval_js_responses: dict[str, dict[str, Any]] = {}
        """Maps expression strings to deterministic return values for eval_js."""
        self.dom_patch_responses: dict[str, dict[str, Any]] = {}
        """Maps pick_id strings to deterministic dom_patch results."""
        self.xpath_matches: dict[str, list[dict[str, Any]]] = {}
        """Maps XPath strings to element descriptor lists for pick_by_xpath_raw."""
        # call-recording lists for dispatch tests
        self.eval_js_calls: list[tuple[str, Pick | None, bool]] = []
        self.dom_patch_calls: list[tuple[str, list[dict[str, Any]]]] = []

    # ── Pick-creators ──────────────────────────────────────────────────────────

    async def query_selector_all(
        self,
        selector: str,
        parent_pick: Pick | None,
        limit: int,
    ) -> dict[str, Any]:
        """Signature takes a pre-resolved Pick object (not pick_id string).

        Raises StalePickError if parent_pick is stale (fingerprint mismatch).
        Returns total_matches + elements capped to limit.
        """
        if parent_pick is not None and parent_pick.pick_id in self.stale_picks:
            raise StalePickError(parent_pick.pick_id)
        elements = self.selector_matches.get(selector, [])
        total = len(elements)
        return {
            "total_matches": total,
            "elements": elements[:limit],
        }

    # ── Navigation ─────────────────────────────────────────────────────────────

    async def navigate(self, url: str) -> dict[str, Any]:
        self.navigations.append(url)
        return {"navigated_to": url, "title": "Fake Page"}

    # ── Element-readers ────────────────────────────────────────────────────────

    async def get_text(self, picks: list[Pick]) -> list[dict[str, Any]]:
        results = []
        for pick in picks:
            if pick.pick_id in self.stale_picks:
                results.append({"error": "stale_pick", "pick_id": pick.pick_id})
                continue
            if pick.pick_id in self.text_responses:
                results.append(self.text_responses[pick.pick_id])
            else:
                results.append(
                    {
                        "pick_id": pick.pick_id,
                        "text": pick.element.text_snippet,
                        "accessible_name": pick.element.text_snippet,
                        "role": "generic",
                        "is_visible": True,
                        "is_enabled": True,
                        "is_focused": False,
                    }
                )
        return results

    async def get_html(self, picks: list[Pick], max_chars: int) -> list[dict[str, Any]]:
        results = []
        for pick in picks:
            if pick.pick_id in self.stale_picks:
                results.append({"error": "stale_pick", "pick_id": pick.pick_id})
                continue
            html = f"<div id='{pick.pick_id}'>{pick.element.text_snippet}</div>"
            truncated = len(html) > max_chars
            results.append(
                {
                    "pick_id": pick.pick_id,
                    "html": html[:max_chars],
                    "truncated": truncated,
                }
            )
        return results

    async def get_attributes(self, picks: list[Pick]) -> list[dict[str, Any]]:
        results = []
        for pick in picks:
            if pick.pick_id in self.stale_picks:
                results.append({"error": "stale_pick", "pick_id": pick.pick_id})
                continue
            results.append(
                {
                    "pick_id": pick.pick_id,
                    "attributes": {"id": pick.pick_id, "class": "fake-element"},
                }
            )
        return results

    async def get_state(self, picks: list[Pick]) -> list[dict[str, Any]]:
        results = []
        for pick in picks:
            if pick.pick_id in self.stale_picks:
                results.append({"error": "stale_pick", "pick_id": pick.pick_id})
                continue
            results.append(
                {
                    "pick_id": pick.pick_id,
                    "visible": True,
                    "enabled": True,
                    "checked": False,
                    "focused": False,
                    "in_viewport": True,
                }
            )
        return results

    async def get_outline(self, picks: list[Pick], max_depth: int, max_nodes: int) -> list[dict[str, Any]]:
        results = []
        for pick in picks:
            if pick.pick_id in self.stale_picks:
                results.append({"error": "stale_pick", "pick_id": pick.pick_id})
                continue
            results.append(
                {
                    "pick_id": pick.pick_id,
                    "outline": {"tag": "div", "children": []},
                }
            )
        return results

    async def screenshot_element(self, picks: list[Pick], padding: int) -> list[dict[str, Any]]:
        results = []
        for pick in picks:
            if pick.pick_id in self.stale_picks:
                results.append({"error": "stale_pick", "pick_id": pick.pick_id})
                continue
            results.append(
                {
                    "pick_id": pick.pick_id,
                    "image_base64": "ZmFrZQ==",  # base64("fake")
                    "format": "png",
                    "width": 100,
                    "height": 30,
                }
            )
        return results

    # ── Page-level ─────────────────────────────────────────────────────────────

    async def get_page_info(self) -> dict[str, Any]:
        return {
            "url": "https://example.com/",
            "title": "Fake Page",
            "viewport": {"width": 1280, "height": 720},
            "scroll": {"x": 0.0, "y": 0.0},
            "ready_state": "complete",
        }

    async def screenshot_page(self, full_page: bool) -> dict[str, Any]:
        return {
            "image_base64": "ZmFrZQ==",
            "format": "png",
            "width": 1280,
            "height": 720 if not full_page else 2000,
        }

    async def scroll_to(self, pick: Pick) -> dict[str, Any]:
        self.scrolls.append(pick.pick_id)
        return {
            "is_in_viewport": True,
            "scroll_x": 0.0,
            "scroll_y": 0.0,
        }

    # ── Low-level escape-hatch (Schema 0.4.0) ─────────────────────────────────

    async def eval_js(
        self,
        expression: str,
        pick_id_arg: Pick | None,
        mutating: bool,
    ) -> dict[str, Any]:
        # adds call-recording on top of the base dispatch logic
        self.eval_js_calls.append((expression, pick_id_arg, mutating))
        if expression in self.eval_js_responses:
            return self.eval_js_responses[expression]
        return {"result": None, "ok": True}

    async def dom_patch(
        self,
        pick: Pick,
        operations: list[dict[str, Any]],
    ) -> dict[str, Any]:
        # adds call-recording on top of the base dispatch logic
        self.dom_patch_calls.append((pick.pick_id, operations))
        if pick.pick_id in self.stale_picks:
            return {"ok": False, "error": "stale_pick"}
        if pick.pick_id in self.dom_patch_responses:
            return self.dom_patch_responses[pick.pick_id]
        results = [{"op": op.get("op", ""), "ok": True} for op in operations]
        return {"ok": True, "results": results}

    async def pick_by_xpath_raw(
        self,
        xpath: str,
        parent_pick: Pick | None,
        limit: int,
    ) -> dict[str, Any]:
        if parent_pick is not None and parent_pick.pick_id in self.stale_picks:
            raise StalePickError(parent_pick.pick_id)
        elements = self.xpath_matches.get(xpath, [])
        total = len(elements)
        return {
            "total_matches": total,
            "elements": elements[:limit],
        }


class FakePageAnalyzer:
    """In-memory PageAnalyzer test double for socket_server dispatch tests."""

    def __init__(self) -> None:
        self.call_count: int = 0
        self.snapshot_invalidated: bool = False
        self.outline_result: dict[str, Any] = {
            "snapshot_id": "snap-1",
            "title": "Fake Page",
            "url": "https://fake.example/",
            "headings": [],
            "links": [],
            "buttons": [],
            "inputs": [],
            "forms": [],
            "landmarks": [],
        }
        self.condensed_html_result: str = "<main>fake</main>"
        self.find_one_result: dict[str, Any] | None = {"pick_id": "fake-pick-1"}
        self.find_first_result: dict[str, Any] | None = {
            "pick_id": "fake-pick-1",
            "total_matches": 1,
        }
        self.find_result: dict[str, Any] = {
            "pick_ids": ["fake-pick-1"],
            "total_matches": 1,
            "captured": 1,
        }
        self.context_result: dict[str, Any] = {
            "ancestors": [],
            "prev_sibling": None,
            "next_sibling": None,
            "in_form": False,
            "in_table": False,
            "semantic_landmark": None,
        }
        self.path_result: list[dict[str, Any]] = [{"tag": "body", "role": None, "text_excerpt": None}]
        self.relocate_result: list[dict[str, Any]] = []
        self.inspect_result: list[dict[str, Any]] = []
        self.pick_from_ref_result: dict[str, Any] | None = None
        self._known_refs: dict[str, str] = {}  # ref_id -> pick_id

    def _track(self) -> None:
        self.call_count += 1

    async def outline(self, options: Any = None) -> dict[str, Any]:
        self._track()
        return self.outline_result

    async def condensed_html(self, options: Any = None) -> dict[str, Any]:
        self._track()
        return {
            "html": self.condensed_html_result,
            "truncated": False,
            "original_chars": 100,
            "stripped_chars": 80,
        }

    async def find_one(self, query: Any, comment: str, parent_pick: Any = None) -> dict[str, Any] | None:
        self._track()
        return self.find_one_result

    async def find_first(self, query: Any, comment: str, parent_pick: Any = None) -> dict[str, Any] | None:
        self._track()
        return self.find_first_result

    async def find_by_text(self, text: str, role: Any, parent_pick: Any, comment: str, limit: int) -> dict[str, Any]:
        self._track()
        return self.find_result

    async def find_by_regex(
        self, pattern: str, field: str, parent_pick: Any, comment: str, limit: int
    ) -> dict[str, Any]:
        self._track()
        return self.find_result

    async def find_similar(self, anchor_pick: Any, threshold: float, max_results: int, comment: str) -> dict[str, Any]:
        self._track()
        return self.find_result

    async def context(self, pick: Any, levels_up: int, sibling_radius: int) -> dict[str, Any]:
        self._track()
        return self.context_result

    async def path(self, pick: Any) -> list[dict[str, Any]]:
        self._track()
        return self.path_result

    async def pick_from_ref(self, ref_id: str, snapshot_id: str, comment: str) -> dict[str, Any]:
        self._track()
        if ref_id in self._known_refs:
            return {"pick_id": self._known_refs[ref_id]}
        return {"error": "ref_expired"}

    async def relocate(self, picks: list[Any]) -> list[dict[str, Any]]:
        self._track()
        return [{"pick_id": p.pick_id, "status": "alive"} for p in picks]

    async def inspect(self, picks: list[Any], fields: list[str]) -> list[dict[str, Any]]:
        self._track()
        return [
            {
                "pick_id": p.pick_id,
                "text": "fake-text",
                "role": "generic",
                "visible": True,
                "enabled": True,
            }
            for p in picks
        ]

    def invalidate_snapshot(self) -> None:
        self.snapshot_invalidated = True


__all__ = ["FakePageAnalyzer", "FakePageController"]
