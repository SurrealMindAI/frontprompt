"""Finders — snapshot-based element discovery.

All methods are async (to match PageAnalyzer interface) but they are
CPU-bound lxml operations — no I/O, no Playwright round-trips.

FindAmbiguousError and StaleAnchorError are raised to the caller
(PageAnalyzer / socket_server dispatch).

Scrapling isolation: only scrapling_bridge APIs used, no direct scrapling
imports (arch-test enforced).
"""

from __future__ import annotations

import time
from typing import Any
from uuid import uuid4

from frontprompt.analysis._impl.scrapling_bridge import (
    ElementMatch,
    ParsedDocument,
    find_by_regex,
    find_by_text,
    find_elements,
    find_similar_elements,
)
from frontprompt.analysis.types import FindResult

# ---------------------------------------------------------------------------
# Exceptions
# ---------------------------------------------------------------------------


class FindAmbiguousError(Exception):
    """Raised by find_one when more than one element matches the query."""

    def __init__(self, total_matches: int) -> None:
        super().__init__(f"find_one: ambiguous — {total_matches} matches found")
        self.total_matches = total_matches


class StaleAnchorError(Exception):
    """Raised by find_similar when the anchor pick's fingerprint cannot be located."""


# ---------------------------------------------------------------------------
# Pick construction helper
# ---------------------------------------------------------------------------


def _match_to_pick(match: ElementMatch, comment: str, url: str, color_index: int = 0) -> Any:
    """Convert an ElementMatch to a Pick, mirroring programmatic_picks.py pattern."""
    from frontprompt.state.state import ElementFingerprint, ElementRect, Pick, PickElement

    fp_dict = match.fingerprint_dict
    return Pick(
        pick_id=str(uuid4()),
        url=url,
        timestamp_ms=int(time.time() * 1000),
        element=PickElement(
            selector=match.css_selector,
            fingerprint=ElementFingerprint(**fp_dict),
            text_snippet=(match.text_content or "")[:120],
            rect=ElementRect(
                x=match.rect.get("x", 0.0),
                y=match.rect.get("y", 0.0),
                width=match.rect.get("width", 0.0),
                height=match.rect.get("height", 0.0),
            ),
        ),
        comment=comment,
        color_index=color_index,
    )


# ---------------------------------------------------------------------------
# Query dict conversion
# ---------------------------------------------------------------------------


def _query_to_dict(query: Any) -> dict[str, Any]:
    """Convert a FindQuery (Pydantic model OR dict) to a scrapling_bridge query dict.

    Supports both Pydantic model instances and raw dict forms (for testing).
    """
    if isinstance(query, dict):
        kind = query.get("kind", "")
    else:
        kind = getattr(query, "kind", "")

    if kind == "css":
        selector = query.get("selector") if isinstance(query, dict) else getattr(query, "selector", "")
        return {"css": selector}
    elif kind == "text":
        text = query.get("text") if isinstance(query, dict) else getattr(query, "text", "")
        role = query.get("role") if isinstance(query, dict) else getattr(query, "role", None)
        exact = query.get("exact", False) if isinstance(query, dict) else getattr(query, "exact", False)
        return {"text": text, "role": role, "exact": exact}
    elif kind == "regex":
        pattern = query.get("pattern") if isinstance(query, dict) else getattr(query, "pattern", "")
        field = query.get("field", "text") if isinstance(query, dict) else getattr(query, "field", "text")
        return {"regex": pattern, "field": field}
    elif kind == "label":
        label = query.get("label_text") if isinstance(query, dict) else getattr(query, "label_text", "")
        return {"label": label}
    elif kind == "role":
        role = query.get("role") if isinstance(query, dict) else getattr(query, "role", "")
        name = query.get("name") if isinstance(query, dict) else getattr(query, "name", None)
        return {"role": role, "name": name}
    else:
        # fallback: treat as CSS
        selector = query.get("selector", "") if isinstance(query, dict) else str(query)
        return {"css": selector}


def _run_query(doc: ParsedDocument, query_dict: dict[str, Any]) -> list[ElementMatch]:
    """Dispatch a query dict to the correct bridge function."""
    if "css" in query_dict:
        return find_elements(doc, {"css": query_dict["css"]})
    elif "text" in query_dict:
        return find_by_text(
            doc,
            text=query_dict["text"],
            role=query_dict.get("role"),
            exact=query_dict.get("exact", False),
            scope=None,
        )
    elif "regex" in query_dict:
        return find_by_regex(
            doc,
            pattern=query_dict["regex"],
            field=query_dict.get("field", "text"),
            scope=None,
        )
    else:
        return []


# ---------------------------------------------------------------------------
# Finders class
# ---------------------------------------------------------------------------


