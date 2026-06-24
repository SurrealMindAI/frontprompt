"""ProgrammaticPickService tests — StateManager.add_pick_from_programmatic_source
and ProgrammaticPickService integration with FakePageController."""

from __future__ import annotations

from typing import Any

import pytest

from frontprompt.ipc.playwright_controller.element_resolver import StalePickError
from frontprompt.state.manager import StateManager
from frontprompt.state.programmatic_picks import ProgrammaticPickService
from frontprompt.state.state import ElementFingerprint, ElementRect, Pick, PickElement
from tests.ipc.fakes import FakePageController


def _make_pick(pick_id: str = "pick-001", comment: str = "test") -> Pick:
    return Pick(
        pick_id=pick_id,
        url="https://example.com/",
        timestamp_ms=1_700_000_000_000,
        element=PickElement(
            selector=f"#{pick_id}",
            fingerprint=ElementFingerprint(tag="div"),
            text_snippet="x",
            rect=ElementRect(x=0.0, y=0.0, width=10.0, height=10.0),
        ),
        comment=comment,
    )


def _el_data(selector: str = "div.x") -> dict[str, Any]:
    """Minimal element descriptor dict for FakePageController.selector_matches."""
    return {
        "selector": selector,
        "fingerprint": {
            "tag": "div",
            "attributes": {},
            "text": "",
            "path": [],
            "parent_name": None,
            "parent_attribs": {},
            "parent_text": "",
            "siblings": [],
            "children": [],
        },
        "rect": {"x": 0.0, "y": 0.0, "width": 100.0, "height": 30.0},
        "text_snippet": "click me",
        "url": "https://example.com/",
        "timestamp_ms": 1_700_000_000_000,
        "color_index": 0,
    }


# ---------------------------------------------------------------------------
# StateManager.add_pick_from_programmatic_source tests (Step A)
# ---------------------------------------------------------------------------


@pytest.mark.anyio
async def test_add_pick_from_programmatic_source_appears_in_snapshot() -> None:
    mgr = StateManager(session_id="test-session")
    pick = _make_pick("p1")
    await mgr.add_pick_from_programmatic_source(pick)
    snap = mgr.snapshot()
    assert len(snap.inspector_state.picks) == 1
    assert snap.inspector_state.picks[0].pick_id == "p1"


@pytest.mark.anyio
async def test_add_pick_programmatic_does_not_activate() -> None:
    mgr = StateManager(session_id="test-session")
    pick = _make_pick("p1")
    await mgr.add_pick_from_programmatic_source(pick)
    snap = mgr.snapshot()
    assert snap.inspector_state.active_pick_id is None
    assert snap.inspector_state.active is False


@pytest.mark.anyio
async def test_add_pick_programmatic_replaces_by_id() -> None:
    mgr = StateManager(session_id="test-session")
    await mgr.add_pick_from_programmatic_source(_make_pick("p1", comment="first"))
    await mgr.add_pick_from_programmatic_source(_make_pick("p1", comment="second"))
    snap = mgr.snapshot()
    assert len(snap.inspector_state.picks) == 1
    assert snap.inspector_state.picks[0].comment == "second"


@pytest.mark.anyio
async def test_add_pick_programmatic_notifies_listeners() -> None:
    mgr = StateManager(session_id="test-session")
    fired: list[int] = []
    mgr.add_snapshot_listener(lambda _snap: fired.append(1))
    await mgr.add_pick_from_programmatic_source(_make_pick("p1"))
    assert fired == [1]


# ---------------------------------------------------------------------------
# ProgrammaticPickService tests (Step C)
# ---------------------------------------------------------------------------


@pytest.mark.anyio
async def test_pick_by_selector_creates_n_picks() -> None:
    mgr = StateManager(session_id="test-session")
    fake = FakePageController()
    fake.selector_matches[".btn"] = [
        _el_data(".btn:nth-of-type(1)"),
        _el_data(".btn:nth-of-type(2)"),
        _el_data(".btn:nth-of-type(3)"),
    ]
    svc = ProgrammaticPickService(mgr, fake)
    result = await svc.pick_by_selector(".btn", "buttons", None, 10)
    assert result["total_matches"] == 3
    assert result["captured"] == 3
    assert len(result["pick_ids"]) == 3
    snap = mgr.snapshot()
    assert len(snap.inspector_state.picks) == 3


@pytest.mark.anyio
async def test_pick_by_selector_auto_suffixes_comments() -> None:
    mgr = StateManager(session_id="test-session")
    fake = FakePageController()
    fake.selector_matches[".x"] = [_el_data() for _ in range(3)]
    svc = ProgrammaticPickService(mgr, fake)
    await svc.pick_by_selector(".x", "items", None, 10)
    snap = mgr.snapshot()
    comments = [p.comment for p in snap.inspector_state.picks]
    assert comments == ["items [match 1/3]", "items [match 2/3]", "items [match 3/3]"]


@pytest.mark.anyio
async def test_pick_by_selector_respects_limit() -> None:
    mgr = StateManager(session_id="test-session")
    fake = FakePageController()
    fake.selector_matches[".x"] = [_el_data() for _ in range(30)]
    svc = ProgrammaticPickService(mgr, fake)
    result = await svc.pick_by_selector(".x", "x", None, 5)
    assert result["total_matches"] == 30
    assert result["captured"] == 5
    snap = mgr.snapshot()
    assert len(snap.inspector_state.picks) == 5


