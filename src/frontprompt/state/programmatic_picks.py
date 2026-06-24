"""ProgrammaticPickService — agent-side pick creation via selector/text queries.

Orchestrates PageController (browser side) and StateManager (state side) under
single-writer discipline. The state write happens inside
StateManager.add_pick_from_programmatic_source (lock-guarded).

Failure modes:
  - parent_pick_id stale → StalePickError propagates up (hard fail, no picks created)
  - 0 selector matches → returns {pick_ids: [], total_matches: 0, captured: 0} (not an error)
  - total > limit → captured=limit, total_matches=N (agent sees the difference)
  - comment auto-suffixed "[match i/N]" where N=total_matches
"""

from __future__ import annotations

import time
from typing import TYPE_CHECKING, Any
from uuid import uuid4

from frontprompt.ipc.page_controller import PageController
from frontprompt.state.manager import StateManager
from frontprompt.state.state import ElementFingerprint, ElementRect, Pick, PickElement

if TYPE_CHECKING:
    from frontprompt.analysis.analyzer import PageAnalyzer


class ProgrammaticPickService:
    def __init__(
        self,
        state_manager: StateManager,
        page_controller: PageController,
        analyzer: PageAnalyzer | None = None,
    ) -> None:
        self._mgr = state_manager
        self._pc = page_controller
        self._analyzer = analyzer

    async def pick_by_selector(
        self,
        selector: str,
        comment: str,
        parent_pick: Pick | None,
        limit: int,
    ) -> dict[str, Any]:
        # takes pre-resolved Pick (not pick_id string).
        # Raises StalePickError if parent_pick is stale (propagates to caller).
        result = await self._pc.query_selector_all(
            selector=selector,
            parent_pick=parent_pick,
            limit=limit,
        )
        total = result["total_matches"]
        elements = result["elements"]  # already capped to limit by PageController
        captured = len(elements)
        pick_ids: list[str] = []
        for idx, el_data in enumerate(elements, start=1):
            suffixed = f"{comment} [match {idx}/{total}]"
            pick = _build_pick_from_element_data(el_data, suffixed)
            await self._mgr.add_pick_from_programmatic_source(pick)
            pick_ids.append(pick.pick_id)
        return {"pick_ids": pick_ids, "total_matches": total, "captured": captured}

    async def pick_by_text(
        self,
        text: str,
        role: str | None,
        comment: str,
        parent_pick: Pick | None,
        limit: int,
    ) -> dict[str, Any]:
        # When role is specified, fall back to the legacy Playwright path which uses
        # get_by_role(role, name=text) and can match accessible names (aria-label).
        # The PageAnalyzer find_by_text only searches text content, not accessible names.
        if self._analyzer is not None and role is None:
            return await self._pick_by_text_via_analyzer(text, role, comment, parent_pick, limit)
        # Legacy path: role-based search or analyzer not wired
        return await self._pick_by_text_legacy(text, role, comment, parent_pick, limit)

    async def _pick_by_text_via_analyzer(
        self,
        text: str,
        role: str | None,
        comment: str,
        parent_pick: Pick | None,
        limit: int,
    ) -> dict[str, Any]:
        """FindResult has .pick_ids (not .picks); find_by_text already
        persists the picks via state_manager. Just return the result directly.

        Post-condition stale-rejection deferred to Phase-2 (would require a
        state_manager.remove_pick API which doesn't exist yet).
        """
        assert self._analyzer is not None
        find_result = await self._analyzer.find_by_text(
            text=text,
            role=role,
            parent_pick=parent_pick,
            comment=comment,
            limit=limit,
        )
        # FindResult has pick_ids: list[str], total_matches: int, captured: int
        # find_by_text inside Finders already calls state_manager.add_pick_from_programmatic_source
        return {
            "pick_ids": find_result.pick_ids,
            "total_matches": find_result.total_matches,
            "captured": find_result.captured,
        }

    async def _pick_by_text_legacy(
        self,
        text: str,
        role: str | None,
        comment: str,
        parent_pick: Pick | None,
        limit: int,
    ) -> dict[str, Any]:
        """Original impl kept for unit tests that don't wire an analyzer."""
        result = await self._pc.query_selector_all(
            selector=_text_pseudo_selector(text, role),
            parent_pick=parent_pick,
            limit=limit,
        )
        total = result["total_matches"]
        elements = result["elements"]
        captured = len(elements)
        pick_ids: list[str] = []
        for idx, el_data in enumerate(elements, start=1):
            suffixed = f"{comment} [match {idx}/{total}]"
            pick = _build_pick_from_element_data(el_data, suffixed)
            await self._mgr.add_pick_from_programmatic_source(pick)
            pick_ids.append(pick.pick_id)
        return {"pick_ids": pick_ids, "total_matches": total, "captured": captured}

    # ── new method for pick_by_xpath dispatch ──────────────────────

    async def pick_from_xpath_elements(
        self,
        elements_result: dict[str, Any],
        comment: str,
    ) -> dict[str, Any]:
        """Materialize Picks from a pick_by_xpath_raw result.

        Mirrors pick_by_selector's element-building path. The xpath query
        runs in PlaywrightPageController.pick_by_xpath_raw (low-level, raw
        element data), and this method persists the results as Picks.

        Args:
            elements_result: dict with keys {"total_matches": int,
                                              "elements": list[dict]}
                              (same shape as query_selector_all returns)
            comment: base comment, auto-suffixed per match

        Returns:
            {"pick_ids": list[str], "total_matches": int, "captured": int}
        """
        total = elements_result["total_matches"]
        elements = elements_result["elements"]
        captured = len(elements)
        pick_ids: list[str] = []
        for idx, el_data in enumerate(elements, start=1):
            suffixed = f"{comment} [match {idx}/{total}]"
            pick = _build_pick_from_element_data(el_data, suffixed)
            await self._mgr.add_pick_from_programmatic_source(pick)
            pick_ids.append(pick.pick_id)
        return {"pick_ids": pick_ids, "total_matches": total, "captured": captured}


def _text_pseudo_selector(text: str, role: str | None) -> str:
    """Build a pseudo-selector key used by PlaywrightPageController.query_selector_all.

    The key encodes both text and optional role so the concrete Playwright impl
    can use page.get_by_role(role, name=text) for AND-semantics. The FakePageController
    uses this string as-is as a dict key in selector_matches.
    """
    if role:
        return f"__text_role__:{text}|{role}"
    return f"__text__:{text}"


def _build_pick_from_element_data(el_data: dict[str, Any], comment: str) -> Pick:
    return Pick(
        pick_id=str(uuid4()),
        url=el_data.get("url", ""),
        timestamp_ms=el_data.get("timestamp_ms", int(time.time() * 1000)),
        element=PickElement(
            selector=el_data["selector"],
            fingerprint=ElementFingerprint(**el_data["fingerprint"]),
            text_snippet=el_data.get("text_snippet", ""),
            rect=ElementRect(**el_data["rect"]),
        ),
        comment=comment,
        color_index=el_data.get("color_index", 0),
    )


__all__ = ["ProgrammaticPickService"]
