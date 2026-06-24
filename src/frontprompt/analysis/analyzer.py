"""PageAnalyzer — high-level page-analysis service.

Snapshots the live DOM via Playwright's page.content(), parses it with
the scrapling bridge (TIER 2), and exposes a pick-domain API.

All methods that are not implemented here are stubs raising NotImplementedError.
They will be filled in by a later high-level-methods iteration.

Constructor dependencies:
    page         — Playwright Page object (anyio-compatible)
    resolver     — ElementResolver (for pick → live ElementHandle lookups)
    state_manager — StateManager (for pick registration / lookup)
    snapshot_ttl_seconds — TTL for parsed snapshot caching (default 30s)
"""

from __future__ import annotations

from typing import TYPE_CHECKING, Any, Literal

if TYPE_CHECKING:
    from frontprompt.analysis.finders import Finders
    from frontprompt.state.state import Pick

from frontprompt.analysis.snapshot import PageSnapshot
from frontprompt.analysis.types import (
    CondensedHtml,
    CondensedHtmlOptions,
    ElementContext,
    FindQuery,
    FindResult,
    InspectField,
    InspectResult,
    OutlineOptions,
    OutlineRef,
    PageOutline,
    PathSegment,
    RelocationResult,
)


class PageAnalyzer:
    """High-level page-analysis service.

    Snapshots the live DOM, runs rich queries, returns Picks.
    Underlying technology (Scrapling/lxml) is implementation-detail.
    """

    def __init__(
        self,
        page: Any,
        resolver: Any,
        state_manager: Any,
        snapshot_ttl_seconds: float = 30.0,
        page_controller: Any = None,
    ) -> None:
        self._page = page
        self._resolver = resolver
        self._state_manager = state_manager
        self._snapshot_ttl_seconds = snapshot_ttl_seconds
        self._current_snapshot: PageSnapshot | None = None
        self._page_controller: Any = page_controller  # for hybrid inspect

    # ── Snapshot lifecycle ─────────────────────────────────────────────────────

    async def snapshot(self, fresh: bool = False) -> PageSnapshot:
        """Return the current snapshot, refreshing if expired or forced.

        Args:
            fresh: If True, always fetch a new snapshot regardless of TTL.
        """
        if self._current_snapshot is None or self._current_snapshot.is_expired or fresh:
            html: str = await self._page.content()
            # capture url (sync property) + title (async) at snapshot-time
            url: str = self._page.url
            try:
                title: str = await self._page.title()
            except Exception:
                title = ""
            from frontprompt.analysis._impl.scrapling_bridge import parse_html

            parsed_doc = parse_html(html)
            self._current_snapshot = PageSnapshot(
                html=html,
                parsed_document=parsed_doc,
                ttl_seconds=self._snapshot_ttl_seconds,
                url=url,
                title=title,
            )
        return self._current_snapshot

    def invalidate_snapshot(self) -> None:
        """Discard the cached snapshot. Next call to snapshot() fetches fresh."""
        self._current_snapshot = None

    # ── Outline + condensed read ───────────────────────────────────────────────

    async def outline(self, options: OutlineOptions | None = None) -> PageOutline:
        """Build a structural outline from the current snapshot."""
        from frontprompt.analysis.outline import OutlineBuilder

        snap = await self.snapshot()
        opts = options or OutlineOptions()
        return OutlineBuilder().build_outline(
            snap.parsed_document,
            opts,
            snapshot_id=snap.snapshot_id,
            expires_at_ms=snap.expires_at_ms(),
            ref_table=snap.ref_table,
            url=snap.url,
            title=snap.title,
        )

    async def condensed_html(self, options: CondensedHtmlOptions | None = None) -> CondensedHtml:
        """Return cleaned/condensed HTML of the page."""
        from frontprompt.analysis._impl.scrapling_bridge import condensed_html as _condensed_html

        snap = await self.snapshot()
        opts = options or CondensedHtmlOptions()
        result_str = _condensed_html(snap.parsed_document, opts.model_dump())
        return CondensedHtml(
            html=result_str,
            truncated=len(result_str) >= opts.max_chars,
            original_chars=len(snap.html),
            stripped_chars=len(result_str),
        )

    # ── Finders ───────────────────────────────────────────────────────────────

    def _make_finders(self, snapshot: PageSnapshot) -> Finders:
        """Construct a Finders instance wired to the current snapshot and the
        live Playwright page (so multi-match finders can enrich rects via
        ``page.query_selector`` + ``bounding_box`` roundtrips)."""
        from frontprompt.analysis.finders import Finders

        return Finders(
            state_manager=self._state_manager,
            url=snapshot.url,
            snapshot_id=snapshot.snapshot_id,
            page=self._page,
        )

    async def find_one(self, query: FindQuery, comment: str, parent_pick: Pick | None = None) -> Pick | None:
        """Find exactly one element. Returns Pick or None. Raises FindAmbiguousError if N > 1."""
        from frontprompt.analysis._impl.scrapling_bridge import find_elements

        snap = await self.snapshot()
        parent_match = None
        if parent_pick is not None:
            matches = find_elements(snap.parsed_document, {"css": parent_pick.element.selector})
            parent_match = matches[0] if matches else None
        return await self._make_finders(snap).find_one(snap.parsed_document, query, comment, parent_match)

    async def find_first(
        self, query: FindQuery, comment: str, parent_pick: Pick | None = None
    ) -> tuple[Pick, int] | None:
        """Find the first matching element. Returns (pick, total) or None."""
        from frontprompt.analysis._impl.scrapling_bridge import find_elements

        snap = await self.snapshot()
        parent_match = None
        if parent_pick is not None:
            matches = find_elements(snap.parsed_document, {"css": parent_pick.element.selector})
            parent_match = matches[0] if matches else None
        return await self._make_finders(snap).find_first(snap.parsed_document, query, comment, parent_match)

    async def find_by_text(
        self,
        text: str,
        role: str | None,
        parent_pick: Pick | None,
        comment: str,
        limit: int,
    ) -> FindResult:
        """Find elements by text content (substring, case-insensitive)."""
        from frontprompt.analysis._impl.scrapling_bridge import find_elements

        snap = await self.snapshot()
        parent_match = None
        if parent_pick is not None:
            matches = find_elements(snap.parsed_document, {"css": parent_pick.element.selector})
            parent_match = matches[0] if matches else None
        return await self._make_finders(snap).find_by_text(
            snap.parsed_document, text, role, comment, limit, parent_match
        )

    async def find_by_regex(
        self,
        pattern: str,
        field: Literal["text", "attribute", "any"],
        parent_pick: Pick | None,
        comment: str,
        limit: int,
    ) -> FindResult:
        """Find elements whose text/attribute matches a regex pattern."""
        from frontprompt.analysis._impl.scrapling_bridge import find_elements

        snap = await self.snapshot()
        parent_match = None
        if parent_pick is not None:
            matches = find_elements(snap.parsed_document, {"css": parent_pick.element.selector})
            parent_match = matches[0] if matches else None
        return await self._make_finders(snap).find_by_regex(
            snap.parsed_document, pattern, field, comment, limit, parent_match
        )

    async def find_similar(
        self,
        anchor_pick: Pick,
        threshold: float,
        max_results: int,
        comment: str,
    ) -> FindResult:
        """Find elements structurally similar to anchor_pick."""
        from frontprompt.analysis._impl.scrapling_bridge import find_elements
        from frontprompt.analysis.finders import StaleAnchorError

        snap = await self.snapshot()
        # Verify anchor exists in snapshot
        anchor_matches = find_elements(snap.parsed_document, {"css": anchor_pick.element.selector})
        if not anchor_matches:
            raise StaleAnchorError("find_similar: anchor pick not found in current snapshot")
        return await self._make_finders(snap).find_similar(
            snap.parsed_document,
            anchor_pick.element.fingerprint.model_dump(),
            threshold,
            max_results,
            comment,
        )

    # ── Context + path ─────────────────────────────────────────────────────────

    async def context(
        self,
        pick: Pick,
        levels_up: int,
        sibling_radius: int,
    ) -> ElementContext:
        """Return structural context (ancestors + siblings) for a pick."""
        from frontprompt.analysis._impl.scrapling_bridge import find_elements
        from frontprompt.analysis.context import build_context

        snap = await self.snapshot()
        matches = find_elements(snap.parsed_document, {"css": pick.element.selector})
        if not matches:
            raise ValueError(f"context: pick {pick.pick_id!r} not found in snapshot")
        return build_context(snap.parsed_document, matches[0], levels_up=levels_up, sibling_radius=sibling_radius)

    async def path(self, pick: Pick) -> list[PathSegment]:
        """Return breadcrumb path from root to the picked element."""
        from frontprompt.analysis._impl.scrapling_bridge import find_elements
        from frontprompt.analysis.context import build_path

        snap = await self.snapshot()
        matches = find_elements(snap.parsed_document, {"css": pick.element.selector})
        if not matches:
            raise ValueError(f"path: pick {pick.pick_id!r} not found in snapshot")
        return build_path(snap.parsed_document, matches[0])

    # ── Ref materialization ────────────────────────────────────────────────────

    async def pick_from_ref(
        self,
        ref_id_or_ref: str | OutlineRef,  # accepts both OutlineRef object and raw ref_id str
        snapshot_id_or_comment: str = "",  # snapshot_id when called with 3 strings, comment when called with OutlineRef
        comment: str = "",  # used when called with 3 strings
    ) -> Pick | None:
        """Materialise an OutlineRef to a Pick.

        Two call forms:
            pick_from_ref(ref_id: str, snapshot_id: str, comment: str)  # pre-resolved-Pick form
            pick_from_ref(ref: OutlineRef, comment: str)                 # integration test form
        """
        from frontprompt.analysis.finders import _match_to_pick

        # Resolve arguments to (ref_id, snapshot_id, comment)
        if isinstance(ref_id_or_ref, OutlineRef):
            ref = ref_id_or_ref
            actual_ref_id = ref.ref_id
            actual_snapshot_id = ref.snapshot_id
            actual_comment = snapshot_id_or_comment  # second arg is comment in this form
        else:
            actual_ref_id = ref_id_or_ref
            actual_snapshot_id = snapshot_id_or_comment
            actual_comment = comment

        # Check snapshot validity
        if self._current_snapshot is None:
            return None
        if actual_snapshot_id and actual_snapshot_id != self._current_snapshot.snapshot_id:
            return None  # ref_expired

        # Look up the element match in ref_table
        match = self._current_snapshot.ref_table.get(actual_ref_id)
        if match is None:
            return None  # ref_not_found

        pick: Pick = _match_to_pick(match, actual_comment, self._current_snapshot.url)
        await self._state_manager.add_pick_from_programmatic_source(pick)
        return pick

    # ── Adaptive relocation ────────────────────────────────────────────────────

    async def relocate(self, picks: list[Pick]) -> list[RelocationResult]:
        """Relocate picks after potential DOM drift."""
        from frontprompt.analysis.relocator import Relocator

        snap = await self.snapshot()
        return Relocator().relocate(snap.parsed_document, picks)

    # ── Inspect ───────────────────────────────────────────────────────────────

    async def inspect(
        self,
        picks: list[Pick],
        fields: list[InspectField] | None = None,
    ) -> list[InspectResult]:
        """Hybrid inspect: static fields from snapshot + dynamic via PageController."""
        from frontprompt.analysis.inspect import Inspector

        snap = await self.snapshot()
        all_fields: list[str] = list(fields) if fields else ["text", "role", "visible", "enabled"]
        return await Inspector().inspect(
            snap.parsed_document,
            picks,
            all_fields,
            self._page_controller if hasattr(self, "_page_controller") else None,
        )


