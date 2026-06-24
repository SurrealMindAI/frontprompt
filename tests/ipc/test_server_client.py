"""Socket-server + socket-client integration tests.

End-to-end: spawn server-task auf ephemeral socket, connect via client, assert
response. Echtes Pydantic-Pickeln + echte unix-sockets.

macOS-Gotcha: AF_UNIX-Pfade sind auf 104 bytes gecappt. pytest's default
``tmp_path`` ist zu tief verschachtelt (``/private/var/folders/.../pytest-of-xxx/...``)
und sprengt das Limit. Wir nutzen daher direkten ``/tmp/``-basierten Pfad
über die :func:`short_socket_dir` fixture.
"""

from __future__ import annotations

import shutil
import tempfile
from collections.abc import Iterator
from pathlib import Path

import anyio
import pytest

from frontprompt.ipc import (
    GetPageInfoRequest,
    GetPickRequest,
    GetPicksRequest,
    GetSnapshotRequest,
    GetStateSummaryRequest,
    IpcConnectError,
    NavigateRequest,
    PingRequest,
    query,
    run_socket_server,
)
from frontprompt.ipc.playwright_controller.timeouts import PageOpTimeoutError
from frontprompt.state import StateManager
from frontprompt.state.state import (
    ElementFingerprint,
    ElementRect,
    Pick,
    PickElement,
)


def _make_pick(pick_id: str = "pick-001", comment: str = "") -> Pick:
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


@pytest.fixture
def short_socket_dir() -> Iterator[Path]:
    """Erzeuge tmp-dir in ``/tmp/`` (kurz genug für AF_UNIX-104-byte-limit auf macOS)."""
    d = Path(tempfile.mkdtemp(prefix="fp-test-", dir="/tmp"))
    try:
        yield d
    finally:
        shutil.rmtree(d, ignore_errors=True)


@pytest.fixture
def socket_path(short_socket_dir: Path) -> Path:
    return short_socket_dir / "s.sock"


@pytest.mark.anyio
async def test_ping(socket_path: Path) -> None:
    sm = StateManager(session_id="test-session")
    async with anyio.create_task_group() as tg:
        tg.start_soon(run_socket_server, sm, socket_path)
        await _wait_for_socket(socket_path)

        response = await query(socket_path, PingRequest())
        assert response.ok is True
        assert response.data == {"pong": True}
        tg.cancel_scope.cancel()


@pytest.mark.anyio
async def test_get_snapshot_empty(socket_path: Path) -> None:
    sm = StateManager(session_id="test-session")
    async with anyio.create_task_group() as tg:
        tg.start_soon(run_socket_server, sm, socket_path)
        await _wait_for_socket(socket_path)

        response = await query(socket_path, GetSnapshotRequest())
        assert response.ok is True
        assert response.data is not None
        assert "panel_state" in response.data
        assert "inspector_state" in response.data
        assert response.data["inspector_state"]["picks"] == []
        tg.cancel_scope.cancel()


@pytest.mark.anyio
async def test_get_picks_returns_added_picks(socket_path: Path) -> None:
    sm = StateManager(session_id="test-session")
    await sm.add_pick(_make_pick("a", comment="first"))
    await sm.add_pick(_make_pick("b", comment="second"))

    async with anyio.create_task_group() as tg:
        tg.start_soon(run_socket_server, sm, socket_path)
        await _wait_for_socket(socket_path)

        response = await query(socket_path, GetPicksRequest())
        assert response.ok is True
        assert isinstance(response.data, list)
        assert len(response.data) == 2
        ids = [p["pick_id"] for p in response.data]
        assert ids == ["a", "b"]
        assert response.data[0]["comment"] == "first"
        tg.cancel_scope.cancel()


@pytest.mark.anyio
async def test_get_pick_by_id_returns_one(socket_path: Path) -> None:
    sm = StateManager(session_id="test-session")
    await sm.add_pick(_make_pick("a"))
    await sm.add_pick(_make_pick("b"))

    async with anyio.create_task_group() as tg:
        tg.start_soon(run_socket_server, sm, socket_path)
        await _wait_for_socket(socket_path)

        response = await query(socket_path, GetPickRequest(pick_id="b"))
        assert response.ok is True
        assert response.data is not None
        assert response.data["pick_id"] == "b"
        tg.cancel_scope.cancel()


@pytest.mark.anyio
async def test_get_pick_unknown_id_returns_error(socket_path: Path) -> None:
    sm = StateManager(session_id="test-session")
    async with anyio.create_task_group() as tg:
        tg.start_soon(run_socket_server, sm, socket_path)
        await _wait_for_socket(socket_path)

        response = await query(socket_path, GetPickRequest(pick_id="ghost"))
        assert response.ok is False
        assert response.error is not None
        assert "pick_not_found" in response.error
        tg.cancel_scope.cancel()


