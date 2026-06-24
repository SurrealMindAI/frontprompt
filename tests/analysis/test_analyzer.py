"""PageAnalyzer tests — snapshot lifecycle + integration tests.

Sub-plan 01: snapshot lifecycle tests (constructor, caching, invalidation, TTL).
Sub-plan 02: integration tests (outline, find_by_text, pick_from_ref, relocate, inspect).
             Integration tests require Playwright chromium (pytest.mark.integration).
"""

from __future__ import annotations

import time

import pytest

from frontprompt.analysis.analyzer import PageAnalyzer


class FakePage:
    def __init__(self, html: str = "<html><body></body></html>") -> None:
        self._html = html
        self.content_calls = 0
        self.url = "https://example.com"

    async def content(self) -> str:
        self.content_calls += 1
        return self._html

    async def title(self) -> str:
        return "Test Page"


@pytest.fixture
def analyzer() -> PageAnalyzer:
    return PageAnalyzer(page=FakePage(), resolver=None, state_manager=None)


# ── Snapshot lifecycle tests (sub-plan 01) ────────────────────────────────────


@pytest.mark.anyio
async def test_constructor_succeeds() -> None:
    pa = PageAnalyzer(page=FakePage(), resolver=None, state_manager=None)
    assert pa is not None


@pytest.mark.anyio
async def test_snapshot_calls_page_content(analyzer: PageAnalyzer) -> None:
    snap = await analyzer.snapshot()
    assert snap.html == "<html><body></body></html>"


@pytest.mark.anyio
async def test_snapshot_caches(analyzer: PageAnalyzer) -> None:
    snap1 = await analyzer.snapshot()
    snap2 = await analyzer.snapshot()
    assert snap1.snapshot_id == snap2.snapshot_id


@pytest.mark.anyio
async def test_snapshot_fresh_bypasses_cache(analyzer: PageAnalyzer) -> None:
    snap1 = await analyzer.snapshot()
    snap2 = await analyzer.snapshot(fresh=True)
    assert snap1.snapshot_id != snap2.snapshot_id


@pytest.mark.anyio
async def test_invalidate_clears_cache(analyzer: PageAnalyzer) -> None:
    snap1 = await analyzer.snapshot()
    analyzer.invalidate_snapshot()
    snap2 = await analyzer.snapshot()
    assert snap1.snapshot_id != snap2.snapshot_id


@pytest.mark.anyio
async def test_snapshot_auto_refreshes_after_ttl_expiry() -> None:
    pa = PageAnalyzer(page=FakePage(), resolver=None, state_manager=None, snapshot_ttl_seconds=0.001)
    snap1 = await pa.snapshot()
    time.sleep(0.01)
    snap2 = await pa.snapshot()
    assert snap1.snapshot_id != snap2.snapshot_id


# ── Unit-level method tests (sub-plan 02, no browser) ────────────────────────


class _FakeSM:
    def __init__(self) -> None:
        self.picks: list = []

    async def add_pick_from_programmatic_source(self, pick: object) -> None:
        self.picks.append(pick)


@pytest.mark.anyio
async def test_outline_on_simple_html() -> None:
    """outline() returns a PageOutline with headings from FakePage HTML."""
    html = """<html><head><title>Test</title></head>
<body><h1>Hello</h1><a href="/about">About</a></body></html>"""
    pa = PageAnalyzer(page=FakePage(html=html), resolver=None, state_manager=_FakeSM())
    outline = await pa.outline()
    assert outline.snapshot_id
    assert len(outline.headings) == 1
    assert outline.headings[0].text == "Hello"


@pytest.mark.anyio
async def test_find_by_text_on_simple_html() -> None:
    """find_by_text returns FindResult with correct total_matches."""
    html = """<html><body>
<button>Save</button><button>Cancel</button>
</body></html>"""
    pa = PageAnalyzer(page=FakePage(html=html), resolver=None, state_manager=_FakeSM())
    result = await pa.find_by_text(text="Save", role=None, parent_pick=None, comment="test", limit=5)
    assert result.total_matches >= 1


@pytest.mark.anyio
async def test_condensed_html_returns_string() -> None:
    """condensed_html() returns a CondensedHtml with non-empty html."""
    html = "<html><body><p>Hello world</p></body></html>"
    pa = PageAnalyzer(page=FakePage(html=html), resolver=None, state_manager=_FakeSM())
    result = await pa.condensed_html()
    assert result.html
    assert result.original_chars > 0


@pytest.mark.anyio
async def test_pick_from_ref_after_outline() -> None:
    """pick_from_ref materialises a Pick from an outline ref."""
    html = """<html><head><title>Test</title></head>
<body><a href="/about">About</a></body></html>"""
    pa = PageAnalyzer(page=FakePage(html=html), resolver=None, state_manager=_FakeSM())
    outline = await pa.outline()
    assert outline.links, "need at least one link"
    ref = outline.links[0].ref
    # Call with OutlineRef form
    pick = await pa.pick_from_ref(ref, comment="about link")
    assert pick is not None
    assert pick.pick_id


