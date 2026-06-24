"""ElementResolver — pick → ElementHandle with fingerprint-stale-detection.

Each MCP tool that operates on picks starts with resolver.resolve(pick).
If the pick's CSS selector no longer matches anything, or matches an element
whose fingerprint differs from the pick's snapshot, returns None (= stale_pick).

The fingerprint verify protects against selector-collision (same selector,
different element) — the core guarantee of the ground-truth pattern.

Optional analyzer fallback (Schema 0.4.0): when a PageAnalyzer is provided,
failed primary lookups are delegated to analyzer.relocate() for adaptive
re-resolution. Zero behaviour change when no analyzer is given.
"""

from __future__ import annotations

from typing import TYPE_CHECKING

from playwright.async_api import ElementHandle, Page

from frontprompt.state.state import Pick

if TYPE_CHECKING:
    from frontprompt.analysis.analyzer import PageAnalyzer


class StalePickError(Exception):
    """Raised by callers that prefer exception over None-return (pick-creators)."""


class ElementResolver:
    def __init__(
        self,
        page: Page,
        analyzer: PageAnalyzer | None = None,
    ) -> None:
        self._page = page
        self._analyzer = analyzer

    async def resolve(self, pick: Pick) -> ElementHandle | None:
        """Returns ElementHandle if selector resolves AND fingerprint matches, else None.

        When an ``analyzer`` was provided at construction time and the CSS lookup
        fails, delegates one-shot adaptive relocation to ``analyzer.relocate``.
        This is opt-in — default behaviour (no analyzer) is unchanged.
        """
        handle = await self._page.query_selector(pick.element.selector)
        if handle is not None and await self._fingerprint_matches(handle, pick):
            return handle
        # Primary lookup failed — try analyzer-based relocation if available
        if self._analyzer is not None:
            results = await self._analyzer.relocate([pick])
            if results and results[0].status in ("alive", "recovered"):
                # Re-resolve using the (potentially updated) selector from relocation
                recovered_pick = results[0].pick if hasattr(results[0], "pick") else pick
                new_handle = await self._page.query_selector(recovered_pick.element.selector)
                if new_handle is not None:
                    return new_handle
        return None

    async def _fingerprint_matches(self, handle: ElementHandle, pick: Pick) -> bool:
        live = await handle.evaluate(
            """(el) => ({
                tag: el.tagName.toLowerCase(),
                classes: Array.from(el.classList),
                text: (el.textContent || '').trim().slice(0, 60),
            })"""
        )
        snap = pick.element.fingerprint
        if live["tag"] != snap.tag:
            return False
        snap_classes = set(snap.attributes.get("class", "").split()) if snap.attributes.get("class") else set()
        if set(live["classes"]) != snap_classes:
            return False
        if live["text"] != (snap.text or "").strip()[:60]:
            return False
        return True


__all__ = ["ElementResolver", "StalePickError"]
