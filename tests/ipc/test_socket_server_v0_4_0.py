"""Socket-server dispatch tests for v0.4.0 PageAnalyzer + low-level routes.

Tests the 14 new dispatch routes added in sub-plan 04. Uses FakePageAnalyzer
+ FakePageController. No Playwright required.

Uses socket_path from tests/ipc/conftest.py.
"""

from __future__ import annotations

import stat as _stat
from pathlib import Path

import anyio
import pytest

from frontprompt.ipc import (
    query,
    run_socket_server,
)
from frontprompt.ipc.protocol import (
    DomPatchRequest,
    EvalJsRequest,
    FindByRegexRequest,
    FindFirstRequest,
    FindOneRequest,
    FindSimilarRequest,
    GetElementContextRequest,
    GetPageHtmlRequest,
    GetPageOutlineRequest,
    InspectElementsRequest,
    PickByXpathRequest,
    PickFromRefRequest,
    PickPathRequest,
    RelocatePicksRequest,
)
from frontprompt.state import StateManager
from frontprompt.state.state import (
    ElementFingerprint,
    ElementRect,
    Pick,
    PickElement,
)
from tests.ipc.fakes import FakePageAnalyzer, FakePageController


def _make_pick(pick_id: str = "p1", comment: str = "") -> Pick:
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


async def _wait_for_socket(path: Path, attempts: int = 50, delay: float = 0.02) -> None:
    for _ in range(attempts):
        try:
            mode = path.stat().st_mode
            if _stat.S_ISSOCK(mode):
                return
        except OSError:
            pass
        await anyio.sleep(delay)
    raise RuntimeError(f"unix-socket {path} not created within {attempts * delay}s")


# ---------------------------------------------------------------------------
# PageAnalyzer high-level routes
# ---------------------------------------------------------------------------


@pytest.mark.anyio
async def test_get_page_outline_dispatch(socket_path: Path) -> None:
    sm = StateManager(session_id="test-session")
    fake_controller = FakePageController()
    fake_analyzer = FakePageAnalyzer()

    async with anyio.create_task_group() as tg:
        tg.start_soon(run_socket_server, sm, socket_path, fake_controller, None, fake_analyzer)
        await _wait_for_socket(socket_path)

        resp = await query(socket_path, GetPageOutlineRequest())
        assert resp.ok is True
        assert "headings" in resp.data
        assert "links" in resp.data
        tg.cancel_scope.cancel()


@pytest.mark.anyio
async def test_get_page_html_dispatch(socket_path: Path) -> None:
    sm = StateManager(session_id="test-session")
    fake_controller = FakePageController()
    fake_analyzer = FakePageAnalyzer()

    async with anyio.create_task_group() as tg:
        tg.start_soon(run_socket_server, sm, socket_path, fake_controller, None, fake_analyzer)
        await _wait_for_socket(socket_path)

        resp = await query(socket_path, GetPageHtmlRequest())
        assert resp.ok is True
        assert isinstance(resp.data["html"], str)
        tg.cancel_scope.cancel()


@pytest.mark.anyio
async def test_pick_from_ref_happy(socket_path: Path) -> None:
    sm = StateManager(session_id="test-session")
    fake_controller = FakePageController()
    fake_analyzer = FakePageAnalyzer()
    fake_analyzer._known_refs["ref:link:abc123"] = "pick-materialized-1"

    async with anyio.create_task_group() as tg:
        tg.start_soon(run_socket_server, sm, socket_path, fake_controller, None, fake_analyzer)
        await _wait_for_socket(socket_path)

        resp = await query(
            socket_path,
            PickFromRefRequest(ref_id="ref:link:abc123", snapshot_id="snap-1", comment="test ref"),
        )
        assert resp.ok is True
        assert resp.data["pick_id"] == "pick-materialized-1"
        tg.cancel_scope.cancel()


