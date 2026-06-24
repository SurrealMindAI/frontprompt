"""Socket-server dispatch tests for v0.3.0 scout tools.

Tests the 11 new dispatch routes added in sub-plan 02. Uses FakePageController
and real StateManager (in-memory). No Playwright required.

Uses short_socket_dir from tests/ipc/conftest.py (scout-mode: extracted from
test_server_client.py to avoid duplication).
"""

from __future__ import annotations

import stat as _stat
from pathlib import Path

import anyio
import pytest

from frontprompt.ipc import (
    GetAttributesRequest,
    GetHtmlRequest,
    GetOutlineRequest,
    GetPageInfoRequest,
    GetStateRequest,
    GetTextRequest,
    PickBySelectorRequest,
    PickByTextRequest,
    ScreenshotElementRequest,
    ScreenshotPageRequest,
    ScrollToRequest,
    query,
    run_socket_server,
)
from frontprompt.state import StateManager
from frontprompt.state.state import (
    ElementFingerprint,
    ElementRect,
    Pick,
    PickElement,
)
from tests.ipc.fakes import FakePageController


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


def _el_data(selector: str = "div.x") -> dict:
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


async def _wait_for_socket(path: Path, attempts: int = 50, delay: float = 0.02) -> None:
    for _ in range(attempts):
        try:
            mode = path.stat().st_mode
            if _stat.S_ISSOCK(mode):
                return
        except OSError:
            pass
        await anyio.sleep(delay)
    raise RuntimeError(f"unix-socket {path} wurde nicht innerhalb {attempts * delay}s erstellt")


# ---------------------------------------------------------------------------
# Pick-creator routes
# ---------------------------------------------------------------------------


@pytest.mark.anyio
async def test_pick_by_selector_dispatch_reaches_service(socket_path: Path) -> None:
    sm = StateManager(session_id="test-session")
    fake = FakePageController()
    fake.selector_matches[".btn"] = [_el_data(".btn:nth-child(1)"), _el_data(".btn:nth-child(2)")]

    async with anyio.create_task_group() as tg:
        tg.start_soon(run_socket_server, sm, socket_path, fake)
        await _wait_for_socket(socket_path)

        response = await query(socket_path, PickBySelectorRequest(selector=".btn", comment="buttons", limit=10))
        assert response.ok is True
        assert response.data["captured"] == 2
        assert response.data["total_matches"] == 2
        assert len(response.data["pick_ids"]) == 2
        snap = sm.snapshot()
        assert len(snap.inspector_state.picks) == 2
        tg.cancel_scope.cancel()


@pytest.mark.anyio
async def test_pick_by_selector_parent_stale_returns_error(socket_path: Path) -> None:
    sm = StateManager(session_id="test-session")
    parent = _make_pick("parent-1")
    await sm.add_pick(parent)

    fake = FakePageController()
    fake.stale_picks.add("parent-1")

    async with anyio.create_task_group() as tg:
        tg.start_soon(run_socket_server, sm, socket_path, fake)
        await _wait_for_socket(socket_path)

        response = await query(
            socket_path,
            PickBySelectorRequest(selector=".x", comment="x", parent_pick_id="parent-1", limit=10),
        )
        assert response.ok is False
        assert response.error is not None
        assert "parent_stale" in response.error
        tg.cancel_scope.cancel()


@pytest.mark.anyio
async def test_pick_by_selector_unknown_parent_returns_error(socket_path: Path) -> None:
    sm = StateManager(session_id="test-session")
    fake = FakePageController()

    async with anyio.create_task_group() as tg:
        tg.start_soon(run_socket_server, sm, socket_path, fake)
        await _wait_for_socket(socket_path)

        response = await query(
            socket_path,
            PickBySelectorRequest(selector=".x", comment="x", parent_pick_id="ghost-pick", limit=10),
        )
        assert response.ok is False
        assert response.error is not None
        assert "parent_not_found" in response.error
        tg.cancel_scope.cancel()


@pytest.mark.anyio
async def test_pick_by_text_dispatch(socket_path: Path) -> None:
    sm = StateManager(session_id="test-session")
    fake = FakePageController()
    fake.selector_matches["__text_role__:OK|button"] = [_el_data("button.ok")]

    async with anyio.create_task_group() as tg:
        tg.start_soon(run_socket_server, sm, socket_path, fake)
        await _wait_for_socket(socket_path)

        response = await query(
            socket_path,
            PickByTextRequest(text="OK", role="button", comment="ok-btn", limit=10),
        )
        assert response.ok is True
        assert response.data["captured"] == 1
        tg.cancel_scope.cancel()


# ---------------------------------------------------------------------------
# Element-reader routes
# ---------------------------------------------------------------------------


@pytest.mark.anyio
async def test_get_text_dispatch_reaches_page_controller(socket_path: Path) -> None:
    sm = StateManager(session_id="test-session")
    await sm.add_pick(_make_pick("known-pick"))
    fake = FakePageController()

    async with anyio.create_task_group() as tg:
        tg.start_soon(run_socket_server, sm, socket_path, fake)
        await _wait_for_socket(socket_path)

        response = await query(socket_path, GetTextRequest(pick_ids=["known-pick"]))
        assert response.ok is True
        assert isinstance(response.data, list)
        assert len(response.data) == 1
        assert response.data[0]["pick_id"] == "known-pick"
        tg.cancel_scope.cancel()


