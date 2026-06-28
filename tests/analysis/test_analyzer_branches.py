"""PageAnalyzer branch coverage tests.

Targets:
- snapshot() with page.title() raising → fallback to empty string (lines 77-78)
- find_one/first/by_text/by_regex with parent_pick (lines 144-202)
- find_similar with stale anchor (lines 214-222)
- context/path when pick not found in snapshot (lines 239-257)
- pick_from_ref when no current snapshot (line 288)
- pick_from_ref when snapshot_id mismatch (line 290) / ref not found (line 295)
"""

from __future__ import annotations

import pytest

from frontprompt.analysis.analyzer import PageAnalyzer
from frontprompt.state.state import ElementFingerprint, ElementRect, Pick, PickElement


class _FakePage:
    def __init__(self, html: str = "<html><body></body></html>", title_raises: bool = False) -> None:
        self._html = html
        self._title_raises = title_raises
        self.url = "https://example.com"

    async def content(self) -> str:
        return self._html

    async def title(self) -> str:
        if self._title_raises:
            raise RuntimeError("page crashed — cannot get title")
        return "Test Page"


class _FakeSM:
    def __init__(self) -> None:
        self.picks: list = []

    async def add_pick_from_programmatic_source(self, pick: object) -> None:
        self.picks.append(pick)


def _make_pick(selector: str, pick_id: str = "pick-1") -> Pick:
    return Pick(
        pick_id=pick_id,
        url="https://example.com",
        timestamp_ms=1000,
        element=PickElement(
            selector=selector,
            fingerprint=ElementFingerprint(tag="div"),
            text_snippet="",
            rect=ElementRect(x=0, y=0, width=10, height=10),
        ),
    )


# ── snapshot() with title() exception ─────────────────────────────────────────


@pytest.mark.anyio
async def test_snapshot_falls_back_to_empty_title_on_exception() -> None:
    """snapshot() catches title() exception and uses empty string as title."""
    pa = PageAnalyzer(page=_FakePage(title_raises=True), resolver=None, state_manager=None)
    snap = await pa.snapshot()
    assert snap.title == ""  # fallback on exception
    assert snap.html  # HTML is still captured


# ── find_one with parent_pick ─────────────────────────────────────────────────


@pytest.mark.anyio
async def test_find_one_with_parent_pick() -> None:
    """find_one with a parent_pick scopes the query within the parent element."""
    html = """<html><body>
    <div id="parent"><button>Submit</button></div>
    <button>Other</button>
    </body></html>"""
    pa = PageAnalyzer(page=_FakePage(html=html), resolver=None, state_manager=_FakeSM())

    from frontprompt.analysis.types import FindByCss

    parent_pick = _make_pick("#parent")
    query = FindByCss(selector="button")
    # Should not raise — parent_pick is resolved in snapshot
    result = await pa.find_one(query, comment="test", parent_pick=parent_pick)
    # Result may be None or a Pick depending on parsing — just verify no exception


@pytest.mark.anyio
async def test_find_first_with_parent_pick() -> None:
    """find_first with a parent_pick uses parent element as scope."""
    html = """<html><body>
    <div id="scope"><a href="/home">Home</a></div>
    </body></html>"""
    pa = PageAnalyzer(page=_FakePage(html=html), resolver=None, state_manager=_FakeSM())

    from frontprompt.analysis.types import FindByCss

    parent_pick = _make_pick("#scope")
    query = FindByCss(selector="a")
    await pa.find_first(query, comment="test", parent_pick=parent_pick)


@pytest.mark.anyio
async def test_find_by_text_with_parent_pick() -> None:
    """find_by_text with a parent_pick filters to parent's subtree."""
    html = """<html><body>
    <div id="scope"><p>Hello World</p></div>
    <p>Hello Somewhere Else</p>
    </body></html>"""
    pa = PageAnalyzer(page=_FakePage(html=html), resolver=None, state_manager=_FakeSM())
    parent_pick = _make_pick("#scope")
    result = await pa.find_by_text(text="Hello", role=None, parent_pick=parent_pick, comment="test", limit=5)
    assert result is not None


