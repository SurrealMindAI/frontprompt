"""Pydantic-protocol roundtrip tests."""

from __future__ import annotations

import pytest
from pydantic import TypeAdapter, ValidationError

from frontprompt.ipc import (
    GetPickRequest,
    GetPicksRequest,
    GetSnapshotRequest,
    IpcRequest,
    IpcResponse,
    NavigateRequest,
    PingRequest,
)

_REQ = TypeAdapter(IpcRequest)


def test_schema_version_is_0_3_0() -> None:
    # Version assertion moved to tests/ipc/test_protocol_v0_4_0.py
    pass


def test_ping_routes_via_discriminator() -> None:
    msg = _REQ.validate_python({"kind": "ping", "schema_version": "0.3.0"})
    assert isinstance(msg, PingRequest)


def test_get_snapshot_routes() -> None:
    msg = _REQ.validate_python({"kind": "get_snapshot", "schema_version": "0.3.0"})
    assert isinstance(msg, GetSnapshotRequest)


def test_get_picks_routes() -> None:
    msg = _REQ.validate_python({"kind": "get_picks", "schema_version": "0.3.0"})
    assert isinstance(msg, GetPicksRequest)


def test_get_pick_routes_with_id() -> None:
    msg = _REQ.validate_python({"kind": "get_pick", "schema_version": "0.3.0", "pick_id": "abc"})
    assert isinstance(msg, GetPickRequest)
    assert msg.pick_id == "abc"


def test_get_pick_rejects_missing_id() -> None:
    with pytest.raises(ValidationError):
        _REQ.validate_python({"kind": "get_pick", "schema_version": "0.3.0"})


def test_navigate_routes_with_url() -> None:
    msg = _REQ.validate_python({"kind": "navigate", "schema_version": "0.3.0", "url": "https://example.com"})
    assert isinstance(msg, NavigateRequest)
    assert msg.url == "https://example.com"


def test_navigate_rejects_missing_url() -> None:
    with pytest.raises(ValidationError):
        _REQ.validate_python({"kind": "navigate", "schema_version": "0.3.0"})


def test_navigate_rejects_empty_url() -> None:
    with pytest.raises(ValidationError):
        _REQ.validate_python({"kind": "navigate", "schema_version": "0.3.0", "url": ""})


def test_unknown_kind_rejected() -> None:
    with pytest.raises(ValidationError):
        _REQ.validate_python({"kind": "unknown_op", "schema_version": "0.3.0"})


def test_extra_field_rejected_in_request() -> None:
    """extra='forbid' verhindert silent typos."""
    with pytest.raises(ValidationError):
        _REQ.validate_python({"kind": "ping", "schema_version": "0.3.0", "extra_typo": True})


def test_response_ok_with_data() -> None:
    r = IpcResponse(ok=True, data={"x": 1})
    assert r.ok is True
    assert r.data == {"x": 1}
    assert r.error is None


def test_response_error() -> None:
    r = IpcResponse(ok=False, error="boom")
    assert r.ok is False
    assert r.error == "boom"
    assert r.data is None


def test_response_roundtrips_json() -> None:
    r = IpcResponse(ok=True, data={"picks": []})
    restored = IpcResponse.model_validate_json(r.model_dump_json())
    assert restored == r
