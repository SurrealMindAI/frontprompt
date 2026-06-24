"""Scrapling bridge — the ONLY file in frontprompt/analysis/ that imports scrapling.

Tech-agnostic API: callers see only ParsedDocument and ElementMatch (our
own Pydantic types). Scrapling-internal types never escape this module.

If scrapling is replaced in a future version, only this file changes.
Bus-factor mitigation: scrapling==0.4.8 is pinned exactly.
"""

from __future__ import annotations

from collections.abc import Mapping
from typing import Any, Final, Literal

from pydantic import BaseModel, ConfigDict

from frontprompt.overlay.injector import DEFAULT_MARKER_ID

# ── condensed_html() pipeline configuration (code-only switches, no API) ──────
# These are private module constants, deliberately not exposed via MCP tool
# schemas or Pydantic request models. A developer-debug toggle: flip _CLEANUP_LEVEL
# to "raw" locally to inspect the un-stripped output. Overlay strip is unconditional —
# overlay artefacts are NEVER part of page content for LLM consumers or screenshots.

_STRIP_FRONTPROMPT_OVERLAY: Final[bool] = True
_CLEANUP_LEVEL: Final[Literal["raw", "semantic"]] = "semantic"

_SEMANTIC_TAG_ALLOWLIST: Final[frozenset[str]] = frozenset(
    {
        # structural
        "html",
        "body",
        "head",
        "title",
        "meta",
        # sectioning
        "header",
        "main",
        "nav",
        "aside",
        "footer",
        "article",
        "section",
        "figure",
        "figcaption",
        # headings
        "h1",
        "h2",
        "h3",
        "h4",
        "h5",
        "h6",
        # text content
        "p",
        "blockquote",
        "pre",
        "code",
        "hr",
        "br",
        # inline semantic
        "a",
        "strong",
        "em",
        "mark",
        "q",
        "cite",
        "abbr",
        "time",
        "kbd",
        "samp",
        "var",
        "dfn",
        # lists
        "ul",
        "ol",
        "li",
        "dl",
        "dt",
        "dd",
        # tables
        "table",
        "thead",
        "tbody",
        "tfoot",
        "tr",
        "th",
        "td",
        "caption",
        "colgroup",
        "col",
        # forms
        "form",
        "input",
        "button",
        "label",
        "select",
        "option",
        "optgroup",
        "textarea",
        "fieldset",
        "legend",
        # media
        "img",
        "picture",
        "source",
        "video",
        "audio",
        "track",
        # interactive
        "details",
        "summary",
        "dialog",
    }
)

_SEMANTIC_ATTR_ALLOWLIST: Final[Mapping[str, frozenset[str]]] = {
    "a": frozenset({"href", "target"}),
    "img": frozenset({"src", "alt"}),
    "picture": frozenset({"srcset", "media", "type"}),
    "source": frozenset({"srcset", "media", "type"}),
    "video": frozenset({"src", "controls", "poster"}),
    "audio": frozenset({"src", "controls", "poster"}),
    "track": frozenset({"src", "kind", "srclang", "label"}),
    "input": frozenset({"type", "name", "value", "placeholder", "checked", "disabled", "required"}),
    "button": frozenset({"type", "name", "value", "disabled"}),
    "select": frozenset({"name", "multiple", "required", "disabled"}),
    "option": frozenset({"value", "selected", "disabled"}),
    "textarea": frozenset({"name", "placeholder", "rows", "cols", "required", "disabled"}),
    "form": frozenset({"action", "method", "enctype", "target"}),
    "label": frozenset({"for"}),
    "fieldset": frozenset({"disabled", "name"}),
    "optgroup": frozenset({"disabled", "label"}),
    "meta": frozenset({"name", "content", "property"}),
    "time": frozenset({"datetime"}),
    "q": frozenset({"cite"}),
    "blockquote": frozenset({"cite"}),
    "td": frozenset({"colspan", "rowspan", "scope"}),
    "th": frozenset({"colspan", "rowspan", "scope"}),
}

# ── Our domain types (no scrapling types leak out) ────────────────────────────


class ParsedDocument(BaseModel):
    """Opaque wrapper around a scrapling Selector instance.

    Callers hold this as a black-box. Only bridge functions interact with
    the underlying scrapling object.
    """

    model_config = ConfigDict(arbitrary_types_allowed=True)

    _selector: Any  # scrapling.parser.Selector

    def __init__(self, selector: Any) -> None:
        # We bypass pydantic's __init__ here to store the mutable selector
        # as a plain Python attribute — Pydantic would reject a non-annotated
        # mutable object otherwise.
        object.__setattr__(self, "_selector", selector)

    @property
    def selector(self) -> Any:
        return object.__getattribute__(self, "_selector")