@pytest.mark.anyio
async def test_get_state_summary_returns_counts_and_grouping(socket_path: Path) -> None:
    """get_state_summary returns the small navigable overview (counts + grouping),
    not the full snapshot."""
    sm = StateManager(session_id="test-session")
    await sm.add_pick(_make_pick("a"))  # url https://example.com/
    await sm.add_pick(_make_pick("b"))

    async with anyio.create_task_group() as tg:
        tg.start_soon(run_socket_server, sm, socket_path)
        await _wait_for_socket(socket_path)

        response = await query(socket_path, GetStateSummaryRequest())
        assert response.ok is True
        assert response.data is not None
        assert response.data["current_session_id"] == "test-session"
        assert response.data["counts"] == {"picks": 2, "regions": 0, "relations": 0}
        assert response.data["owned_vs_foreign"] == {"owned": 2, "foreign": 0}
        hosts = {h["hostname"]: h["picks"] for h in response.data["by_hostname"]}
        assert hosts == {"example.com": 2}
        sessions = {g["session"]: g["picks"] for g in response.data["by_origin_session"]}
        assert sessions == {"test-session": 2}
        tg.cancel_scope.cancel()


@pytest.mark.anyio
async def test_navigate_without_page_controller_returns_unavailable(socket_path: Path) -> None:
    """Default NullPageController makes navigate ok=False with navigate_unavailable."""
    sm = StateManager(session_id="test-session")
    async with anyio.create_task_group() as tg:
        tg.start_soon(run_socket_server, sm, socket_path)
        await _wait_for_socket(socket_path)

        response = await query(socket_path, NavigateRequest(url="https://example.com"))
        assert response.ok is False
        assert response.error is not None
        assert "navigate_unavailable" in response.error
        tg.cancel_scope.cancel()


@pytest.mark.anyio
async def test_navigate_with_page_controller_dispatches_to_navigate(socket_path: Path) -> None:
    """With a wired PageController, NavigateRequest awaits its navigate() and returns the result."""
    sm = StateManager(session_id="test-session")

    captured_urls: list[str] = []

    class _FakeController:
        async def navigate(self, url: str) -> dict[str, str]:
            captured_urls.append(url)
            return {"navigated_to": url, "title": "Example Domain"}

    async with anyio.create_task_group() as tg:
        tg.start_soon(run_socket_server, sm, socket_path, _FakeController())
        await _wait_for_socket(socket_path)

        response = await query(socket_path, NavigateRequest(url="https://example.com"))
        assert response.ok is True
        assert response.data == {"navigated_to": "https://example.com", "title": "Example Domain"}
        assert captured_urls == ["https://example.com"]
        tg.cancel_scope.cancel()


@pytest.mark.anyio
async def test_navigate_page_controller_raises_propagates_as_error(socket_path: Path) -> None:
    """If the PageController.navigate raises (e.g. playwright timeout), response is ok=False."""
    sm = StateManager(session_id="test-session")

    class _BrokenController:
        async def navigate(self, url: str) -> dict[str, str]:
            raise RuntimeError("net::ERR_NAME_NOT_RESOLVED")

    async with anyio.create_task_group() as tg:
        tg.start_soon(run_socket_server, sm, socket_path, _BrokenController())
        await _wait_for_socket(socket_path)

        response = await query(socket_path, NavigateRequest(url="https://nonexistent.invalid"))
        assert response.ok is False
        assert response.error is not None
        assert "navigate_failed" in response.error
        assert "NAME_NOT_RESOLVED" in response.error
        tg.cancel_scope.cancel()


@pytest.mark.anyio
async def test_get_page_info_timeout_returns_page_op_timeout(socket_path: Path) -> None:
    """A wedged page op (PageOpTimeoutError) is caught by the dispatcher and
    surfaced as ok=False page_op_timeout — the show-side always replies."""
    sm = StateManager(session_id="test-session")

    class _WedgedController:
        async def get_page_info(self) -> dict[str, str]:
            raise PageOpTimeoutError("page_info", 10.0)

    async with anyio.create_task_group() as tg:
        tg.start_soon(run_socket_server, sm, socket_path, _WedgedController())
        await _wait_for_socket(socket_path)

        response = await query(socket_path, GetPageInfoRequest())
        assert response.ok is False
        assert response.error is not None
        assert "page_op_timeout" in response.error
        assert "page_info" in response.error
        tg.cancel_scope.cancel()


