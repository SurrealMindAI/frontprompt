"""Context + path tests — element ancestors, siblings, breadcrumb."""

from __future__ import annotations

from frontprompt.analysis._impl.scrapling_bridge import find_elements, parse_html
from frontprompt.analysis.context import build_context, build_path

_HTML_NESTED = """<html><body>
  <main>
    <section>
      <form action="/submit">
        <div class="field">
          <label>Name</label>
          <input type="text" name="name" />
          <button type="submit">Submit</button>
        </div>
      </form>
    </section>
    <table>
      <tr><td><span>Cell content</span></td></tr>
    </table>
  </main>
</body></html>"""


def test_context_levels_up_ancestors_count() -> None:
    doc = parse_html(_HTML_NESTED)
    matches = find_elements(doc, {"css": "button[type=submit]"})
    assert matches, "button must be found"
    ctx = build_context(doc, matches[0], levels_up=2, sibling_radius=1)
    assert len(ctx.ancestors) == 2


def test_context_in_form_true() -> None:
    doc = parse_html(_HTML_NESTED)
    matches = find_elements(doc, {"css": "input[name=name]"})
    ctx = build_context(doc, matches[0], levels_up=3, sibling_radius=0)
    assert ctx.in_form is True


def test_context_in_table_true() -> None:
    doc = parse_html(_HTML_NESTED)
    matches = find_elements(doc, {"css": "span"})
    ctx = build_context(doc, matches[0], levels_up=4, sibling_radius=0)
    assert ctx.in_table is True


def test_context_semantic_landmark() -> None:
    doc = parse_html(_HTML_NESTED)
    matches = find_elements(doc, {"css": "button[type=submit]"})
    ctx = build_context(doc, matches[0], levels_up=5, sibling_radius=0)
    assert ctx.semantic_landmark in ("main", "section", "form", None)


def test_path_returns_breadcrumb() -> None:
    doc = parse_html(_HTML_NESTED)
    matches = find_elements(doc, {"css": "button[type=submit]"})
    segments = build_path(doc, matches[0])
    assert len(segments) >= 3
    tags = [s.tag for s in segments]
    assert "button" == tags[-1]


def test_context_sibling_radius_zero_no_siblings() -> None:
    doc = parse_html(_HTML_NESTED)
    matches = find_elements(doc, {"css": "input[name=name]"})
    ctx = build_context(doc, matches[0], levels_up=1, sibling_radius=0)
    assert ctx.prev_sibling is None
    assert ctx.next_sibling is None