class ElementMatch(BaseModel):
    """One matched element returned by a bridge query.

    Exposes the subset of scrapling element attributes that
    PageAnalyzer needs. No raw scrapling Selector is exposed.
    """

    model_config = ConfigDict(arbitrary_types_allowed=True)

    tag: str
    text: str = ""
    attributes: dict[str, str] = {}
    path: list[str] = []
    html_content: str = ""
    # fingerprint dict for re-feeding into scrapling.relocate()
    fingerprint: dict[str, Any] = {}
    # internal — kept to allow scrapling.find_similar on the original object
    _raw: Any = None

    def __init__(
        self,
        *,
        tag: str,
        text: str = "",
        attributes: dict[str, str] | None = None,
        path: list[str] | None = None,
        html_content: str = "",
        fingerprint: dict[str, Any] | None = None,
        _raw: Any = None,
    ) -> None:
        super().__init__(
            tag=tag,
            text=text,
            attributes=attributes or {},
            path=path or [],
            html_content=html_content,
            fingerprint=fingerprint or {},
        )
        object.__setattr__(self, "_raw", _raw)

    @property
    def raw(self) -> Any:
        """Raw scrapling element — only scrapling_bridge.py should use this."""
        return object.__getattribute__(self, "_raw")

    # ── Convenience aliases used by higher-level modules ──────────────────────

    @property
    def text_content(self) -> str:
        """Alias for text — matches plan API references."""
        return self.text

    @property
    def outer_html(self) -> str:
        """Alias for html_content."""
        return self.html_content

    @property
    def css_selector(self) -> str:
        """Generate a CSS selector for this element from fingerprint data.

        Uses 'id' attribute for strong selectors, falls back to tag + path.
        Not guaranteed unique for multi-match queries — for that case see
        :pyattr:`unique_selector`.
        """
        elem_id = self.attributes.get("id", "")
        if elem_id:
            return f"{self.tag}#{elem_id}"
        cls = self.attributes.get("class", "")
        if cls:
            first_cls = cls.split()[0]
            return f"{self.tag}.{first_cls}"
        return self.tag

    @property
    def unique_selector(self) -> str | None:
        """Path-disambiguated CSS selector that resolves uniquely against the live DOM.

        Delegates to scrapling's ``generate_css_selector`` property on the raw
        element, which builds an ``ancestor > … > tag:nth-of-type(N)`` chain
        with id-shortcut when present (e.g. ``"#main"`` for ``<div id="main">``
        and ``"body > div > span:nth-of-type(2)"`` for the second sibling span).
        Scrapling omits ``:nth-of-type(1)`` for the first same-tag sibling —
        that is semantically correct since ``page.query_selector()`` returns
        the first match for an ambiguous selector.

        Defensive escape: when the element has a CSS-unsafe ``id`` (whitespace,
        special characters), scrapling emits the raw id which Playwright would
        reject. In that case we emit the attribute-selector form
        ``"<tag>[id='…']"`` so the round-trip remains valid.

        Used by :func:`Finders._try_fetch_rect` to resolve a scrapling match
        back to its live Playwright counterpart for ``bounding_box()``.

        Returns ``None`` when no raw element is attached (hand-built
        ElementMatch) — callers must skip the Playwright round-trip and leave
        rect zeroed.
        """
        import re

        raw = self.raw
        if raw is None:
            return None

        elem_id = self.attributes.get("id", "")
        if elem_id and not re.match(r"^[A-Za-z_][\w-]*$", elem_id):
            escaped = elem_id.replace("\\", "\\\\").replace("'", "\\'")
            return f"{self.tag}[id='{escaped}']"

        try:
            sel = raw.generate_css_selector
        except Exception:
            return None
        return str(sel) if sel else None

    @property
    def fingerprint_dict(self) -> dict[str, Any]:
        """Alias for fingerprint — matches plan API references."""
        return self.fingerprint

    @property
    def rect(self) -> dict[str, float]:
        """Empty rect — static parse has no layout information."""
        return {"x": 0.0, "y": 0.0, "width": 0.0, "height": 0.0}


# ── Bridge helpers ─────────────────────────────────────────────────────────────


