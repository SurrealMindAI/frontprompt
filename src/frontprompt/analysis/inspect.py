"""Inspector — hybrid static (snapshot) + dynamic (live page) element inspection.

Static fields: lxml-based from ParsedDocument — no I/O, synchronous.
Dynamic fields: delegated to PageController.evaluate_pick_dynamic_fields — async.

Split design: inspect_static + inspect_dynamic compose into inspect().
Scrapling isolation: no direct scrapling imports (arch-test enforced).

Note: STATIC_FIELDS and DYNAMIC_FIELDS are scoped to what InspectResult supports.
      See analysis/types.py InspectResult for the authoritative field list.
"""

from __future__ import annotations

from typing import Any

from frontprompt.analysis._impl.scrapling_bridge import ParsedDocument, find_elements
from frontprompt.analysis.types import InspectResult
from frontprompt.state.state import Pick

# Fields that can be extracted from the static parsed document (lxml/scrapling)
STATIC_FIELDS: frozenset[str] = frozenset({"text", "accessible_name", "role", "attributes", "html", "outline"})

# Fields that require a live page evaluation via PageController
DYNAMIC_FIELDS: frozenset[str] = frozenset({"visible", "enabled", "focused", "checked", "in_viewport"})


class Inspector:
    """Stateless inspector — instantiate once, reuse."""

    def inspect_static(self, doc: ParsedDocument, picks: list[Pick], fields: list[str]) -> list[InspectResult]:
        """Extract static fields from the parsed document for each pick."""
        results: list[InspectResult] = []
        requested = frozenset(fields) & STATIC_FIELDS
        for pick in picks:
            matches = find_elements(doc, {"css": pick.element.selector})
            if not matches:
                results.append(InspectResult(pick_id=pick.pick_id, error="stale_pick"))
                continue
            match = matches[0]
            result = InspectResult(pick_id=pick.pick_id)
            if "text" in requested:
                result.text = match.text_content or ""
            if "role" in requested:
                result.role = match.attributes.get("role") or match.tag
            if "accessible_name" in requested:
                # accessible name: aria-label > title > text content
                result.accessible_name = (
                    match.attributes.get("aria-label") or match.attributes.get("title") or match.text_content or ""
                )
            if "attributes" in requested:
                result.attributes = dict(match.attributes)
            if "html" in requested:
                result.html = match.outer_html
            if "outline" in requested:
                # outline: summary dict of key element properties
                result.outline = {
                    "tag": match.tag,
                    "id": match.attributes.get("id"),
                    "class": match.attributes.get("class"),
                    "text_excerpt": (match.text_content or "")[:80],
                }
            results.append(result)
        return results

    async def inspect_dynamic(
        self,
        doc: ParsedDocument,
        picks: list[Pick],
        fields: list[str],
        page_controller: Any,
    ) -> list[InspectResult]:
        """Evaluate dynamic fields for each pick via page_controller."""
        results: list[InspectResult] = []
        requested = list(frozenset(fields) & DYNAMIC_FIELDS)
        for pick in picks:
            dyn = await page_controller.evaluate_pick_dynamic_fields(pick, requested)
            result = InspectResult(pick_id=pick.pick_id)
            if "error" in dyn and dyn["error"] == "stale_pick":
                result.error = "stale_pick"
            else:
                for field in requested:
                    if field in dyn:
                        setattr(result, field, dyn[field])
            results.append(result)
        return results

    async def inspect(
        self,
        doc: ParsedDocument,
        picks: list[Pick],
        fields: list[str],
        page_controller: Any,
    ) -> list[InspectResult]:
        """Inspect picks — split fields into static/dynamic, merge per pick."""
        static_fields = [f for f in fields if f in STATIC_FIELDS]
        dynamic_fields = [f for f in fields if f in DYNAMIC_FIELDS]

        static_results = (
            self.inspect_static(doc, picks, static_fields)
            if static_fields
            else [InspectResult(pick_id=p.pick_id) for p in picks]
        )
        dynamic_results = (
            await self.inspect_dynamic(doc, picks, dynamic_fields, page_controller)
            if dynamic_fields
            else [InspectResult(pick_id=p.pick_id) for p in picks]
        )

        merged: list[InspectResult] = []
        for s_res, d_res in zip(static_results, dynamic_results, strict=False):
            if s_res.error == "stale_pick" or d_res.error == "stale_pick":
                merged.append(InspectResult(pick_id=s_res.pick_id, error="stale_pick"))
                continue
            # Overlay dynamic fields onto static result.
            # Always set the field (even if None) so exclude_unset serialization
            # includes explicitly-requested fields like checked=None for h1.
            for field in dynamic_fields:
                val = getattr(d_res, field, None)
                setattr(s_res, field, val)
            merged.append(s_res)
        return merged