@pytest.mark.anyio
async def test_pick_from_ref_expired(socket_path: Path) -> None:
    sm = StateManager(session_id="test-session")
    fake_controller = FakePageController()
    fake_analyzer = FakePageAnalyzer()
    # no refs registered → expired

    async with anyio.create_task_group() as tg:
        tg.start_soon(run_socket_server, sm, socket_path, fake_controller, None, fake_analyzer)
        await _wait_for_socket(socket_path)

        resp = await query(
            socket_path,
            PickFromRefRequest(ref_id="ref:unknown:xyz", snapshot_id="snap-ghost", comment="test"),
        )
        assert resp.ok is True
        assert resp.data["error"] == "ref_expired"
        tg.cancel_scope.cancel()


@pytest.mark.anyio
async def test_find_one_happy(socket_path: Path) -> None:
    sm = StateManager(session_id="test-session")
    fake_controller = FakePageController()
    fake_analyzer = FakePageAnalyzer()
    fake_analyzer.find_one_result = {"pick_id": "found-pick-1"}

    async with anyio.create_task_group() as tg:
        tg.start_soon(run_socket_server, sm, socket_path, fake_controller, None, fake_analyzer)
        await _wait_for_socket(socket_path)

        resp = await query(
            socket_path,
            FindOneRequest(query={"kind": "text", "text": "Submit"}, comment="submit btn"),
        )
        assert resp.ok is True
        assert resp.data["pick_id"] == "found-pick-1"
        tg.cancel_scope.cancel()


@pytest.mark.anyio
async def test_find_one_ambiguous(socket_path: Path) -> None:
    sm = StateManager(session_id="test-session")
    fake_controller = FakePageController()
    fake_analyzer = FakePageAnalyzer()
    fake_analyzer.find_one_result = {"error": "ambiguous", "total_matches": 3}

    async with anyio.create_task_group() as tg:
        tg.start_soon(run_socket_server, sm, socket_path, fake_controller, None, fake_analyzer)
        await _wait_for_socket(socket_path)

        resp = await query(
            socket_path,
            FindOneRequest(query={"kind": "css", "selector": "div.item"}, comment="items"),
        )
        assert resp.ok is True
        assert resp.data["error"] == "ambiguous"
        tg.cancel_scope.cancel()


@pytest.mark.anyio
async def test_find_one_not_found(socket_path: Path) -> None:
    sm = StateManager(session_id="test-session")
    fake_controller = FakePageController()
    fake_analyzer = FakePageAnalyzer()
    fake_analyzer.find_one_result = None  # not found

    async with anyio.create_task_group() as tg:
        tg.start_soon(run_socket_server, sm, socket_path, fake_controller, None, fake_analyzer)
        await _wait_for_socket(socket_path)

        resp = await query(
            socket_path,
            FindOneRequest(query={"kind": "text", "text": "nonexistent"}, comment="none"),
        )
        assert resp.ok is True
        assert resp.data["error"] == "not_found"
        tg.cancel_scope.cancel()


@pytest.mark.anyio
async def test_find_first_happy(socket_path: Path) -> None:
    sm = StateManager(session_id="test-session")
    fake_controller = FakePageController()
    fake_analyzer = FakePageAnalyzer()
    fake_analyzer.find_first_result = {"pick_id": "first-pick", "total_matches": 5}

    async with anyio.create_task_group() as tg:
        tg.start_soon(run_socket_server, sm, socket_path, fake_controller, None, fake_analyzer)
        await _wait_for_socket(socket_path)

        resp = await query(
            socket_path,
            FindFirstRequest(query={"kind": "css", "selector": "div.item"}, comment="first item"),
        )
        assert resp.ok is True
        assert resp.data["pick_id"] == "first-pick"
        assert resp.data["total_matches"] == 5
        tg.cancel_scope.cancel()