def parse_html(html: str) -> ParsedDocument:
    """Parse raw HTML into a ParsedDocument ready for querying.

    Uses scrapling.parser.Selector (lxml-backed, no browser round-trip).
    """
    from scrapling.parser import Selector  # the ONLY scrapling import in analysis/

    selector = Selector(content=html)
    return ParsedDocument(selector)


def _element_to_match(el: Any) -> ElementMatch:
    """Convert a scrapling element to our ElementMatch domain type."""
    tag = getattr(el, "tag", "") or ""
    text = ""
    raw_text = getattr(el, "text", None)
    if raw_text is not None:
        text = str(raw_text)
    attrib = getattr(el, "attrib", {})
    attributes = dict(attrib) if attrib else {}
    html_content = ""
    raw_html = getattr(el, "html_content", None)
    if raw_html is not None:
        html_content = str(raw_html)

    # Build fingerprint compatible with ElementFingerprint / scrapling.relocate()
    path_attr = getattr(el, "path", None)
    # path is a Selectors iterable — extract tag strings
    path: list[str] = []
    if path_attr is not None:
        for p in path_attr:
            tag_val = getattr(p, "tag", "") or ""
            path.append(str(tag_val))

    parent = getattr(el, "parent", None)
    parent_name: str | None = None
    parent_attribs: dict[str, str] = {}
    parent_text: str = ""
    if parent is not None:
        parent_name = getattr(parent, "tag", None)
        raw_pa = getattr(parent, "attrib", {})
        parent_attribs = dict(raw_pa) if raw_pa else {}
        raw_pt = getattr(parent, "text", None)
        parent_text = str(raw_pt) if raw_pt else ""

    siblings_raw = getattr(el, "siblings", None)
    siblings: list[str] = []
    if siblings_raw is not None:
        siblings = [getattr(s, "tag", "") for s in siblings_raw if s is not None]

    children_raw = getattr(el, "children", None)
    children: list[str] = []
    if children_raw is not None:
        children = [getattr(c, "tag", "") for c in children_raw if c is not None]

    fingerprint = {
        "tag": tag,
        "attributes": attributes,
        "text": text[:500],
        "path": path,
        "parent_name": parent_name,
        "parent_attribs": parent_attribs,
        "parent_text": parent_text[:500],
        "siblings": siblings,
        "children": children,
    }
    return ElementMatch(
        tag=tag,
        text=text,
        attributes=attributes,
        path=path,
        html_content=html_content,
        fingerprint=fingerprint,
        _raw=el,
    )


def find_by_text(
    doc: ParsedDocument,
    text: str,
    role: str | None,
    exact: bool,
    scope: ElementMatch | None,
) -> list[ElementMatch]:
    """Find elements by visible text content.

    ``exact=False`` (default) is case-insensitive substring.
    ``scope`` restricts the search to a sub-tree.
    ``role`` is an optional ARIA role filter (applied post-query).
    """
    root = doc.selector if scope is None else scope.raw
    if root is None:
        return []

    # scrapling uses partial=True for substring, partial=False for exact
    # Our API: exact=True → partial=False; exact=False → partial=True
    results = root.find_by_text(text, first_match=False, partial=not exact)
    if results is None:
        return []
    matches = [_element_to_match(el) for el in results]
    if role:
        matches = [m for m in matches if m.attributes.get("role") == role]
    return matches


def find_by_regex(
    doc: ParsedDocument,
    pattern: str,
    field: str,
    scope: ElementMatch | None,
) -> list[ElementMatch]:
    """Find elements where a field matches the regex pattern."""
    root = doc.selector if scope is None else scope.raw
    if root is None:
        return []

    results = root.find_by_regex(pattern, first_match=False)
    if results is None:
        return []
    return [_element_to_match(el) for el in results]


def find_elements(doc: ParsedDocument, query: dict[str, Any]) -> list[ElementMatch]:
    """Generic element query via CSS selector dict.

    ``query`` accepts ``selector`` or ``css`` as the key.
    """
    selector_str = query.get("selector") or query.get("css", "")
    if not selector_str:
        return []
    results = doc.selector.find_all(selector_str)
    if results is None:
        return []
    return [_element_to_match(el) for el in results]


def find_similar_elements(
    doc: ParsedDocument,
    anchor_fingerprint: dict[str, Any],
    threshold: float,
    max_results: int,
) -> list[ElementMatch]:
    """Find elements structurally similar to an anchor fingerprint.

    Uses scrapling's relocate() with the given percentage threshold.
    """
    percentage = int(threshold * 100)
    results = doc.selector.relocate(element=anchor_fingerprint, percentage=percentage)
    if results is None:
        return []
    return [_element_to_match(el) for el in results[:max_results]]


