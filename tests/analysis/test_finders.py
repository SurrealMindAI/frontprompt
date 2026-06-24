"""Finder tests — find_one/_first/_by_text/_by_regex/_similar.

Uses synthetic HTML + real scrapling_bridge (lxml, no Playwright).
FakeStateManager captures created picks.
"""

from __future__ import annotations

import pytest

from frontprompt.analysis._impl.scrapling_bridge import parse_html
from frontprompt.analysis.finders import FindAmbiguousError, Finders
from frontprompt.analysis.types import FindQuery  # discriminated union
from frontprompt.state.state import (
    Pick,
)

_HTML_MULTI = """<html><body>
  <button class="btn">Save</button>
  <button class="btn">Cancel</button>
  <a href="/home">Go home</a>
  <input type="text" name="email" placeholder="Email" />
  <div class="card">Card A</div>
  <div class="card">Card B</div>
  <div class="card">Card C</div>
</body></html>"""


class _FakeSM:
    def __init__(self) -> None:
        self.picks: list[Pick] = []

    async def add_pick_from_programmatic_source(self, pick: Pick) -> None:
        self.picks.append(pick)


@pytest.mark.anyio
async def test_find_one_exact_match_returns_pick() -> None:
    doc = parse_html(_HTML_MULTI)
    sm = _FakeSM()
    finders = Finders(state_manager=sm, url="https://x.com", snapshot_id="s1")
    query: FindQuery = {"kind": "css", "selector": "a[href='/home']"}  # type: ignore[assignment]
    pick = await finders.find_one(doc, query, comment="home link")
    assert pick is not None
    assert len(sm.picks) == 1


@pytest.mark.anyio
async def test_find_one_no_match_returns_none() -> None:
    doc = parse_html(_HTML_MULTI)
    sm = _FakeSM()
    finders = Finders(state_manager=sm, url="https://x.com", snapshot_id="s1")
    query: FindQuery = {"kind": "css", "selector": ".nonexistent"}  # type: ignore[assignment]
    pick = await finders.find_one(doc, query, comment="x")
    assert pick is None
    assert len(sm.picks) == 0


@pytest.mark.anyio
async def test_find_one_ambiguous_raises() -> None:
    doc = parse_html(_HTML_MULTI)
    sm = _FakeSM()
    finders = Finders(state_manager=sm, url="https://x.com", snapshot_id="s1")
    query: FindQuery = {"kind": "css", "selector": "button"}  # type: ignore[assignment]
    with pytest.raises(FindAmbiguousError) as exc_info:
        await finders.find_one(doc, query, comment="btn")
    assert exc_info.value.total_matches == 2
    assert len(sm.picks) == 0  # no pick on ambiguous


@pytest.mark.anyio
async def test_find_first_returns_pick_and_total() -> None:
    doc = parse_html(_HTML_MULTI)
    sm = _FakeSM()
    finders = Finders(state_manager=sm, url="https://x.com", snapshot_id="s1")
    query: FindQuery = {"kind": "css", "selector": "button"}  # type: ignore[assignment]
    result = await finders.find_first(doc, query, comment="btn")
    assert result is not None
    _pick, total = result
    assert total == 2
    assert len(sm.picks) == 1


@pytest.mark.anyio
async def test_find_by_text_no_role_substring_match() -> None:
    doc = parse_html(_HTML_MULTI)
    sm = _FakeSM()
    finders = Finders(state_manager=sm, url="https://x.com", snapshot_id="s1")
    result = await finders.find_by_text(doc, text="card", role=None, comment="cards", limit=10, parent_match=None)
    assert result.total_matches == 3
    assert len(sm.picks) == 3


@pytest.mark.anyio
async def test_find_by_text_with_role_filter() -> None:
    """role AND-filter: only button elements containing 'Save'."""
    doc = parse_html(_HTML_MULTI)
    sm = _FakeSM()
    finders = Finders(state_manager=sm, url="https://x.com", snapshot_id="s1")
    result = await finders.find_by_text(doc, text="Save", role="button", comment="save", limit=10, parent_match=None)
    assert result.total_matches == 1
    assert len(sm.picks) == 1


@pytest.mark.anyio
async def test_find_by_text_limit_caps_picks() -> None:
    doc = parse_html(_HTML_MULTI)
    sm = _FakeSM()
    finders = Finders(state_manager=sm, url="https://x.com", snapshot_id="s1")
    result = await finders.find_by_text(doc, text="card", role=None, comment="cards", limit=2, parent_match=None)
    assert result.total_matches == 3  # total found
    assert len(sm.picks) == 2  # only limit=2 persisted


@pytest.mark.anyio
async def test_find_by_regex_text_field() -> None:
    doc = parse_html(_HTML_MULTI)
    sm = _FakeSM()
    finders = Finders(state_manager=sm, url="https://x.com", snapshot_id="s1")
    result = await finders.find_by_regex(
        doc, pattern=r"Card [A-C]", field="text", comment="cards", limit=10, parent_match=None
    )
    assert result.total_matches == 3


@pytest.mark.anyio
async def test_find_similar_threshold_zero_matches_all_cards() -> None:
    doc = parse_html(_HTML_MULTI)
    sm = _FakeSM()
    finders = Finders(state_manager=sm, url="https://x.com", snapshot_id="s1")
    # Build a synthetic anchor fingerprint for div.card
    from frontprompt.analysis._impl.scrapling_bridge import find_elements

    matches = find_elements(doc, {"css": "div.card"})
    anchor_fp = matches[0].fingerprint_dict
    result = await finders.find_similar(
        doc, anchor_fingerprint=anchor_fp, threshold=0.0, max_results=10, comment="cards"
    )
    # With threshold=0.0 all structurally similar elements should be found
    assert result.total_matches >= 1


