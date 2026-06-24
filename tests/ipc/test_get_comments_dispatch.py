"""IPC socket-server dispatch tests for GetCommentsRequest (IPC 0.6.0).

Tests the get_comments dispatch route. Uses StateManager with real picks.
No Playwright required.
"""

from __future__ import annotations

import stat as _stat
from pathlib import Path

import anyio
import pytest
from pydantic import TypeAdapter

from frontprompt.ipc import (
    query,
    run_socket_server,
)
from frontprompt.ipc.protocol import (
    IPC_SCHEMA_VERSION,
    AnnotationEntry,
    GetCommentsRequest,
    IpcRequest,
)
from frontprompt.state import StateManager
from frontprompt.state.state import (
    ElementFingerprint,
    ElementRect,
    Pick,
    PickElement,
)
from tests.ipc.fakes import FakePageAnalyzer, FakePageController

# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


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
# Protocol-level unit tests
# ---------------------------------------------------------------------------


def test_get_comments_request_roundtrip() -> None:
    """GetCommentsRequest round-trips through Pydantic (kind discriminator)."""
    req = GetCommentsRequest()
    assert req.kind == "get_comments"
    data = req.model_dump()
    assert data["kind"] == "get_comments"


def test_get_comments_request_schema_version() -> None:
    req = GetCommentsRequest()
    assert req.schema_version == IPC_SCHEMA_VERSION


def test_get_comments_dispatches_via_union_discriminator() -> None:
    adapter: TypeAdapter[IpcRequest] = TypeAdapter(IpcRequest)
    parsed = adapter.validate_python({"kind": "get_comments"})
    assert isinstance(parsed, GetCommentsRequest)


def test_annotation_entry_model() -> None:
    """AnnotationEntry has pick_id, comment, selector, url fields."""
    entry = AnnotationEntry(
        pick_id="p1",
        comment="my note",
        selector="#btn",
        url="https://example.com/",
    )
    assert entry.pick_id == "p1"
    assert entry.comment == "my note"
    assert entry.selector == "#btn"
    assert entry.url == "https://example.com/"


def test_annotation_entry_roundtrip() -> None:
    entry = AnnotationEntry(pick_id="p2", comment="note", selector=".x", url="https://a.com/")
    data = entry.model_dump()
    assert data["pick_id"] == "p2"
    assert data["comment"] == "note"
    assert data["selector"] == ".x"
    assert data["url"] == "https://a.com/"


# ---------------------------------------------------------------------------
# Socket dispatch tests
# ---------------------------------------------------------------------------


@pytest.mark.anyio
async def test_get_comments_dispatch_returns_annotated_picks(socket_path: Path) -> None:
    """get_comments returns only picks with non-empty comments."""
    sm = StateManager(session_id="test-session")
    # Add two picks: one with a comment, one without
    pick_with_comment = _make_pick("p1", comment="my annotation")
    pick_no_comment = _make_pick("p2", comment="")
    await sm.add_pick(pick_with_comment)
    await sm.add_pick(pick_no_comment)

    fake_controller = FakePageController()
    fake_analyzer = FakePageAnalyzer()

    async with anyio.create_task_group() as tg:
        tg.start_soon(run_socket_server, sm, socket_path, fake_controller, None, fake_analyzer)
        await _wait_for_socket(socket_path)

        response = await query(socket_path, GetCommentsRequest())
        assert response.ok is True
        data = response.data
        assert isinstance(data, list)

        # Only p1 (with comment) should be returned
        pick_ids = [e["pick_id"] for e in data]
        assert "p1" in pick_ids
        assert "p2" not in pick_ids

        # Verify the AnnotationEntry shape
        entry = next(e for e in data if e["pick_id"] == "p1")
        assert entry["comment"] == "my annotation"
        assert entry["selector"] == "#p1"
        assert entry["url"] == "https://example.com/"

        tg.cancel_scope.cancel()


@pytest.mark.anyio
async def test_get_comments_dispatch_empty_state(socket_path: Path) -> None:
    """get_comments returns empty list when no picks have comments."""
    sm = StateManager(session_id="test-session")
    await sm.add_pick(_make_pick("p1", comment=""))
    await sm.add_pick(_make_pick("p2", comment=""))

    fake_controller = FakePageController()
    fake_analyzer = FakePageAnalyzer()

    async with anyio.create_task_group() as tg:
        tg.start_soon(run_socket_server, sm, socket_path, fake_controller, None, fake_analyzer)
        await _wait_for_socket(socket_path)

        response = await query(socket_path, GetCommentsRequest())
        assert response.ok is True
        assert response.data == []

        tg.cancel_scope.cancel()


@pytest.mark.anyio
async def test_get_comments_dispatch_no_picks(socket_path: Path) -> None:
    """get_comments returns empty list when there are no picks at all."""
    sm = StateManager(session_id="test-session")

    fake_controller = FakePageController()
    fake_analyzer = FakePageAnalyzer()

    async with anyio.create_task_group() as tg:
        tg.start_soon(run_socket_server, sm, socket_path, fake_controller, None, fake_analyzer)
        await _wait_for_socket(socket_path)

        response = await query(socket_path, GetCommentsRequest())
        assert response.ok is True
        assert response.data == []

        tg.cancel_scope.cancel()
