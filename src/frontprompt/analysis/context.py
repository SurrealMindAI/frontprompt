"""Context + path helpers for PageAnalyzer.

All scrapling_bridge calls — no direct scrapling imports (arch-test enforced).
build_context and build_path are synchronous pure functions.

Note: ElementContext.ancestors is list[PathSegment] and
      prev_sibling/next_sibling are dict[str, Any] | None
      (as defined in types.py).
"""

from __future__ import annotations

from typing import Any

from frontprompt.analysis._impl.scrapling_bridge import (
    ElementMatch,
    ParsedDocument,
    get_ancestors,
    get_siblings,
)
from frontprompt.analysis.types import ElementContext, PathSegment

_LANDMARK_TAGS = frozenset({"main", "nav", "aside", "footer", "header"})
_LANDMARK_ROLES = frozenset({"main", "navigation", "complementary", "contentinfo", "banner"})
_TABLE_TAGS = frozenset({"table", "tbody", "thead", "tfoot", "tr", "td", "th"})


def _match_to_path_segment(match: ElementMatch) -> PathSegment:
    """Convert an ElementMatch to a PathSegment."""
    return PathSegment(
        tag=match.tag,
        role=match.attributes.get("role"),
        text_excerpt=(match.text_content or "")[:40],
        semantic_landmark=match.tag if match.tag in _LANDMARK_TAGS else None,
    )


def _match_to_sibling_dict(match: ElementMatch) -> dict[str, Any]:
    """Convert an ElementMatch to the dict format expected by ElementContext siblings."""
    return {
        "tag": match.tag,
        "text": (match.text_content or "")[:40],
        "attributes": match.attributes,
    }


def build_context(
    doc: ParsedDocument,
    match: ElementMatch,
    *,
    levels_up: int,
    sibling_radius: int,
) -> ElementContext:
    """Build ElementContext for match — ancestor chain + siblings + semantic info."""
    ancestors_full = get_ancestors(doc, match)  # nearest-first order (direct parent → root)
    # Trim to levels_up nearest ancestors
    trimmed = ancestors_full[:levels_up] if levels_up > 0 else []

    ancestor_segments = [_match_to_path_segment(a) for a in trimmed]

    all_tags = {a.tag for a in ancestors_full}
    in_form = "form" in all_tags
    in_table = bool(all_tags & _TABLE_TAGS)

    semantic_landmark: str | None = None
    for a in ancestors_full:
        if a.tag in _LANDMARK_TAGS or a.attributes.get("role", "") in _LANDMARK_ROLES:
            semantic_landmark = a.attributes.get("role") or a.tag
            break

    prev_sibling = None
    next_sibling = None
    if sibling_radius > 0:
        prev_sib, next_sib = get_siblings(doc, match, radius=sibling_radius)
        prev_sibling = _match_to_sibling_dict(prev_sib) if prev_sib is not None else None
        next_sibling = _match_to_sibling_dict(next_sib) if next_sib is not None else None

    return ElementContext(
        ancestors=ancestor_segments,
        prev_sibling=prev_sibling,
        next_sibling=next_sibling,
        in_form=in_form,
        in_table=in_table,
        semantic_landmark=semantic_landmark,
    )


def build_path(doc: ParsedDocument, match: ElementMatch) -> list[PathSegment]:
    """Build breadcrumb list from root to match element (inclusive).

    Returns segments from root → match (reversed from iterancestors order).
    """
    ancestors_full = get_ancestors(doc, match)  # nearest-first: parent, grandparent, ...
    # Reverse to get root-first order
    segments: list[PathSegment] = []
    for a in reversed(ancestors_full):
        segments.append(_match_to_path_segment(a))
    # Append the element itself
    segments.append(_match_to_path_segment(match))
    return segments