def relocate_element(
    doc: ParsedDocument,
    fingerprint: dict[str, Any],
) -> ElementMatch | None:
    """Try to re-find an element given a stored fingerprint.

    Returns the best match or None if nothing is above 70% similarity.
    """
    results = doc.selector.relocate(element=fingerprint, percentage=70)
    if not results:
        return None
    return _element_to_match(results[0])


def condensed_html(doc: ParsedDocument, options: dict[str, Any]) -> str:
    """Return cleaned HTML of the document root.

    Pipeline (all in-memory, never mutates the live DOM):

      1. regex strips (scripts/styles/svg/comments) from the prettified scrapling output
      2. lxml.html.document_fromstring parse
      3. drop the frontprompt overlay-host element (#__frontprompt_overlay_host__) —
         hardcoded via _STRIP_FRONTPROMPT_OVERLAY so its artefact never reaches LLMs
      4. semantic tree-walk (when _CLEANUP_LEVEL == "semantic"): unwrap non-allowlisted
         tags, reduce attributes of allowlisted tags to the per-tag attr allowlist
      5. tostring + optional collapse_whitespace

    Caller (analyzer.py) passes CondensedHtmlOptions.model_dump(). The new pipeline
    stages (overlay strip + semantic cleanup) are NOT exposed in CondensedHtmlOptions
    — they are governed by private module constants and apply unconditionally.
    """
    import re

    raw = doc.selector.prettify() or ""

    if options.get("strip_scripts", True):
        raw = re.sub(r"<script[^>]*>.*?</script>", "", raw, flags=re.DOTALL | re.IGNORECASE)
    if options.get("strip_styles", True):
        raw = re.sub(r"<style[^>]*>.*?</style>", "", raw, flags=re.DOTALL | re.IGNORECASE)
    if options.get("strip_comments", True):
        raw = re.sub(r"<!--.*?-->", "", raw, flags=re.DOTALL)
    if options.get("strip_svg", True):
        raw = re.sub(r"<svg[^>]*>.*?</svg>", "", raw, flags=re.DOTALL | re.IGNORECASE)

    # Empty / shell-only input → empty output (consistent with caller expectation
    # for empty pages). Detect by stripping the bare html/head/body skeleton.
    _SHELL_RE = re.compile(r"</?(html|head|body|title)\s*/?>", re.IGNORECASE)
    if not _SHELL_RE.sub("", raw).strip():
        return ""

    import lxml.html  # type: ignore[import-untyped]
    from lxml import etree

    try:
        tree = lxml.html.document_fromstring(raw)
    except (etree.ParserError, etree.XMLSyntaxError, ValueError):
        # Malformed input that even lxml's forgiving parser cannot handle —
        # fall back to the regex-only output with optional final whitespace collapse.
        out = raw
        if options.get("collapse_whitespace", True):
            out = re.sub(r"\s{2,}", " ", out)
        return out

    if _STRIP_FRONTPROMPT_OVERLAY:
        for host_el in tree.xpath(f"//*[@id='{DEFAULT_MARKER_ID}']"):
            host_el.drop_tree()

    if _CLEANUP_LEVEL == "semantic":
        _apply_semantic_cleanup(tree)

    out = etree.tostring(tree, encoding="unicode", method="html")

    if options.get("collapse_whitespace", True):
        out = re.sub(r"\s{2,}", " ", out)

    return out


def _apply_semantic_cleanup(tree: Any) -> None:
    """In-place semantic cleanup of an lxml tree.

    Stage (a): reduce attributes of allowlisted elements to the per-tag allowlist
               (elements without an entry in _SEMANTIC_ATTR_ALLOWLIST lose ALL attrs).
    Stage (b): unwrap (strip_tags) non-allowlisted elements — text and any
               allowlisted descendants are preserved as children of the grandparent.
    """
    from lxml import etree

    # Stage (a): attribute reduction
    for el in tree.iter():
        tag_raw = el.tag
        if not isinstance(tag_raw, str):
            continue  # skip comments, processing instructions, etc.
        tag = tag_raw.lower()
        if tag in _SEMANTIC_TAG_ALLOWLIST:
            allowed_attrs = _SEMANTIC_ATTR_ALLOWLIST.get(tag, frozenset())
            for attr_name in list(el.attrib.keys()):
                if attr_name not in allowed_attrs:
                    del el.attrib[attr_name]

    # Stage (b): collect tags to unwrap, then strip in one pass
    tags_to_strip: set[str] = set()
    for el in tree.iter():
        tag_raw = el.tag
        if not isinstance(tag_raw, str):
            continue
        tag = tag_raw.lower()
        if tag not in _SEMANTIC_TAG_ALLOWLIST:
            tags_to_strip.add(tag)

    if tags_to_strip:
        etree.strip_tags(tree, *tags_to_strip)