class Finders:
    """Element finders backed by ParsedDocument + scrapling_bridge.

    Instantiate with state_manager, url, snapshot_id, and (optionally) the
    Playwright Page. Each method accepts a ParsedDocument and returns Pick or
    FindResult.

    When ``page`` is provided, the rect on each resulting Pick is enriched via a
    Playwright ``query_selector`` + ``bounding_box`` round-trip using the
    :pyattr:`ElementMatch.unique_selector` (path-disambiguated, with
    nth-of-type for N>=2 same-tag siblings). This costs one Playwright RPC per
    match; for ``find_similar(max_results=50)`` that is up to 50 round-trips,
    sub-second on a local headful chromium.

    When ``page`` is ``None`` (e.g. in unit tests with parse_html only), the
    rect remains zeroed — the legacy behaviour.
    """

    def __init__(
        self,
        *,
        state_manager: Any,
        url: str,
        snapshot_id: str,
        page: Any = None,
    ) -> None:
        self._sm = state_manager
        self._url = url
        self._snapshot_id = snapshot_id
        self._page = page

    async def _try_fetch_rect(self, match: ElementMatch, pick: Any) -> None:
        """Resolve match.unique_selector via Playwright and copy the bounding box.

        Silent no-op when ``self._page`` is None, when the match has no
        unique_selector, when query_selector returns None, or when bounding_box
        raises. In any failure case the pick's pre-existing zeroed rect stays.
        """
        if self._page is None:
            return
        selector = match.unique_selector
        if not selector:
            return
        try:
            handle = await self._page.query_selector(selector)
            if handle is None:
                return
            box = await handle.bounding_box()
            if box is None:
                return
            pick.element.rect.x = float(box.get("x", 0.0))
            pick.element.rect.y = float(box.get("y", 0.0))
            pick.element.rect.width = float(box.get("width", 0.0))
            pick.element.rect.height = float(box.get("height", 0.0))
        except Exception:
            return

    async def find_one(
        self,
        doc: ParsedDocument,
        query: Any,
        comment: str,
        parent_match: ElementMatch | None = None,
    ) -> Any | None:
        """Find exactly one element. Returns Pick or None. Raises FindAmbiguousError if N > 1."""
        query_dict = _query_to_dict(query)
        if parent_match is not None and "css" in query_dict:
            # Scope the CSS query to parent's subtree
            scope_sel = parent_match.css_selector
            query_dict = {"css": f"{scope_sel} {query_dict['css']}"}
        matches = _run_query(doc, query_dict)
        if len(matches) == 0:
            return None
        if len(matches) > 1:
            raise FindAmbiguousError(total_matches=len(matches))
        pick = _match_to_pick(matches[0], comment, self._url)
        await self._try_fetch_rect(matches[0], pick)
        await self._sm.add_pick_from_programmatic_source(pick)
        return pick

    async def find_first(
        self,
        doc: ParsedDocument,
        query: Any,
        comment: str,
        parent_match: ElementMatch | None = None,
    ) -> tuple[Any, int] | None:
        """Find the first element. Returns (pick, total_matches) or None."""
        query_dict = _query_to_dict(query)
        if parent_match is not None and "css" in query_dict:
            scope_sel = parent_match.css_selector
            query_dict = {"css": f"{scope_sel} {query_dict['css']}"}
        matches = _run_query(doc, query_dict)
        if not matches:
            return None
        pick = _match_to_pick(matches[0], comment, self._url)
        await self._try_fetch_rect(matches[0], pick)
        await self._sm.add_pick_from_programmatic_source(pick)
        return pick, len(matches)

    async def find_by_text(
        self,
        doc: ParsedDocument,
        text: str,
        role: str | None,
        comment: str,
        limit: int,
        parent_match: ElementMatch | None,
    ) -> FindResult:
        """Find all elements containing text (case-insensitive substring).

        Creates picks for up to `limit` matches but reports total_matches.
        role AND-filters to matching ARIA role or tag.
        """
        all_matches = find_by_text(doc, text=text, role=None, exact=False, scope=parent_match)

        # Role filter: match role attribute OR tag
        if role:
            all_matches = [m for m in all_matches if m.attributes.get("role") == role or m.tag == role]

        total = len(all_matches)
        to_persist = all_matches[:limit]
        pick_ids = []
        for i, match in enumerate(to_persist):
            pick = _match_to_pick(match, comment, self._url, color_index=i)
            await self._try_fetch_rect(match, pick)
            await self._sm.add_pick_from_programmatic_source(pick)
            pick_ids.append(pick.pick_id)

        return FindResult(
            pick_ids=pick_ids,
            total_matches=total,
            captured=len(to_persist),
        )

    async def find_by_regex(
        self,
        doc: ParsedDocument,
        pattern: str,
        field: str,
        comment: str,
        limit: int,
        parent_match: ElementMatch | None,
    ) -> FindResult:
        """Find elements whose text (or attribute) matches a regex pattern."""
        all_matches = find_by_regex(doc, pattern=pattern, field=field, scope=parent_match)
        total = len(all_matches)
        to_persist = all_matches[:limit]
        pick_ids = []
        for i, match in enumerate(to_persist):
            pick = _match_to_pick(match, comment, self._url, color_index=i)
            await self._try_fetch_rect(match, pick)
            await self._sm.add_pick_from_programmatic_source(pick)
            pick_ids.append(pick.pick_id)

        return FindResult(
            pick_ids=pick_ids,
            total_matches=total,
            captured=len(to_persist),
        )

    async def find_similar(
        self,
        doc: ParsedDocument,
        anchor_fingerprint: dict[str, Any],
        threshold: float,
        max_results: int,
        comment: str,
    ) -> FindResult:
        """Find elements structurally similar to the anchor fingerprint.

        Raises StaleAnchorError if no matches found at threshold.
        """
        all_matches = find_similar_elements(
            doc,
            anchor_fingerprint=anchor_fingerprint,
            threshold=threshold,
            max_results=max_results,
        )
        if not all_matches and threshold > 0.0:
            raise StaleAnchorError(f"find_similar: anchor fingerprint not found at threshold {threshold}")
        pick_ids = []
        for i, match in enumerate(all_matches):
            pick = _match_to_pick(match, comment, self._url, color_index=i)
            await self._try_fetch_rect(match, pick)
            await self._sm.add_pick_from_programmatic_source(pick)
            pick_ids.append(pick.pick_id)

        return FindResult(
            pick_ids=pick_ids,
            total_matches=len(all_matches),
            captured=len(all_matches),
        )