@pytest.mark.anyio
async def test_find_similar_dispatch(socket_path: Path) -> None:
    sm = StateManager(session_id="test-session")
    anchor = _make_pick("anchor-1")
    await sm.add_pick(anchor)
    fake_controller = FakePageController()
    fake_analyzer = FakePageAnalyzer()
    fake_analyzer.find_result = {"pick_ids": ["similar-1", "similar-2"], "total_matches": 2, "captured": 2}

    async with anyio.create_task_group() as tg:
        tg.start_soon(run_socket_server, sm, socket_path, fake_controller, None, fake_analyzer)
        await _wait_for_socket(socket_path)

        resp = await query(
            socket_path,
            FindSimilarRequest(anchor_pick_id="anchor-1", comment="similar items"),
        )
        assert resp.ok is True
        assert isinstance(resp.data["pick_ids"], list)
        tg.cancel_scope.cancel()


@pytest.mark.anyio
async def test_find_by_regex_dispatch(socket_path: Path) -> None:
    sm = StateManager(session_id="test-session")
    fake_controller = FakePageController()
    fake_analyzer = FakePageAnalyzer()
    fake_analyzer.find_result = {"pick_ids": ["r1"], "total_matches": 1, "captured": 1}

    async with anyio.create_task_group() as tg:
        tg.start_soon(run_socket_server, sm, socket_path, fake_controller, None, fake_analyzer)
        await _wait_for_socket(socket_path)

        resp = await query(
            socket_path,
            FindByRegexRequest(pattern="Alpha|Beta", field="text", comment="regex test"),
        )
        assert resp.ok is True
        assert isinstance(resp.data["total_matches"], int)
        tg.cancel_scope.cancel()


@pytest.mark.anyio
async def test_get_element_context_dispatch(socket_path: Path) -> None:
    sm = StateManager(session_id="test-session")
    pick = _make_pick("ctx-pick-1")
    await sm.add_pick(pick)
    fake_controller = FakePageController()
    fake_analyzer = FakePageAnalyzer()

    async with anyio.create_task_group() as tg:
        tg.start_soon(run_socket_server, sm, socket_path, fake_controller, None, fake_analyzer)
        await _wait_for_socket(socket_path)

        resp = await query(
            socket_path,
            GetElementContextRequest(pick_id="ctx-pick-1"),
        )
        assert resp.ok is True
        assert "ancestors" in resp.data
        tg.cancel_scope.cancel()


@pytest.mark.anyio
async def test_pick_path_dispatch(socket_path: Path) -> None:
    sm = StateManager(session_id="test-session")
    pick = _make_pick("path-pick-1")
    await sm.add_pick(pick)
    fake_controller = FakePageController()
    fake_analyzer = FakePageAnalyzer()

    async with anyio.create_task_group() as tg:
        tg.start_soon(run_socket_server, sm, socket_path, fake_controller, None, fake_analyzer)
        await _wait_for_socket(socket_path)

        resp = await query(
            socket_path,
            PickPathRequest(pick_id="path-pick-1"),
        )
        assert resp.ok is True
        assert isinstance(resp.data["path"], list)
        tg.cancel_scope.cancel()


@pytest.mark.anyio
async def test_relocate_picks_dispatch(socket_path: Path) -> None:
    sm = StateManager(session_id="test-session")
    p1 = _make_pick("rel-1")
    p2 = _make_pick("rel-2")
    await sm.add_pick(p1)
    await sm.add_pick(p2)
    fake_controller = FakePageController()
    fake_analyzer = FakePageAnalyzer()

    async with anyio.create_task_group() as tg:
        tg.start_soon(run_socket_server, sm, socket_path, fake_controller, None, fake_analyzer)
        await _wait_for_socket(socket_path)

        resp = await query(
            socket_path,
            RelocatePicksRequest(),  # no pick_ids = relocate all
        )
        assert resp.ok is True
        assert isinstance(resp.data, list)
        assert len(resp.data) == 2
        tg.cancel_scope.cancel()


@pytest.mark.anyio
async def test_inspect_elements_dispatch(socket_path: Path) -> None:
    sm = StateManager(session_id="test-session")
    pick = _make_pick("insp-1")
    await sm.add_pick(pick)
    fake_controller = FakePageController()
    fake_analyzer = FakePageAnalyzer()

    async with anyio.create_task_group() as tg:
        tg.start_soon(run_socket_server, sm, socket_path, fake_controller, None, fake_analyzer)
        await _wait_for_socket(socket_path)

        resp = await query(
            socket_path,
            InspectElementsRequest(pick_ids=["insp-1"]),  # default fields
        )
        assert resp.ok is True
        assert isinstance(resp.data, list)
        # first entry: no errors, has text + role (from FakePageAnalyzer.inspect)
        entry = resp.data[0]
        assert "text" in entry
        assert "role" in entry
        tg.cancel_scope.cancel()