@pytest.mark.anyio
async def test_connect_to_nonexistent_socket_raises(short_socket_dir: Path) -> None:
    """Client gibt klare Error-Message wenn kein server läuft."""
    missing = short_socket_dir / "ghost.sock"
    with pytest.raises(IpcConnectError):
        await query(missing, PingRequest())


@pytest.mark.anyio
async def test_query_times_out_when_peer_accepts_but_never_responds(socket_path: Path) -> None:
    """A wedged show-child accepts the connection but never sends a response.

    The daemon-side IPC client must return a clean ipc_timeout response within
    the bound — never hang forever (the symptom that kills the MCP tool call)."""
    socket_path.parent.mkdir(parents=True, exist_ok=True)

    async def _silent_peer(stream: object) -> None:
        # Accept the connection, then never reply — simulate the pinned page thread.
        async with stream:  # type: ignore[attr-defined]
            await anyio.sleep_forever()

    async with anyio.create_task_group() as tg:
        listener = await anyio.create_unix_listener(str(socket_path), mode=0o600)
        tg.start_soon(listener.serve, _silent_peer)
        await _wait_for_socket(socket_path)

        response = await query(socket_path, PingRequest(), timeout=0.1)
        assert response.ok is False
        assert response.error is not None
        assert "ipc_timeout" in response.error

        await listener.aclose()
        tg.cancel_scope.cancel()


@pytest.mark.anyio
async def test_query_logs_structured_timeout_event(socket_path: Path) -> None:
    """On IPC round-trip timeout, a structured mcp.tool.ipc.timeout event is logged."""
    import structlog.testing

    socket_path.parent.mkdir(parents=True, exist_ok=True)

    async def _silent_peer(stream: object) -> None:
        async with stream:  # type: ignore[attr-defined]
            await anyio.sleep_forever()

    async with anyio.create_task_group() as tg:
        listener = await anyio.create_unix_listener(str(socket_path), mode=0o600)
        tg.start_soon(listener.serve, _silent_peer)
        await _wait_for_socket(socket_path)

        with structlog.testing.capture_logs() as logs:
            await query(socket_path, PingRequest(), timeout=0.1)

        timeout_events = [e for e in logs if "ipc.timeout" in str(e.get("event", ""))]
        assert timeout_events, f"expected an ipc.timeout log event, got: {logs}"

        await listener.aclose()
        tg.cancel_scope.cancel()


@pytest.mark.anyio
async def test_server_auto_removes_stale_socket_file(socket_path: Path) -> None:
    """anyio's create_unix_listener removed existing socket — kein 'address in use'."""
    # Lege eine "stale" socket-file an
    socket_path.parent.mkdir(parents=True, exist_ok=True)
    socket_path.touch()

    sm = StateManager(session_id="test-session")
    async with anyio.create_task_group() as tg:
        tg.start_soon(run_socket_server, sm, socket_path)
        await _wait_for_socket(socket_path)

        response = await query(socket_path, PingRequest())
        assert response.ok is True
        tg.cancel_scope.cancel()


# ---------------------------------------------------------------------------
# _read_frame logs debug on EndOfStream
# ---------------------------------------------------------------------------


@pytest.mark.anyio
async def test_read_frame_logs_debug_on_end_of_stream() -> None:
    """_read_frame must emit a debug log event on anyio.EndOfStream."""
    import structlog.testing

    from frontprompt.ipc.socket_server import _read_frame

    class _MockStream:
        async def receive(self, max_bytes: int = 4096) -> bytes:
            raise anyio.EndOfStream

    with structlog.testing.capture_logs() as logs:
        result = await _read_frame(_MockStream())  # type: ignore[arg-type]

    assert result == b""
    debug_events = [e for e in logs if e.get("log_level") == "debug"]
    found = any(
        "end_of_stream" in str(e.get("event", "")) or "connection closed" in str(e.get("event", ""))
        for e in debug_events
    )
    assert found, f"Expected a debug log containing 'end_of_stream' or 'connection closed', got: {logs}"


async def _wait_for_socket(path: Path, attempts: int = 50, delay: float = 0.02) -> None:
    """Poll bis ECHTER unix-socket erscheint — server-task hat startup-latenz.

    Wichtig: check via ``stat.S_ISSOCK``, nicht nur exists() — der
    ``test_server_auto_removes_stale_socket_file`` test legt ein REGULAR
    file an, das server-side erst ersetzt wird. Polling auf exists() würde
    sonst zu früh return-en.
    """
    import stat as _stat

    for _ in range(attempts):
        try:
            mode = path.stat().st_mode
            if _stat.S_ISSOCK(mode):
                return
        except OSError:
            pass
        await anyio.sleep(delay)
    raise RuntimeError(f"unix-socket {path} wurde nicht innerhalb {attempts * delay}s erstellt")