@pytest.mark.anyio
async def test_pick_from_ref_three_string_form() -> None:
    """pick_from_ref with (ref_id, snapshot_id, comment) 3-string form."""
    html = """<html><body><a href="/contact">Contact</a></body></html>"""
    pa = PageAnalyzer(page=FakePage(html=html), resolver=None, state_manager=_FakeSM())
    outline = await pa.outline()
    assert outline.links
    ref = outline.links[0].ref
    pick = await pa.pick_from_ref(ref.ref_id, ref.snapshot_id, "contact link")
    assert pick is not None


@pytest.mark.anyio
async def test_pick_from_ref_expired_snapshot_returns_none() -> None:
    """pick_from_ref with wrong snapshot_id returns None (expired ref)."""
    html = '<html><body><a href="/">Home</a></body></html>'
    pa = PageAnalyzer(page=FakePage(html=html), resolver=None, state_manager=_FakeSM())
    outline = await pa.outline()
    assert outline.links
    ref = outline.links[0].ref
    # Use wrong snapshot_id
    pick = await pa.pick_from_ref(ref.ref_id, "wrong-snapshot-id", "test")
    assert pick is None


@pytest.mark.anyio
async def test_relocate_fresh_pick_alive() -> None:
    """relocate on a freshly created pick returns alive or recovered."""
    html = """<html><body><button id="ok">OK</button></body></html>"""
    sm = _FakeSM()
    pa = PageAnalyzer(page=FakePage(html=html), resolver=None, state_manager=sm)
    await pa.find_by_text(text="OK", role=None, parent_pick=None, comment="ok button", limit=1)
    assert sm.picks
    reloc = await pa.relocate([sm.picks[-1]])
    assert reloc[0].status in ("alive", "recovered")


# ── Integration tests (sub-plan 02, require Playwright chromium) ──────────────


@pytest.fixture
async def analyzer_on_example() -> None:  # type: ignore[return]
    """PageAnalyzer wired to example.com."""
    from playwright.async_api import async_playwright

    from frontprompt.ipc.playwright_controller.controller import PlaywrightPageController
    from frontprompt.ipc.playwright_controller.element_resolver import ElementResolver
    from frontprompt.state.manager import StateManager

    async with async_playwright() as pw:
        browser = await pw.chromium.launch(headless=True)
        page = await browser.new_page()
        await page.goto("https://example.com")
        sm = StateManager(session_id="test-session")
        resolver = ElementResolver(page)
        pc = PlaywrightPageController(page, resolver)
        analyzer = PageAnalyzer(
            page=page,
            resolver=resolver,
            state_manager=sm,
            snapshot_ttl_seconds=30.0,
            page_controller=pc,
        )
        yield analyzer
        await browser.close()


@pytest.mark.anyio
@pytest.mark.integration
async def test_outline_returns_links(analyzer_on_example: PageAnalyzer) -> None:
    outline = await analyzer_on_example.outline()
    assert len(outline.links) > 0


@pytest.mark.anyio
@pytest.mark.integration
async def test_find_by_text_learn_more(analyzer_on_example: PageAnalyzer) -> None:
    """Smoke-test regression: find_by_text on example.com link must work.

    Note: example.com's link text changed pre-2026-05 from 'More information...' to
    'Learn more'. The yesterday-smoke-test 0-match finding was data-drift, not a bug.
    """
    result = await analyzer_on_example.find_by_text(
        text="Learn more",  # example.com link text (was "More information..." pre-2026-05)
        role=None,
        parent_pick=None,
        comment="example.com more info link",
        limit=5,
    )
    assert result.total_matches >= 1


@pytest.mark.anyio
@pytest.mark.integration
async def test_pick_from_ref_materialises_pick(analyzer_on_example: PageAnalyzer) -> None:
    outline = await analyzer_on_example.outline()
    assert outline.links, "need at least one link ref"
    ref = outline.links[0].ref
    pick = await analyzer_on_example.pick_from_ref(ref, comment="first link")
    assert pick is not None
    assert pick.pick_id


@pytest.mark.anyio
@pytest.mark.integration
async def test_relocate_fresh_pick_alive_integration(analyzer_on_example: PageAnalyzer) -> None:
    await analyzer_on_example.find_by_text(
        text="Learn more",
        role=None,
        parent_pick=None,
        comment="relocate test",
        limit=1,
    )
    sm = analyzer_on_example._state_manager
    picks = sm._inspector_state.picks
    assert picks
    reloc = await analyzer_on_example.relocate([picks[-1]])
    assert reloc[0].status in ("alive", "recovered")


@pytest.mark.anyio
@pytest.mark.integration
async def test_inspect_mixed_static_and_dynamic(analyzer_on_example: PageAnalyzer) -> None:
    await analyzer_on_example.find_by_text(
        text="Learn more",
        role=None,
        parent_pick=None,
        comment="inspect test",
        limit=1,
    )
    sm = analyzer_on_example._state_manager
    picks = sm._inspector_state.picks
    assert picks
    results = await analyzer_on_example.inspect([picks[-1]], fields=["text", "visible", "enabled"])
    assert len(results) == 1
    assert results[0].error is None
    assert results[0].text is not None