def get_ancestors(doc: ParsedDocument, match: ElementMatch) -> list[ElementMatch]:
    """Return the ancestor chain of match, from nearest (direct parent) to root.

    Uses scrapling's iterancestors() on the raw element.
    """
    raw = match.raw
    if raw is None:
        return []
    try:
        ancestors_raw = list(raw.iterancestors())
    except Exception:
        return []
    return [_element_to_match(a) for a in ancestors_raw]


def get_siblings(
    doc: ParsedDocument,
    match: ElementMatch,
    radius: int,
) -> tuple[ElementMatch | None, ElementMatch | None]:
    """Return (prev_sibling, next_sibling) within the given radius.

    Uses scrapling's .previous and .next on the raw element.
    radius > 0 is required to return non-None; radius=0 always returns (None, None).
    """
    if radius <= 0:
        return None, None
    raw = match.raw
    if raw is None:
        return None, None
    prev_raw = getattr(raw, "previous", None)
    next_raw = getattr(raw, "next", None)
    prev = _element_to_match(prev_raw) if prev_raw is not None else None
    nxt = _element_to_match(next_raw) if next_raw is not None else None
    return prev, nxt


def fingerprint_similarity(match: ElementMatch, fp_dict: dict[str, Any]) -> float:
    """Return 0.0-1.0 similarity between match and fp_dict.

    Uses scrapling's internal __calculate_similarity_score via the raw element.
    Falls back to a lightweight attribute-based heuristic if scrapling internals fail.
    """
    raw = match.raw
    if raw is None:
        return _attribute_similarity(match, fp_dict)

    try:
        from scrapling.parser import Selector as _Sel

        score_fn = getattr(_Sel, "_Selector__calculate_similarity_score", None)
        if score_fn is None:
            return _attribute_similarity(match, fp_dict)
        # Build a Selector from the document that contains the raw element
        # We use the raw element's parent document if accessible
        raw_root = raw.getroottree().getroot() if hasattr(raw, "getroottree") else None
        if raw_root is None:
            return _attribute_similarity(match, fp_dict)
        import lxml.etree as _etree  # type: ignore[import-untyped]

        outer_html = _etree.tostring(raw_root, encoding="unicode", method="html")
        doc_sel = _Sel(content=outer_html)
        percentage = score_fn(doc_sel, fp_dict, raw)
        return min(1.0, max(0.0, float(percentage) / 100.0))
    except Exception:
        return _attribute_similarity(match, fp_dict)


def _attribute_similarity(match: ElementMatch, fp_dict: dict[str, Any]) -> float:
    """Lightweight fallback similarity based on tag + id + class + text."""
    score = 0.0
    checks = 0

    # tag match
    if match.tag == fp_dict.get("tag", ""):
        score += 1.0
    checks += 1

    # id match (strong signal)
    match_id = match.attributes.get("id", "")
    fp_id = fp_dict.get("attributes", {}).get("id", "")
    if match_id or fp_id:
        if match_id == fp_id:
            score += 1.0
        checks += 1

    # text match
    match_text = (match.text or "")[:100]
    fp_text = (fp_dict.get("text", "") or "")[:100]
    if match_text or fp_text:
        if match_text == fp_text:
            score += 1.0
        checks += 1

    # class match
    match_cls = match.attributes.get("class", "")
    fp_cls = fp_dict.get("attributes", {}).get("class", "")
    if match_cls or fp_cls:
        if match_cls == fp_cls:
            score += 1.0
        checks += 1

    if checks == 0:
        return 0.5
    return round(score / checks, 2)


__all__ = [
    "ElementMatch",
    "ParsedDocument",
    "condensed_html",
    "find_by_regex",
    "find_by_text",
    "find_elements",
    "find_similar_elements",
    "fingerprint_similarity",
    "get_ancestors",
    "get_siblings",
    "parse_html",
    "relocate_element",
]
