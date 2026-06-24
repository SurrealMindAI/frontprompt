"""HTML-cleanup pipeline tests — condensed_html() with hardcoded overlay-strip
and semantic tree-walk (cleanup_level=semantic by default).

These tests cover the HTML-cleanup part of the v0.4.0 smoke-findings-fixes plan.
"""

from __future__ import annotations

import pytest

from frontprompt.analysis._impl import scrapling_bridge as _bridge
from frontprompt.analysis._impl.scrapling_bridge import condensed_html, parse_html
from frontprompt.overlay.injector import DEFAULT_MARKER_ID

_DEFAULT_OPTS: dict[str, object] = {
    "strip_scripts": True,
    "strip_styles": True,
    "strip_comments": True,
    "strip_svg": True,
    "collapse_whitespace": True,
}


def _condense(html: str, **overrides: object) -> str:
    opts = {**_DEFAULT_OPTS, **overrides}
    return condensed_html(parse_html(html), opts)


def test_overlay_host_div_is_stripped() -> None:
    html = (
        f"<html><body>"
        f'<div id="{DEFAULT_MARKER_ID}"><span>OVERLAY ARTEFACT</span></div>'
        f"<h1>Real Content</h1>"
        f"</body></html>"
    )
    out = _condense(html)
    assert DEFAULT_MARKER_ID not in out
    assert "OVERLAY ARTEFACT" not in out
    assert "Real Content" in out


def test_decorative_wrappers_are_unwrapped_in_semantic_mode() -> None:
    html = '<html><body><div class="wrap"><span><h1>Page</h1></span></div><div><p>Body text</p></div></body></html>'
    out = _condense(html)
    assert "<h1>Page</h1>" in out
    assert "Body text" in out
    assert "<div" not in out
    assert "<span" not in out


def test_allowlisted_tag_keeps_only_semantic_attributes() -> None:
    html = '<html><body><a href="https://example.com" data-uuid="123" class="cta">Visit</a></body></html>'
    out = _condense(html)
    assert 'href="https://example.com"' in out
    assert "data-uuid" not in out
    assert 'class="cta"' not in out
    assert ">Visit</a>" in out


def test_form_input_keeps_functional_attributes() -> None:
    html = (
        "<html><body><form>"
        '<input type="text" name="q" placeholder="Search" data-vue-x="y" class="input-lg">'
        "</form></body></html>"
    )
    out = _condense(html)
    assert 'type="text"' in out
    assert 'name="q"' in out
    assert 'placeholder="Search"' in out
    assert "data-vue-x" not in out
    assert "input-lg" not in out


def test_cleanup_is_idempotent() -> None:
    html = (
        "<html><body>"
        '<div class="wrap"><h1>Title</h1>'
        '<p>Para with <a href="/x" class="link">link</a>.</p></div>'
        "</body></html>"
    )
    once = _condense(html)
    twice = _condense(once)
    assert once == twice


def test_empty_input_returns_empty_string() -> None:
    assert _condense("") == ""
    assert _condense("   \n\t  ") == ""


def test_raw_cleanup_level_keeps_decorative_wrappers(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(_bridge, "_CLEANUP_LEVEL", "raw")
    html = '<html><body><div class="wrap"><h1>Page</h1></div></body></html>'
    out = _condense(html)
    assert "<div" in out
    assert "<h1>Page</h1>" in out


def test_raw_cleanup_level_still_strips_overlay_host(monkeypatch: pytest.MonkeyPatch) -> None:
    """Overlay-strip is _STRIP_FRONTPROMPT_OVERLAY (independent of _CLEANUP_LEVEL)."""
    monkeypatch.setattr(_bridge, "_CLEANUP_LEVEL", "raw")
    html = f'<html><body><div id="{DEFAULT_MARKER_ID}">OVERLAY</div><h1>Body</h1></body></html>'
    out = _condense(html)
    assert DEFAULT_MARKER_ID not in out
    assert "OVERLAY" not in out
    assert "<h1>Body</h1>" in out


def test_malformed_html_does_not_raise() -> None:
    # lxml is forgiving — unbalanced tags shouldn't crash the pipeline
    html = "<html><body><div><span>unclosed</body></html>"
    out = _condense(html)
    assert "unclosed" in out


def test_semantic_keeps_lists_and_tables() -> None:
    html = (
        "<html><body>"
        "<ul><li>a</li><li>b</li></ul>"
        '<table><thead><tr><th scope="col">H</th></tr></thead>'
        "<tbody><tr><td>v</td></tr></tbody></table>"
        "</body></html>"
    )
    out = _condense(html)
    assert "<ul>" in out
    assert "<li>a</li>" in out
    assert "<table>" in out
    assert 'scope="col"' in out
    assert "<td>v</td>" in out
