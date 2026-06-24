"""Tests for the scrapling bridge — parse_html, find_by_text, find_elements, etc."""

from __future__ import annotations

import pytest

scrapling = pytest.importorskip("scrapling", reason="scrapling not installed")

from frontprompt.analysis._impl.scrapling_bridge import (  # noqa: E402
    ParsedDocument,
    condensed_html,
    find_by_text,
    find_elements,
    parse_html,
    relocate_element,
)

SIMPLE_HTML = """
<!DOCTYPE html><html><body>
  <h1>Hello World</h1>
  <a href="/more">More information</a>
  <button class="btn">Submit</button>
</body></html>
"""


def test_parse_html_returns_parsed_document() -> None:
    doc = parse_html(SIMPLE_HTML)
    assert isinstance(doc, ParsedDocument)


def test_find_by_text_exact_match() -> None:
    doc = parse_html(SIMPLE_HTML)
    matches = find_by_text(doc, "More information", role=None, exact=True, scope=None)
    assert len(matches) == 1
    assert matches[0].tag == "a"


def test_find_by_text_substring_match() -> None:
    doc = parse_html(SIMPLE_HTML)
    matches = find_by_text(doc, "More info", role=None, exact=False, scope=None)
    assert len(matches) >= 1


def test_find_by_text_no_match_returns_empty() -> None:
    doc = parse_html(SIMPLE_HTML)
    matches = find_by_text(doc, "xyznoexist", role=None, exact=False, scope=None)
    assert matches == []


def test_find_elements_by_css() -> None:
    doc = parse_html(SIMPLE_HTML)
    matches = find_elements(doc, {"selector": ".btn"})
    assert len(matches) == 1
    assert matches[0].tag == "button"


def test_condensed_html_strips_scripts() -> None:
    html = "<html><head><script>alert('x')</script></head><body><p>hi</p></body></html>"
    doc = parse_html(html)
    result = condensed_html(
        doc,
        {
            "strip_scripts": True,
            "strip_styles": False,
            "strip_comments": False,
            "strip_svg": False,
            "collapse_whitespace": False,
        },
    )
    assert "<script>" not in result
    assert "hi" in result


def test_condensed_html_strips_styles() -> None:
    html = "<html><head><style>.x{color:red}</style></head><body><p>hi</p></body></html>"
    doc = parse_html(html)
    result = condensed_html(
        doc,
        {
            "strip_scripts": False,
            "strip_styles": True,
            "strip_comments": False,
            "strip_svg": False,
            "collapse_whitespace": False,
        },
    )
    assert "<style>" not in result
    assert "hi" in result


def test_element_match_fingerprint_has_required_keys() -> None:
    doc = parse_html(SIMPLE_HTML)
    matches = find_elements(doc, {"selector": "a"})
    assert matches
    fp = matches[0].fingerprint
    required = {"tag", "attributes", "text", "path", "parent_name", "parent_attribs", "parent_text", "siblings"}
    assert required.issubset(fp.keys())


def test_relocate_element_finds_in_same_html() -> None:
    doc1 = parse_html(SIMPLE_HTML)
    matches = find_elements(doc1, {"selector": "a"})
    assert matches
    fp = matches[0].fingerprint
    doc2 = parse_html(SIMPLE_HTML)
    result = relocate_element(doc2, fp)
    assert result is not None
    assert result.tag == "a"


def test_relocate_element_returns_none_for_different_html() -> None:
    fp = {
        "tag": "div",
        "attributes": {"id": "hero-cta"},
        "text": "Click me",
        "path": ["html", "body", "main", "div"],
        "parent_name": "main",
        "parent_attribs": {},
        "parent_text": "",
        "siblings": [],
        "children": [],
    }
    other_html = "<html><body><header><nav><a>link</a></nav></header></body></html>"
    doc = parse_html(other_html)
    result = relocate_element(doc, fp)
    assert result is None