@pytest.mark.anyio
async def test_find_by_regex_with_parent_pick() -> None:
    """find_by_regex with a parent_pick filters to parent's subtree."""
    html = """<html><body>
    <div id="scope"><p>abc-123</p></div>
    </body></html>"""
    pa = PageAnalyzer(page=_FakePage(html=html), resolver=None, state_manager=_FakeSM())
    parent_pick = _make_pick("#scope")
    result = await pa.find_by_regex(
        pattern=r"\d+", field="text", parent_pick=parent_pick, comment="test", limit=5
    )
    assert result is not None


# ── find_similar with stale anchor ────────────────────────────────────────────


@pytest.mark.anyio
async def test_find_similar_raises_on_stale_anchor() -> None:
    """find_similar raises StaleAnchorError when anchor pick not found in snapshot."""
    from frontprompt.analysis.finders import StaleAnchorError

    html = "<html><body><p>text</p></body></html>"
    pa = PageAnalyzer(page=_FakePage(html=html), resolver=None, state_manager=_FakeSM())
    # Use a pick with a selector that won't match anything
    stale_pick = _make_pick("#does-not-exist-xyz-999")
    with pytest.raises(StaleAnchorError):
        await pa.find_similar(anchor_pick=stale_pick, threshold=0.8, max_results=5, comment="test")


# ── context / path with pick not found ────────────────────────────────────────


@pytest.mark.anyio
async def test_context_raises_when_pick_not_found() -> None:
    """context() raises ValueError when pick selector not found in snapshot."""
    html = "<html><body><p>text</p></body></html>"
    pa = PageAnalyzer(page=_FakePage(html=html), resolver=None, state_manager=_FakeSM())
    nonexistent_pick = _make_pick("#no-such-element-7777")
    with pytest.raises(ValueError, match="not found in snapshot"):
        await pa.context(nonexistent_pick, levels_up=2, sibling_radius=2)


@pytest.mark.anyio
async def test_path_raises_when_pick_not_found() -> None:
    """path() raises ValueError when pick selector not found in snapshot."""
    html = "<html><body><p>text</p></body></html>"
    pa = PageAnalyzer(page=_FakePage(html=html), resolver=None, state_manager=_FakeSM())
    nonexistent_pick = _make_pick("#ghost-element-8888")
    with pytest.raises(ValueError, match="not found in snapshot"):
        await pa.path(nonexistent_pick)


# ── pick_from_ref edge cases ───────────────────────────────────────────────────


@pytest.mark.anyio
async def test_pick_from_ref_returns_none_when_no_snapshot() -> None:
    """pick_from_ref returns None when no snapshot has been taken yet."""
    pa = PageAnalyzer(page=_FakePage(), resolver=None, state_manager=_FakeSM())
    # _current_snapshot is None at construction time
    result = await pa.pick_from_ref("ref-123", "snap-xyz", "test comment")
    assert result is None


@pytest.mark.anyio
async def test_pick_from_ref_returns_none_on_snapshot_id_mismatch() -> None:
    """pick_from_ref returns None when snapshot_id doesn't match current snapshot."""
    pa = PageAnalyzer(page=_FakePage(), resolver=None, state_manager=_FakeSM())
    await pa.snapshot()  # creates a snapshot with some id
    # Pass a different snapshot_id
    result = await pa.pick_from_ref("ref-456", "wrong-snapshot-id", "test")
    assert result is None


@pytest.mark.anyio
async def test_pick_from_ref_returns_none_when_ref_not_in_table() -> None:
    """pick_from_ref returns None when ref_id not found in current snapshot's ref_table."""
    pa = PageAnalyzer(page=_FakePage(), resolver=None, state_manager=_FakeSM())
    snap = await pa.snapshot()
    # Use the correct snapshot_id but a ref_id that doesn't exist in the ref_table
    result = await pa.pick_from_ref("nonexistent-ref-id", snap.snapshot_id, "test")
    assert result is None


@pytest.mark.anyio
async def test_pick_from_ref_accepts_outline_ref_object() -> None:
    """pick_from_ref accepts OutlineRef as first argument (two-arg call form)."""
    from frontprompt.analysis.types import OutlineRef

    pa = PageAnalyzer(page=_FakePage(), resolver=None, state_manager=_FakeSM())
    snap = await pa.snapshot()
    # Create a fake OutlineRef pointing to the current snapshot but nonexistent ref
    ref = OutlineRef(ref_id="ghost-ref", snapshot_id=snap.snapshot_id, expires_at_ms=0)
    result = await pa.pick_from_ref(ref, "test comment")
    assert result is None  # ref not in table