class NullPageAnalyzer:
    """Null-object pattern for boot paths without a live browser.

    All methods raise NotImplementedError. Used by run_socket_server when no
    real PageAnalyzer can be constructed (e.g. NullPageController scenarios).
    """

    async def snapshot(self, fresh: bool = False) -> Any:
        raise NotImplementedError("NullPageAnalyzer has no live page")

    def invalidate_snapshot(self) -> None:
        pass  # no-op for null

    async def outline(self, options: Any = None) -> Any:
        raise NotImplementedError("NullPageAnalyzer has no live page")

    async def condensed_html(self, options: Any = None) -> Any:
        raise NotImplementedError("NullPageAnalyzer has no live page")

    async def find_one(self, query: Any, comment: str) -> Any:
        raise NotImplementedError("NullPageAnalyzer has no live page")

    async def find_first(self, query: Any, comment: str) -> Any:
        raise NotImplementedError("NullPageAnalyzer has no live page")

    async def find_by_text(self, *args: Any, **kwargs: Any) -> Any:
        raise NotImplementedError("NullPageAnalyzer has no live page")

    async def find_by_regex(self, *args: Any, **kwargs: Any) -> Any:
        raise NotImplementedError("NullPageAnalyzer has no live page")

    async def find_similar(self, *args: Any, **kwargs: Any) -> Any:
        raise NotImplementedError("NullPageAnalyzer has no live page")

    async def context(self, *args: Any, **kwargs: Any) -> Any:
        raise NotImplementedError("NullPageAnalyzer has no live page")

    async def path(self, *args: Any, **kwargs: Any) -> Any:
        raise NotImplementedError("NullPageAnalyzer has no live page")

    async def pick_from_ref(self, ref_id: str, snapshot_id: str, comment: str) -> Any:
        raise NotImplementedError("NullPageAnalyzer has no live page")

    async def relocate(self, *args: Any, **kwargs: Any) -> Any:
        raise NotImplementedError("NullPageAnalyzer has no live page")

    async def inspect(self, *args: Any, **kwargs: Any) -> Any:
        raise NotImplementedError("NullPageAnalyzer has no live page")