@pytest.mark.anyio
async def test_find_first_no_match_returns_none() -> None:
    doc = parse_html(_HTML_MULTI)
    sm = _FakeSM()
    finders = Finders(state_manager=sm, url="https://x.com", snapshot_id="s1")
    query: FindQuery = {"kind": "css", "selector": ".nonexistent"}  # type: ignore[assignment]
    result = await finders.find_first(doc, query, comment="x")
    assert result is None
    assert len(sm.picks) == 0


# ---------------------------------------------------------------------------
# Rect-roundtrip via _try_fetch_rect — covers the rect-roundtrip of v0.4.0 smoke-findings
# ---------------------------------------------------------------------------


class _FakeBoundingBox:
    """Returns a fixed bounding box dict from .bounding_box() call."""

    def __init__(self, rect: dict[str, float]) -> None:
        self._rect = rect

    async def bounding_box(self) -> dict[str, float]:
        return self._rect


class _FakePage:
    """Resolves selectors to _FakeBoundingBox handles based on the rects map."""

    def __init__(self, rects_by_selector: dict[str, dict[str, float] | None]) -> None:
        self._rects = rects_by_selector
        self.calls: list[str] = []

    async def query_selector(self, selector: str) -> _FakeBoundingBox | None:
        self.calls.append(selector)
        rect = self._rects.get(selector)
        if rect is None:
            return None
        return _FakeBoundingBox(rect)


@pytest.mark.anyio
async def test_find_first_without_page_keeps_rect_zero() -> None:
    """Default constructor (page=None) — rect must remain zeroed (legacy behaviour)."""
    doc = parse_html(_HTML_MULTI)
    sm = _FakeSM()
    finders = Finders(state_manager=sm, url="https://x.com", snapshot_id="s1")
    query: FindQuery = {"kind": "css", "selector": "a[href='/home']"}  # type: ignore[assignment]
    result = await finders.find_first(doc, query, comment="home")
    assert result is not None
    pick, _ = result
    assert pick.element.rect.width == 0.0
    assert pick.element.rect.height == 0.0


@pytest.mark.anyio
async def test_find_first_populates_rect_from_page() -> None:
    """With a page argument, _try_fetch_rect resolves the unique_selector
    to a live element and copies its bounding_box into pick.element.rect."""
    doc = parse_html(_HTML_MULTI)
    sm = _FakeSM()
    from frontprompt.analysis._impl.scrapling_bridge import find_elements

    matches = find_elements(doc, {"css": "a[href='/home']"})
    expected_selector = matches[0].unique_selector
    assert expected_selector is not None
    fake_page = _FakePage({expected_selector: {"x": 12.5, "y": 34.0, "width": 200.0, "height": 24.0}})
    finders = Finders(state_manager=sm, url="https://x.com", snapshot_id="s1", page=fake_page)
    query: FindQuery = {"kind": "css", "selector": "a[href='/home']"}  # type: ignore[assignment]
    result = await finders.find_first(doc, query, comment="home")
    assert result is not None
    pick, _ = result
    assert pick.element.rect.x == 12.5
    assert pick.element.rect.y == 34.0
    assert pick.element.rect.width == 200.0
    assert pick.element.rect.height == 24.0
    assert expected_selector in fake_page.calls


@pytest.mark.anyio
async def test_find_by_text_populates_rect_per_match() -> None:
    """Multi-match finders perform one Playwright round-trip per pick;
    each pick gets its own bounding box, not the first one for all of them."""
    doc = parse_html(_HTML_MULTI)
    sm = _FakeSM()
    from frontprompt.analysis._impl.scrapling_bridge import find_elements

    cards = find_elements(doc, {"css": ".card"})
    assert len(cards) == 3
    rects_map = {
        cards[0].unique_selector: {"x": 10.0, "y": 10.0, "width": 100.0, "height": 50.0},
        cards[1].unique_selector: {"x": 10.0, "y": 70.0, "width": 100.0, "height": 50.0},
        cards[2].unique_selector: {"x": 10.0, "y": 130.0, "width": 100.0, "height": 50.0},
    }
    fake_page = _FakePage(rects_map)  # type: ignore[arg-type]
    finders = Finders(state_manager=sm, url="https://x.com", snapshot_id="s1", page=fake_page)
    result = await finders.find_by_text(doc, text="card", role=None, comment="cards", limit=10, parent_match=None)
    assert result.captured == 3
    ys = sorted(p.element.rect.y for p in sm.picks)
    assert ys == [10.0, 70.0, 130.0]


@pytest.mark.anyio
async def test_rect_fetch_falls_back_to_zero_when_query_returns_none() -> None:
    """Graceful fallback: when page.query_selector returns None, leave rect zeroed."""
    doc = parse_html(_HTML_MULTI)
    sm = _FakeSM()
    fake_page = _FakePage({})  # empty — every query returns None
    finders = Finders(state_manager=sm, url="https://x.com", snapshot_id="s1", page=fake_page)
    query: FindQuery = {"kind": "css", "selector": "a[href='/home']"}  # type: ignore[assignment]
    result = await finders.find_first(doc, query, comment="home")
    assert result is not None
    pick, _ = result
    assert pick.element.rect.width == 0.0
    assert pick.element.rect.height == 0.0
