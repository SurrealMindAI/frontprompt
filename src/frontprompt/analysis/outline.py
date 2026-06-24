"""OutlineBuilder — synchronous page-outline construction from ParsedDocument.

All scrapling_bridge calls are lxml CPU-bound (no I/O). The caller
(PageAnalyzer.outline) is async but invokes this synchronously.

Design choice: ref_table is passed by reference (dict mutation) so that
PageSnapshot owns the lifetime — OutlineBuilder does not hold any state.
Scrapling isolation: this module uses ONLY scrapling_bridge APIs, never
direct scrapling imports (arch-test enforced).
"""

from __future__ import annotations

from frontprompt.analysis._impl.scrapling_bridge import ElementMatch, ParsedDocument, find_elements, parse_html
from frontprompt.analysis.types import (
    OutlineButton,
    OutlineForm,
    OutlineHeading,
    OutlineInput,
    OutlineLandmark,
    OutlineLink,
    OutlineOptions,
    OutlineRef,
    PageOutline,
)


class OutlineBuilder:
    """Builds a PageOutline from a ParsedDocument.

    Stateless — create once, reuse across snapshots.
    ref_table is owned by PageSnapshot; builder populates it.
    """

    def build_outline(
        self,
        doc: ParsedDocument,
        options: OutlineOptions,
        *,
        snapshot_id: str,
        expires_at_ms: int,
        ref_table: dict[str, ElementMatch],
        url: str = "",
        title: str = "",
    ) -> PageOutline:
        """Build a PageOutline, populating ref_table with ElementMatch per ref_id."""
        args = (doc, options, snapshot_id, expires_at_ms, ref_table)
        headings = self._build_headings(*args) if options.include_headings else []
        links = self._build_links(*args) if options.include_links else []
        buttons = self._build_buttons(*args) if options.include_buttons else []
        inputs = self._build_inputs(*args) if options.include_inputs else []
        forms = self._build_forms(*args) if options.include_forms else []
        landmarks = self._build_landmarks(*args) if options.include_landmarks else []
        return PageOutline(
            snapshot_id=snapshot_id,
            title=title,
            url=url,
            headings=headings,
            links=links,
            buttons=buttons,
            inputs=inputs,
            forms=forms,
            landmarks=landmarks,
        )

    def _make_ref(self, kind: str, idx: int, snapshot_id: str, expires_at_ms: int) -> OutlineRef:
        return OutlineRef(
            ref_id=f"out:{kind}:{idx}",
            snapshot_id=snapshot_id,
            expires_at_ms=expires_at_ms,
        )

    def _register(self, ref_id: str, match: ElementMatch, ref_table: dict[str, ElementMatch]) -> None:
        ref_table[ref_id] = match

    def _build_headings(
        self,
        doc: ParsedDocument,
        options: OutlineOptions,
        snapshot_id: str,
        expires_at_ms: int,
        ref_table: dict[str, ElementMatch],
    ) -> list[OutlineHeading]:
        matches = find_elements(doc, {"css": "h1, h2, h3, h4, h5, h6"})[: options.max_items_per_kind]
        result = []
        for idx, match in enumerate(matches):
            ref = self._make_ref("heading", idx, snapshot_id, expires_at_ms)
            self._register(ref.ref_id, match, ref_table)
            level = int(match.tag[-1]) if match.tag and match.tag[-1].isdigit() else 1
            result.append(OutlineHeading(ref=ref, level=level, text=match.text_content or ""))
        return result

    def _build_links(
        self,
        doc: ParsedDocument,
        options: OutlineOptions,
        snapshot_id: str,
        expires_at_ms: int,
        ref_table: dict[str, ElementMatch],
    ) -> list[OutlineLink]:
        matches = find_elements(doc, {"css": "a[href]"})[: options.max_items_per_kind]
        result = []
        for idx, match in enumerate(matches):
            ref = self._make_ref("link", idx, snapshot_id, expires_at_ms)
            self._register(ref.ref_id, match, ref_table)
            result.append(
                OutlineLink(
                    ref=ref,
                    text=match.text_content or "",
                    href=match.attributes.get("href"),
                )
            )
        return result

    def _build_buttons(
        self,
        doc: ParsedDocument,
        options: OutlineOptions,
        snapshot_id: str,
        expires_at_ms: int,
        ref_table: dict[str, ElementMatch],
    ) -> list[OutlineButton]:
        _css = "button, input[type=button], input[type=submit], [role=button]"
        matches = find_elements(doc, {"css": _css})[: options.max_items_per_kind]
        result = []
        for idx, match in enumerate(matches):
            ref = self._make_ref("button", idx, snapshot_id, expires_at_ms)
            self._register(ref.ref_id, match, ref_table)
            text = match.text_content or match.attributes.get("value", "")
            result.append(OutlineButton(ref=ref, text=text))
        return result

    def _build_inputs(
        self,
        doc: ParsedDocument,
        options: OutlineOptions,
        snapshot_id: str,
        expires_at_ms: int,
        ref_table: dict[str, ElementMatch],
    ) -> list[OutlineInput]:
        matches = find_elements(
            doc, {"css": "input:not([type=button]):not([type=submit]):not([type=hidden]), select, textarea"}
        )[: options.max_items_per_kind]
        result = []
        for idx, match in enumerate(matches):
            ref = self._make_ref("input", idx, snapshot_id, expires_at_ms)
            self._register(ref.ref_id, match, ref_table)
            result.append(
                OutlineInput(
                    ref=ref,
                    input_type=match.attributes.get("type", "text"),
                    name=match.attributes.get("name"),
                    placeholder=match.attributes.get("placeholder"),
                    label=None,  # label association is Phase 3
                )
            )
        return result

    def _build_forms(
        self,
        doc: ParsedDocument,
        options: OutlineOptions,
        snapshot_id: str,
        expires_at_ms: int,
        ref_table: dict[str, ElementMatch],
    ) -> list[OutlineForm]:
        matches = find_elements(doc, {"css": "form"})[: options.max_items_per_kind]
        result = []
        for idx, match in enumerate(matches):
            ref = self._make_ref("form", idx, snapshot_id, expires_at_ms)
            self._register(ref.ref_id, match, ref_table)
            # Count inputs in this form via sub-parse of outer_html
            input_count = 0
            if match.outer_html:
                try:
                    child_doc = parse_html(match.outer_html)
                    input_count = len(find_elements(child_doc, {"css": "input, select, textarea"}))
                except Exception:
                    pass
            result.append(
                OutlineForm(
                    ref=ref,
                    action=match.attributes.get("action"),
                    method=match.attributes.get("method", "get"),
                    input_count=input_count,
                )
            )
        return result

    def _build_landmarks(
        self,
        doc: ParsedDocument,
        options: OutlineOptions,
        snapshot_id: str,
        expires_at_ms: int,
        ref_table: dict[str, ElementMatch],
    ) -> list[OutlineLandmark]:
        _landmark_css = (
            "main, nav, aside, footer, header, "
            "[role=main], [role=navigation], [role=complementary], "
            "[role=contentinfo], [role=banner]"
        )
        matches = find_elements(doc, {"css": _landmark_css})[: options.max_items_per_kind]
        result = []
        for idx, match in enumerate(matches):
            ref = self._make_ref("landmark", idx, snapshot_id, expires_at_ms)
            self._register(ref.ref_id, match, ref_table)
            role = match.attributes.get("role") or match.tag
            result.append(
                OutlineLandmark(
                    ref=ref,
                    role=role,
                    label=match.attributes.get("aria-label"),
                )
            )
        return result
