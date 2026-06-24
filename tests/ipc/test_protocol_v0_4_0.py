"""Pydantic-validation tests for IPC Schema 0.4.0 (14 new Request classes)."""

from __future__ import annotations

import pytest
from pydantic import ValidationError

from frontprompt.ipc.protocol import (
    IPC_SCHEMA_VERSION,
    DomPatchRequest,
    EvalJsRequest,
    FindOneRequest,
    FindSimilarRequest,
    GetPageOutlineRequest,
)


def test_schema_version_is_at_least_0_4_0() -> None:
    # 0.4.0 introduced these 14 request classes; the version moves forward
    # additively (0.5.0 added get_state_summary). The exact pin lives in the
    # version-specific test file for the latest bump.
    assert IPC_SCHEMA_VERSION >= "0.4.0"


def test_get_page_outline_defaults() -> None:
    r = GetPageOutlineRequest()
    assert r.include_headings is True
    assert r.include_links is True
    assert r.max_items_per_kind == 50


def test_get_page_outline_max_items_lower_bound() -> None:
    with pytest.raises(ValidationError):
        GetPageOutlineRequest(max_items_per_kind=0)


def test_get_page_outline_max_items_upper_bound() -> None:
    with pytest.raises(ValidationError):
        GetPageOutlineRequest(max_items_per_kind=201)


def test_find_one_with_find_by_text() -> None:
    r = FindOneRequest(
        query={"kind": "text", "text": "Submit"},
        comment="submit button",
    )
    assert r.kind == "find_one"
    assert r.query.kind == "text"  # type: ignore[union-attr]


def test_find_one_with_find_by_css() -> None:
    r = FindOneRequest(
        query={"kind": "css", "selector": ".btn"},
        comment="main button",
    )
    assert r.query.kind == "css"  # type: ignore[union-attr]


def test_find_one_rejects_unknown_query_kind() -> None:
    with pytest.raises(ValidationError):
        FindOneRequest(query={"kind": "unknown", "text": "x"}, comment="x")


def test_find_similar_threshold_bounds() -> None:
    with pytest.raises(ValidationError):
        FindSimilarRequest(anchor_pick_id="p1", threshold=-0.1, comment="x")
    with pytest.raises(ValidationError):
        FindSimilarRequest(anchor_pick_id="p1", threshold=1.1, comment="x")


def test_find_similar_max_results_bounds() -> None:
    with pytest.raises(ValidationError):
        FindSimilarRequest(anchor_pick_id="p1", max_results=0, comment="x")
    with pytest.raises(ValidationError):
        FindSimilarRequest(anchor_pick_id="p1", max_results=201, comment="x")


def test_eval_js_defaults() -> None:
    r = EvalJsRequest(expression="1+1")
    assert r.mutating is False
    assert r.pick_id_arg is None


def test_eval_js_rejects_empty_expression() -> None:
    with pytest.raises(ValidationError):
        EvalJsRequest(expression="")


def test_dom_patch_set_attribute() -> None:
    r = DomPatchRequest(
        pick_id="p1",
        operations=[{"op": "set_attribute", "name": "data-x", "value": "1"}],
    )
    assert r.operations[0].op == "set_attribute"  # type: ignore[union-attr]


def test_dom_patch_remove_element() -> None:
    r = DomPatchRequest(
        pick_id="p1",
        operations=[{"op": "remove_element"}],
    )
    assert r.operations[0].op == "remove_element"  # type: ignore[union-attr]


def test_dom_patch_rejects_unknown_op() -> None:
    with pytest.raises(ValidationError):
        DomPatchRequest(pick_id="p1", operations=[{"op": "zap"}])


def test_dom_patch_rejects_empty_operations() -> None:
    with pytest.raises(ValidationError):
        DomPatchRequest(pick_id="p1", operations=[])


def test_ipc_request_discriminates_get_page_outline() -> None:
    from pydantic import TypeAdapter

    from frontprompt.ipc.protocol import IpcRequest

    ta = TypeAdapter(IpcRequest)
    r = ta.validate_python({"kind": "get_page_outline"})
    assert isinstance(r, GetPageOutlineRequest)


def test_ipc_request_discriminates_find_one() -> None:
    from pydantic import TypeAdapter

    from frontprompt.ipc.protocol import IpcRequest

    ta = TypeAdapter(IpcRequest)
    r = ta.validate_python({"kind": "find_one", "query": {"kind": "text", "text": "foo"}, "comment": "test"})
    assert isinstance(r, FindOneRequest)


def test_ipc_request_discriminates_eval_js() -> None:
    from pydantic import TypeAdapter

    from frontprompt.ipc.protocol import IpcRequest

    ta = TypeAdapter(IpcRequest)
    r = ta.validate_python({"kind": "eval_js", "expression": "1+1"})
    assert isinstance(r, EvalJsRequest)


def test_ipc_request_discriminates_dom_patch() -> None:
    from pydantic import TypeAdapter

    from frontprompt.ipc.protocol import IpcRequest

    ta = TypeAdapter(IpcRequest)
    r = ta.validate_python({"kind": "dom_patch", "pick_id": "p1", "operations": [{"op": "remove_element"}]})
    assert isinstance(r, DomPatchRequest)
