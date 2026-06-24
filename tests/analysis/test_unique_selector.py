"""ElementMatch.unique_selector — path-disambiguated CSS selector tests.

The unique_selector property is what _try_fetch_rect uses to resolve a scrapling
match back to its live Playwright counterpart for bounding_box() lookup.

For N≈50 same-tag results (find_similar typical case), css_selector falls back
to bare tag names ("div") and page.query_selector() returns the first match.
unique_selector must disambiguate via id-shortcut OR path + :nth-of-type.
"""

from __future__ import annotations

from frontprompt.analysis._impl.scrapling_bridge import (
    ElementMatch,
    find_elements,
    parse_html,
)


def test_unique_selector_uses_id_when_present_and_css_safe() -> None:
    doc = parse_html('<html><body><div id="main">x</div></body></html>')
    matches = find_elements(doc, {"css": "div"})
    assert len(matches) == 1
    assert matches[0].unique_selector == "#main"


def test_unique_selector_uses_id_when_alphanumeric_with_dashes_and_underscores() -> None:
    doc = parse_html('<html><body><section id="my-section_42">x</section></body></html>')
    matches = find_elements(doc, {"css": "section"})
    assert matches[0].unique_selector == "#my-section_42"


def test_unique_selector_emits_attribute_form_for_css_unsafe_id() -> None:
    doc = parse_html('<html><body><div id="bad id with spaces">x</div></body></html>')
    matches = find_elements(doc, {"css": "div"})
    selector = matches[0].unique_selector
    assert selector is not None
    # Bare "#bad id with spaces" would be invalid CSS — must escape to attribute form
    assert not selector.startswith("#bad id"), f"unsafe id leaked as bare # shortcut: {selector!r}"
    assert "[id='bad id with spaces']" in selector


def test_unique_selector_disambiguates_same_tag_siblings() -> None:
    html = "<html><body><div><span>first</span><span>second</span><span>third</span></div></body></html>"
    doc = parse_html(html)
    matches = find_elements(doc, {"css": "span"})
    assert len(matches) == 3
    selectors = [m.unique_selector for m in matches]
    # All three must be non-None and distinct so page.query_selector() resolves
    # each scrapling match to the matching live element (not the first one).
    assert all(s is not None for s in selectors), f"None in selectors: {selectors}"
    assert len(set(selectors)) == 3, f"selectors collide: {selectors}"
    # nth-of-type(N) for N>=2 — the first sibling is intentionally bare
    # because page.query_selector() returns the first match anyway.
    assert ":nth-of-type(2)" in selectors[1]
    assert ":nth-of-type(3)" in selectors[2]


def test_unique_selector_returns_none_when_no_path_available() -> None:
    # Construct directly without _raw or path — simulates a manually-built
    # ElementMatch that lacks ancestor information.
    em = ElementMatch(tag="div")
    assert em.unique_selector is None


def test_unique_selector_for_deeply_nested_element() -> None:
    html = "<html><body><main><article><section><p>deep</p></section></article></main></body></html>"
    doc = parse_html(html)
    matches = find_elements(doc, {"css": "p"})
    assert len(matches) == 1
    selector = matches[0].unique_selector
    assert selector is not None
    # Should encode the ancestor chain — at minimum the leaf tag preceded by
    # a parent reference via " > ".
    assert " > p" in selector or selector.startswith("p")
    # Sanity: any of the wrapping landmarks should appear
    assert any(seg in selector for seg in ("body", "main", "article", "section"))