@pytest.mark.anyio
async def test_pick_by_selector_zero_matches_no_error() -> None:
    mgr = StateManager(session_id="test-session")
    fake = FakePageController()
    fake.selector_matches[".gone"] = []
    svc = ProgrammaticPickService(mgr, fake)
    result = await svc.pick_by_selector(".gone", "gone", None, 10)
    assert result == {"pick_ids": [], "total_matches": 0, "captured": 0}
    snap = mgr.snapshot()
    assert snap.inspector_state.picks == []


@pytest.mark.anyio
async def test_pick_by_selector_parent_stale_hard_fail() -> None:
    """svc takes Pick object now, parent_pick.pick_id triggers stale check."""
    mgr = StateManager(session_id="test-session")
    fake = FakePageController()
    fake.stale_picks.add("parent-1")
    svc = ProgrammaticPickService(mgr, fake)
    parent = _make_pick("parent-1", comment="parent")
    with pytest.raises(StalePickError):
        await svc.pick_by_selector(".x", "x", parent, 10)
    snap = mgr.snapshot()
    assert snap.inspector_state.picks == []


@pytest.mark.anyio
async def test_pick_by_text_with_role() -> None:
    mgr = StateManager(session_id="test-session")
    fake = FakePageController()
    fake.selector_matches["__text_role__:Submit|button"] = [_el_data("button.submit")]
    svc = ProgrammaticPickService(mgr, fake)
    result = await svc.pick_by_text("Submit", "button", "submit-btn", None, 10)
    assert result["captured"] == 1
    snap = mgr.snapshot()
    assert snap.inspector_state.picks[0].comment == "submit-btn [match 1/1]"


@pytest.mark.anyio
async def test_pick_by_text_without_role() -> None:
    mgr = StateManager(session_id="test-session")
    fake = FakePageController()
    fake.selector_matches["__text__:Click me"] = [_el_data(), _el_data()]
    svc = ProgrammaticPickService(mgr, fake)
    result = await svc.pick_by_text("Click me", None, "clickable", None, 10)
    assert result["captured"] == 2
    snap = mgr.snapshot()
    assert len(snap.inspector_state.picks) == 2


# ── analyzer-delegating pick_by_text tests (sub-plan 03) ─────────────────────


@pytest.mark.anyio
async def test_pick_by_text_delegates_to_analyzer_find_by_text() -> None:
    """When analyzer is wired, pick_by_text calls analyzer.find_by_text.
    (FindResult has .pick_ids not .picks; find_by_text persists picks)
    """
    from unittest.mock import AsyncMock, MagicMock

    mgr = StateManager(session_id="test-session")
    fake_pc = FakePageController()

    # Build a minimal FindResult mock (matches sub-plan 01 FindResult shape)
    find_result = MagicMock()
    find_result.pick_ids = ["p1"]
    find_result.total_matches = 1
    find_result.captured = 1

    mock_analyzer = MagicMock()
    mock_analyzer.find_by_text = AsyncMock(return_value=find_result)

    svc = ProgrammaticPickService(mgr, fake_pc, analyzer=mock_analyzer)
    result = await svc.pick_by_text("More information", None, "link", None, 10)

    mock_analyzer.find_by_text.assert_called_once_with(
        text="More information",
        role=None,
        parent_pick=None,
        comment="link",
        limit=10,
    )
    assert result == {"pick_ids": ["p1"], "total_matches": 1, "captured": 1}


@pytest.mark.anyio
async def test_pick_by_text_without_analyzer_uses_legacy_path() -> None:
    """Without analyzer, pick_by_text uses the existing pseudo-selector path."""
    mgr = StateManager(session_id="test-session")
    fake = FakePageController()
    fake.selector_matches["__text__:Click me"] = [_el_data(), _el_data()]
    svc = ProgrammaticPickService(mgr, fake)  # no analyzer
    result = await svc.pick_by_text("Click me", None, "clickable", None, 10)
    assert result["captured"] == 2


@pytest.mark.anyio
async def test_pick_from_xpath_elements_creates_picks() -> None:
    """pick_from_xpath_elements materializes Picks from raw xpath result."""
    mgr = StateManager(session_id="test-session")
    fake = FakePageController()
    svc = ProgrammaticPickService(mgr, fake)
    elements_result = {
        "total_matches": 2,
        "elements": [_el_data("li:nth-of-type(1)"), _el_data("li:nth-of-type(2)")],
    }
    result = await svc.pick_from_xpath_elements(elements_result, "nav item")
    assert result["total_matches"] == 2
    assert result["captured"] == 2
    assert len(result["pick_ids"]) == 2
    snap = mgr.snapshot()
    assert len(snap.inspector_state.picks) == 2
    assert snap.inspector_state.picks[0].comment == "nav item [match 1/2]"


@pytest.mark.anyio
async def test_pick_from_xpath_elements_zero_results() -> None:
    mgr = StateManager(session_id="test-session")
    fake = FakePageController()
    svc = ProgrammaticPickService(mgr, fake)
    result = await svc.pick_from_xpath_elements({"total_matches": 0, "elements": []}, "x")
    assert result == {"pick_ids": [], "total_matches": 0, "captured": 0}
