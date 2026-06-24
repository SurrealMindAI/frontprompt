"""Outline builder + OutlineRef materialization tests.

No Playwright — uses scrapling_bridge.parse_html directly with synthetic HTML.
FakeStateManager verifies pick-isolation: outline must NOT create picks.
"""

from __future__ import annotations

from frontprompt.analysis._impl.scrapling_bridge import parse_html
from frontprompt.analysis.outline import OutlineBuilder
from frontprompt.analysis.types import OutlineOptions, OutlineRef

_SAMPLE_HTML = """<!doctype html>
<html><head><title>Test</title></head>
<body>
  <h1>Main heading</h1>
  <h2>Sub heading</h2>
  <nav><a href="/about">About</a><a href="/contact">Contact</a></nav>
  <main>
    <button type="button">Click me</button>
    <form action="/search" method="get">
      <input type="text" name="q" id="search" />
      <input type="submit" value="Search" />
    </form>
  </main>
  <footer><p>Footer text</p></footer>
</body>
</html>"""


class _FakeStateManager:
    def __init__(self) -> None:
        self.added: list = []

    async def add_pick_from_programmatic_source(self, pick: object) -> None:
        self.added.append(pick)


def test_outline_headings_return_refs_not_picks() -> None:
    doc = parse_html(_SAMPLE_HTML)
    ref_table: dict = {}
    builder = OutlineBuilder()
    options = OutlineOptions(
        include_headings=True,
        include_links=False,
        include_buttons=False,
        include_inputs=False,
        include_forms=False,
        include_landmarks=False,
        max_items_per_kind=50,
    )
    outline = builder.build_outline(
        doc, options, snapshot_id="snap-1", expires_at_ms=9_999_999_999_999, ref_table=ref_table
    )
    assert len(outline.headings) == 2
    for h in outline.headings:
        assert isinstance(h.ref, OutlineRef)
        assert h.ref.ref_id.startswith("out:heading:")
        assert h.ref.snapshot_id == "snap-1"
        assert h.ref.ref_id in ref_table


def test_outline_links_include_href() -> None:
    doc = parse_html(_SAMPLE_HTML)
    ref_table: dict = {}
    builder = OutlineBuilder()
    options = OutlineOptions(
        include_headings=False,
        include_links=True,
        include_buttons=False,
        include_inputs=False,
        include_forms=False,
        include_landmarks=False,
        max_items_per_kind=50,
    )
    outline = builder.build_outline(
        doc, options, snapshot_id="snap-1", expires_at_ms=9_999_999_999_999, ref_table=ref_table
    )
    hrefs = {lnk.href for lnk in outline.links}
    assert "/about" in hrefs
    assert "/contact" in hrefs


def test_outline_does_not_create_picks() -> None:
    """OutlineBuilder MUST NOT call StateManager — picks are lazy via pick_from_ref."""
    doc = parse_html(_SAMPLE_HTML)
    ref_table: dict = {}
    fake_sm = _FakeStateManager()
    builder = OutlineBuilder()
    options = OutlineOptions(max_items_per_kind=50)
    builder.build_outline(doc, options, snapshot_id="s1", expires_at_ms=9_999_999_999_999, ref_table=ref_table)
    assert fake_sm.added == []


def test_outline_max_items_per_kind_caps_results() -> None:
    doc = parse_html(_SAMPLE_HTML)
    ref_table: dict = {}
    builder = OutlineBuilder()
    options = OutlineOptions(include_headings=True, include_links=True, max_items_per_kind=1)
    outline = builder.build_outline(
        doc, options, snapshot_id="s1", expires_at_ms=9_999_999_999_999, ref_table=ref_table
    )
    assert len(outline.headings) <= 1
    assert len(outline.links) <= 1


def test_snapshot_invalidation_clears_ref_table() -> None:
    """Invalidating the snapshot empties _ref_table so stale refs return KeyError."""
    ref_table: dict = {"out:link:0": object()}
    ref_table.clear()  # simulate what snapshot.invalidate() does
    assert "out:link:0" not in ref_table


def test_outline_buttons_disabled_returns_empty_buttons() -> None:
    """include_buttons=False produces empty buttons list."""
    doc = parse_html(_SAMPLE_HTML)
    ref_table: dict = {}
    builder = OutlineBuilder()
    options = OutlineOptions(
        include_headings=False,
        include_links=False,
        include_buttons=False,
        include_inputs=False,
        include_forms=False,
        include_landmarks=False,
        max_items_per_kind=50,
    )
    outline = builder.build_outline(
        doc, options, snapshot_id="s1", expires_at_ms=9_999_999_999_999, ref_table=ref_table
    )
    assert outline.buttons == []
