"""Pydantic-validation tests for IPC Schema 0.5.0 — get_state_summary."""

from __future__ import annotations

import pytest
from pydantic import TypeAdapter, ValidationError

from frontprompt.ipc.protocol import (
    IPC_SCHEMA_VERSION,
    GetStateSummaryRequest,
    IpcRequest,
)


def test_schema_version_is_at_least_0_5_0() -> None:
    # Version was 0.5.0 when get_state_summary landed; bumped to 0.6.0 by get_comments.
    from packaging.version import Version

    assert Version(IPC_SCHEMA_VERSION) >= Version("0.5.0")


def test_get_state_summary_defaults() -> None:
    r = GetStateSummaryRequest()
    assert r.kind == "get_state_summary"
    assert r.schema_version == IPC_SCHEMA_VERSION


def test_get_state_summary_forbids_extra_fields() -> None:
    with pytest.raises(ValidationError):
        GetStateSummaryRequest(unexpected="x")  # type: ignore[call-arg]


def test_get_state_summary_dispatches_via_union_discriminator() -> None:
    adapter: TypeAdapter[IpcRequest] = TypeAdapter(IpcRequest)
    parsed = adapter.validate_python({"kind": "get_state_summary"})
    assert isinstance(parsed, GetStateSummaryRequest)