@pytest.mark.anyio
async def test_get_text_unknown_pick_id_returns_not_found(socket_path: Path) -> None:
    sm = StateManager(session_id="test-session")
    fake = FakePageController()

    async with anyio.create_task_group() as tg:
        tg.start_soon(run_socket_server, sm, socket_path, fake)
        await _wait_for_socket(socket_path)

        response = await query(socket_path, GetTextRequest(pick_ids=["ghost"]))
        assert response.ok is True
        assert isinstance(response.data, list)
        assert len(response.data) == 1
        assert response.data[0] == {"error": "pick_not_found", "pick_id": "ghost"}
        tg.cancel_scope.cancel()


@pytest.mark.anyio
async def test_get_html_dispatch_with_max_chars(socket_path: Path) -> None:
    sm = StateManager(session_id="test-session")
    await sm.add_pick(_make_pick("p1"))
    fake = FakePageController()

    async with anyio.create_task_group() as tg:
        tg.start_soon(run_socket_server, sm, socket_path, fake)
        await _wait_for_socket(socket_path)

        response = await query(socket_path, GetHtmlRequest(pick_ids=["p1"], max_chars=200))
        assert response.ok is True
        assert isinstance(response.data, list)
        assert len(response.data) == 1
        assert "html" in response.data[0]
        tg.cancel_scope.cancel()


@pytest.mark.anyio
async def test_get_attributes_dispatch(socket_path: Path) -> None:
    sm = StateManager(session_id="test-session")
    await sm.add_pick(_make_pick("p1"))
    fake = FakePageController()

    async with anyio.create_task_group() as tg:
        tg.start_soon(run_socket_server, sm, socket_path, fake)
        await _wait_for_socket(socket_path)

        response = await query(socket_path, GetAttributesRequest(pick_ids=["p1"]))
        assert response.ok is True
        assert isinstance(response.data, list)
        assert "attributes" in response.data[0]
        tg.cancel_scope.cancel()


@pytest.mark.anyio
async def test_get_state_dispatch(socket_path: Path) -> None:
    sm = StateManager(session_id="test-session")
    await sm.add_pick(_make_pick("p1"))
    fake = FakePageController()

    async with anyio.create_task_group() as tg:
        tg.start_soon(run_socket_server, sm, socket_path, fake)
        await _wait_for_socket(socket_path)

        response = await query(socket_path, GetStateRequest(pick_ids=["p1"]))
        assert response.ok is True
        assert isinstance(response.data, list)
        assert "visible" in response.data[0]
        tg.cancel_scope.cancel()


@pytest.mark.anyio
async def test_get_outline_dispatch(socket_path: Path) -> None:
    sm = StateManager(session_id="test-session")
    await sm.add_pick(_make_pick("p1"))
    fake = FakePageController()

    async with anyio.create_task_group() as tg:
        tg.start_soon(run_socket_server, sm, socket_path, fake)
        await _wait_for_socket(socket_path)

        response = await query(socket_path, GetOutlineRequest(pick_ids=["p1"]))
        assert response.ok is True
        assert isinstance(response.data, list)
        assert "outline" in response.data[0]
        tg.cancel_scope.cancel()


@pytest.mark.anyio
async def test_screenshot_element_dispatch(socket_path: Path) -> None:
    sm = StateManager(session_id="test-session")
    await sm.add_pick(_make_pick("p1"))
    fake = FakePageController()

    async with anyio.create_task_group() as tg:
        tg.start_soon(run_socket_server, sm, socket_path, fake)
        await _wait_for_socket(socket_path)

        response = await query(socket_path, ScreenshotElementRequest(pick_ids=["p1"]))
        assert response.ok is True
        assert isinstance(response.data, list)
        assert "image_base64" in response.data[0]
        tg.cancel_scope.cancel()


# ---------------------------------------------------------------------------
# Page-level routes
# ---------------------------------------------------------------------------


@pytest.mark.anyio
async def test_get_page_info_dispatch(socket_path: Path) -> None:
    sm = StateManager(session_id="test-session")
    fake = FakePageController()

    async with anyio.create_task_group() as tg:
        tg.start_soon(run_socket_server, sm, socket_path, fake)
        await _wait_for_socket(socket_path)

        response = await query(socket_path, GetPageInfoRequest())
        assert response.ok is True
        assert "url" in response.data
        assert "title" in response.data
        tg.cancel_scope.cancel()


@pytest.mark.anyio
async def test_screenshot_page_dispatch(socket_path: Path) -> None:
    sm = StateManager(session_id="test-session")
    fake = FakePageController()

    async with anyio.create_task_group() as tg:
        tg.start_soon(run_socket_server, sm, socket_path, fake)
        await _wait_for_socket(socket_path)

        response = await query(socket_path, ScreenshotPageRequest(full_page=False))
        assert response.ok is True
        assert response.data["format"] == "png"
        tg.cancel_scope.cancel()


@pytest.mark.anyio
async def test_scroll_to_dispatch(socket_path: Path) -> None:
    sm = StateManager(session_id="test-session")
    await sm.add_pick(_make_pick("known-pick"))
    fake = FakePageController()

    async with anyio.create_task_group() as tg:
        tg.start_soon(run_socket_server, sm, socket_path, fake)
        await _wait_for_socket(socket_path)

        response = await query(socket_path, ScrollToRequest(pick_id="known-pick"))
        assert response.ok is True
        assert "is_in_viewport" in response.data
        tg.cancel_scope.cancel()


@pytest.mark.anyio
async def test_scroll_to_unknown_pick_returns_error(socket_path: Path) -> None:
    sm = StateManager(session_id="test-session")
    fake = FakePageController()

    async with anyio.create_task_group() as tg:
        tg.start_soon(run_socket_server, sm, socket_path, fake)
        await _wait_for_socket(socket_path)

        response = await query(socket_path, ScrollToRequest(pick_id="ghost"))
        assert response.ok is False
        assert response.error is not None
        assert "pick_not_found" in response.error
        tg.cancel_scope.cancel()
