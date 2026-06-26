"""IPC protocol + socket-server dispatch tests for recording read-side (IPC 0.7.0).

Covers:
- GetRecordingsRequest round-trip (protocol-level)
- GetRecordingRequest validates recording_id is non-empty
- IpcRequest discriminated union routes both new kinds correctly
- Existing IpcRequest variants still route correctly (regression)
- GetRecordingsRequest dispatch → list_recordings_meta()
- GetRecordingRequest(known_id) → full Recording JSON
- GetRecordingRequest(unknown_id) → {ok: false, error: "recording not found: <id>"}
"""

from __future__ import annotations

import stat as _stat
from pathlib import Path

import anyio
import pytest
from pydantic import TypeAdapter, ValidationError

from frontprompt.ipc import query, run_socket_server
from frontprompt.ipc.protocol import (
    IPC_SCHEMA_VERSION,
    GetRecordingRequest,
    GetRecordingsRequest,
    IpcRequest,
    PingRequest,
)
from frontprompt.state import StateManager
from tests.ipc.fakes import FakePageAnalyzer, FakePageController


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


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


def test_get_recordings_request_roundtrip() -> None:
    """GetRecordingsRequest round-trips with only kind + schema_version."""
    req = GetRecordingsRequest()
    assert req.kind == "get_recordings"
    data = req.model_dump()
    assert data["kind"] == "get_recordings"
    assert data["schema_version"] == IPC_SCHEMA_VERSION


def test_get_recording_request_requires_recording_id() -> None:
    """GetRecordingRequest requires a non-empty recording_id."""
    req = GetRecordingRequest(recording_id="abc-123")
    assert req.recording_id == "abc-123"
    assert req.kind == "get_recording"
    # empty string should fail validation
    with pytest.raises(ValidationError):
        GetRecordingRequest(recording_id="")


def test_get_recordings_routes_via_union_discriminator() -> None:
    """IpcRequest discriminated union resolves get_recordings correctly."""
    adapter: TypeAdapter[IpcRequest] = TypeAdapter(IpcRequest)
    parsed = adapter.validate_python({"kind": "get_recordings"})
    assert isinstance(parsed, GetRecordingsRequest)


def test_get_recording_routes_via_union_discriminator() -> None:
    """IpcRequest discriminated union resolves get_recording correctly."""
    adapter: TypeAdapter[IpcRequest] = TypeAdapter(IpcRequest)
    parsed = adapter.validate_python({"kind": "get_recording", "recording_id": "r1"})
    assert isinstance(parsed, GetRecordingRequest)
    assert parsed.recording_id == "r1"


def test_existing_ping_still_routes_correctly() -> None:
    """Regression: existing IpcRequest variants still route after union extension."""
    adapter: TypeAdapter[IpcRequest] = TypeAdapter(IpcRequest)
    parsed = adapter.validate_python({"kind": "ping"})
    assert isinstance(parsed, PingRequest)


def test_schema_version_is_0_7_0() -> None:
    """IPC_SCHEMA_VERSION is bumped to 0.7.0."""
    assert IPC_SCHEMA_VERSION == "0.7.0"


# ---------------------------------------------------------------------------
# Socket dispatch tests
# ---------------------------------------------------------------------------


@pytest.mark.anyio
async def test_get_recordings_dispatch_returns_meta_list(socket_path: Path) -> None:
    """GetRecordingsRequest → list of RecordingMeta dicts from StateManager."""
    sm = StateManager(session_id="test-session")
    await sm.start_recording(name="Test Rec", description="desc")

    fake_controller = FakePageController()
    fake_analyzer = FakePageAnalyzer()

    async with anyio.create_task_group() as tg:
        tg.start_soon(run_socket_server, sm, socket_path, fake_controller, None, fake_analyzer)
        await _wait_for_socket(socket_path)

        response = await query(socket_path, GetRecordingsRequest())
        assert response.ok is True
        data = response.data
        assert isinstance(data, list)
        assert len(data) == 1
        assert data[0]["name"] == "Test Rec"
        assert data[0]["description"] == "desc"
        assert data[0]["status"] == "active"

        tg.cancel_scope.cancel()


@pytest.mark.anyio
async def test_get_recordings_dispatch_empty_state(socket_path: Path) -> None:
    """GetRecordingsRequest → empty list when no recordings exist."""
    sm = StateManager(session_id="test-session")
    fake_controller = FakePageController()
    fake_analyzer = FakePageAnalyzer()

    async with anyio.create_task_group() as tg:
        tg.start_soon(run_socket_server, sm, socket_path, fake_controller, None, fake_analyzer)
        await _wait_for_socket(socket_path)

        response = await query(socket_path, GetRecordingsRequest())
        assert response.ok is True
        assert response.data == []

        tg.cancel_scope.cancel()


@pytest.mark.anyio
async def test_get_recording_dispatch_known_id(socket_path: Path) -> None:
    """GetRecordingRequest(known_id) → full Recording with entries."""
    sm = StateManager(session_id="test-session")
    await sm.start_recording(name="Full Rec", description="")

    # Capture the recording_id from state
    metas = sm.list_recordings_meta()
    assert len(metas) == 1
    recording_id = metas[0].recording_id

    fake_controller = FakePageController()
    fake_analyzer = FakePageAnalyzer()

    async with anyio.create_task_group() as tg:
        tg.start_soon(run_socket_server, sm, socket_path, fake_controller, None, fake_analyzer)
        await _wait_for_socket(socket_path)

        response = await query(socket_path, GetRecordingRequest(recording_id=recording_id))
        assert response.ok is True
        data = response.data
        assert isinstance(data, dict)
        assert data["recording_id"] == recording_id
        assert data["name"] == "Full Rec"
        assert "entries" in data

        tg.cancel_scope.cancel()


@pytest.mark.anyio
async def test_get_recording_dispatch_unknown_id(socket_path: Path) -> None:
    """GetRecordingRequest(unknown_id) → ok=false, error message contains id."""
    sm = StateManager(session_id="test-session")
    fake_controller = FakePageController()
    fake_analyzer = FakePageAnalyzer()

    async with anyio.create_task_group() as tg:
        tg.start_soon(run_socket_server, sm, socket_path, fake_controller, None, fake_analyzer)
        await _wait_for_socket(socket_path)

        response = await query(socket_path, GetRecordingRequest(recording_id="nonexistent-id"))
        assert response.ok is False
        assert response.error is not None
        assert "nonexistent-id" in response.error
        assert "recording not found" in response.error

        tg.cancel_scope.cancel()