# ---------------------------------------------------------------------------
# Low-level escape routes
# ---------------------------------------------------------------------------


@pytest.mark.anyio
async def test_eval_js_dispatch(socket_path: Path) -> None:
    sm = StateManager(session_id="test-session")
    fake_controller = FakePageController()
    fake_controller.eval_js_responses["1+1"] = {"result": 2, "ok": True}
    fake_analyzer = FakePageAnalyzer()

    async with anyio.create_task_group() as tg:
        tg.start_soon(run_socket_server, sm, socket_path, fake_controller, None, fake_analyzer)
        await _wait_for_socket(socket_path)

        resp = await query(
            socket_path,
            EvalJsRequest(expression="1+1", mutating=False),
        )
        assert resp.ok is True
        assert resp.data["ok"] is True
        tg.cancel_scope.cancel()


@pytest.mark.anyio
async def test_dom_patch_dispatch(socket_path: Path) -> None:
    sm = StateManager(session_id="test-session")
    pick = _make_pick("patch-pick-1")
    await sm.add_pick(pick)
    fake_controller = FakePageController()
    fake_analyzer = FakePageAnalyzer()

    async with anyio.create_task_group() as tg:
        tg.start_soon(run_socket_server, sm, socket_path, fake_controller, None, fake_analyzer)
        await _wait_for_socket(socket_path)

        resp = await query(
            socket_path,
            DomPatchRequest(
                pick_id="patch-pick-1",
                operations=[{"op": "set_attribute", "name": "data-test", "value": "yes"}],
            ),
        )
        assert resp.ok is True
        assert resp.data["ok"] is True
        tg.cancel_scope.cancel()


@pytest.mark.anyio
async def test_pick_by_xpath_dispatch(socket_path: Path) -> None:
    sm = StateManager(session_id="test-session")
    fake_controller = FakePageController()
    fake_controller.xpath_matches["//div[@class='item']"] = [
        {
            "selector": "div.item:nth-child(1)",
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
            "text_snippet": "Alpha",
            "url": "https://example.com/",
            "timestamp_ms": 1_700_000_000_000,
            "color_index": 0,
        }
    ]
    fake_analyzer = FakePageAnalyzer()

    async with anyio.create_task_group() as tg:
        tg.start_soon(run_socket_server, sm, socket_path, fake_controller, None, fake_analyzer)
        await _wait_for_socket(socket_path)

        resp = await query(
            socket_path,
            PickByXpathRequest(xpath="//div[@class='item']", comment="xpath items"),
        )
        assert resp.ok is True
        assert isinstance(resp.data["pick_ids"], list)
        tg.cancel_scope.cancel()


# ---------------------------------------------------------------------------
# Pre-constructed once
# ---------------------------------------------------------------------------


@pytest.mark.anyio
async def test_page_analyzer_pre_constructed_once(socket_path: Path) -> None:
    """Verify FakePageAnalyzer is reused across requests (not re-constructed)."""
    sm = StateManager(session_id="test-session")
    pick = _make_pick("once-pick-1")
    await sm.add_pick(pick)
    fake_controller = FakePageController()
    fake_analyzer = FakePageAnalyzer()

    async with anyio.create_task_group() as tg:
        tg.start_soon(run_socket_server, sm, socket_path, fake_controller, None, fake_analyzer)
        await _wait_for_socket(socket_path)

        # Two requests — both should hit the same FakePageAnalyzer instance
        await query(socket_path, GetPageOutlineRequest())
        await query(socket_path, GetPageHtmlRequest())

        # call_count reflects both calls on the SAME instance
        assert fake_analyzer.call_count == 2
        tg.cancel_scope.cancel()
