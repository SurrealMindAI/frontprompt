"""Relocator — adaptive pick relocation after DOM drift.

Two-stage strategy:
  1. CSS selector lookup — if match found, check fingerprint similarity.
  2. scrapling relocate_element fallback — fingerprint-similarity search.

All scrapling_bridge — no direct scrapling imports (arch-test enforced).
Synchronous: lxml queries, no async I/O.
"""

from __future__ import annotations

from frontprompt.analysis._impl.scrapling_bridge import (
    ParsedDocument,
    find_elements,
    fingerprint_similarity,
    relocate_element,
)
from frontprompt.analysis.types import RelocationResult
from frontprompt.state.state import Pick

_ALIVE_THRESHOLD = 0.9
_RECOVERED_THRESHOLD = 0.7


class Relocator:
    """Stateless relocator — instantiate once, reuse."""

    def relocate(self, doc: ParsedDocument, picks: list[Pick]) -> list[RelocationResult]:
        return [self._relocate_one(doc, pick) for pick in picks]

    def _relocate_one(self, doc: ParsedDocument, pick: Pick) -> RelocationResult:
        fp_dict = pick.element.fingerprint.model_dump()
        css_matches = find_elements(doc, {"css": pick.element.selector})

        if css_matches:
            match = css_matches[0]
            sim = fingerprint_similarity(match, fp_dict)
            if sim >= _ALIVE_THRESHOLD:
                return RelocationResult(
                    pick_id=pick.pick_id,
                    status="alive",
                    new_selector=match.css_selector,
                    similarity=sim,
                )
            if sim >= _RECOVERED_THRESHOLD:
                return RelocationResult(
                    pick_id=pick.pick_id,
                    status="recovered",
                    new_selector=match.css_selector,
                    similarity=sim,
                )
            # sim < 0.7 but CSS still resolves — element found, treat as recovered
            return RelocationResult(
                pick_id=pick.pick_id,
                status="recovered",
                new_selector=match.css_selector,
                similarity=sim,
            )

        # CSS failed — try scrapling relocate fallback
        fallback = relocate_element(doc, fp_dict)
        if fallback is not None:
            fb_sim = fingerprint_similarity(fallback, fp_dict)
            if fb_sim >= _RECOVERED_THRESHOLD:
                return RelocationResult(
                    pick_id=pick.pick_id,
                    status="recovered",
                    new_selector=fallback.css_selector,
                    similarity=fb_sim,
                )

        return RelocationResult(pick_id=pick.pick_id, status="stale")
