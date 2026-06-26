"""MCP tool surface tests for v0.4.0 refinement tools.

Pure unit tests — no socket, no browser. Calls _build_tool_list() and
_build_ipc_request() directly to verify the 14 new tools + 5 deprecation warnings.
"""

from __future__ import annotations

import pytest

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
from frontprompt.mcp_server import _build_ipc_request, _build_tool_list

_ALL_NEW_TOOL_NAMES = [
    "frontprompt_get_page_outline",
    "frontprompt_get_page_html",
    "frontprompt_pick_from_ref",
    "frontprompt_find_one",
    "frontprompt_find_first",
    "frontprompt_find_similar",
    "frontprompt_find_by_regex",
    "frontprompt_get_element_context",
    "frontprompt_pick_path",
    "frontprompt_relocate_picks",
    "frontprompt_inspect_elements",
    "frontprompt_eval_js",
    "frontprompt_dom_patch",
    "frontprompt_pick_by_xpath",
]

_DEPRECATED_TOOL_NAMES: list[str] = []

_REMOVED_TOOL_NAMES = [
    "frontprompt_get_text",
    "frontprompt_get_attributes",
    "frontprompt_get_state",
    "frontprompt_get_html",
    "frontprompt_get_outline",
]


def test_tool_list_has_31_tools() -> None:
    # 31 = 29 (v0.6.0 after deprecated removal) + 2 recording tools (v0.7.0).
    # Breakdown: 1 diagnostic + 7 read-only (v0.1+0.2+0.6) + 6 scout v0.3.0
    # (pick_by_selector, pick_by_text, screenshot_element, get_page_info,
    #  screenshot_page, scroll_to) + 14 refinement v0.4.0 + 1 state-summary v0.5.0
    # + 2 recording v0.7.0 (list_recordings, get_recording).
    tools = _build_tool_list()
    assert len(tools) == 31
    names = {t.name for t in tools}
    assert "fp_status" in names
    assert "frontprompt_get_state_summary" in names
    assert "frontprompt_get_comments" in names


def test_tool_list_contains_all_14_new_names() -> None:
    tools = _build_tool_list()
    names = {t.name for t in tools}
    missing = [n for n in _ALL_NEW_TOOL_NAMES if n not in names]
    assert not missing, f"Missing new tools: {missing}"


@pytest.mark.parametrize(
    "name",
    [
        "frontprompt_get_text",
        "frontprompt_get_html",
        "frontprompt_get_attributes",
        "frontprompt_get_state",
        "frontprompt_get_outline",
    ],
)
def test_deprecated_tool_absent_from_list(name: str) -> None:
    names = {t.name for t in _build_tool_list()}
    assert name not in names, f"Deprecated tool {name!r} still present in tool list"


@pytest.mark.parametrize(
    "name",
    [
        "frontprompt_get_text",
        "frontprompt_get_html",
        "frontprompt_get_attributes",
        "frontprompt_get_state",
        "frontprompt_get_outline",
    ],
)
def test_build_ipc_request_raises_for_removed_tools(name: str) -> None:
    with pytest.raises(ValueError, match="unknown tool"):
        _build_ipc_request(name, {"pick_ids": ["abc"]})


def test_get_page_outline_dispatch() -> None:
    req = _build_ipc_request("frontprompt_get_page_outline", {})
    assert isinstance(req, GetPageOutlineRequest)
    assert req.include_headings is True
    assert req.include_links is True
    assert req.max_items_per_kind == 50


def test_get_page_html_dispatch() -> None:
    req = _build_ipc_request("frontprompt_get_page_html", {})
    assert isinstance(req, GetPageHtmlRequest)
    assert req.strip_scripts is True
    assert req.max_chars == 50000


def test_pick_from_ref_dispatch() -> None:
    req = _build_ipc_request(
        "frontprompt_pick_from_ref",
        {"ref_id": "ref:link:abc", "snapshot_id": "snap-1", "comment": "test"},
    )
    assert isinstance(req, PickFromRefRequest)
    assert req.ref_id == "ref:link:abc"


def test_find_one_dispatch() -> None:
    req = _build_ipc_request(
        "frontprompt_find_one",
        {"query": {"kind": "text", "text": "Submit"}, "comment": "btn"},
    )
    assert isinstance(req, FindOneRequest)
    assert req.comment == "btn"


def test_find_first_dispatch() -> None:
    req = _build_ipc_request(
        "frontprompt_find_first",
        {"query": {"kind": "css", "selector": "div.item"}, "comment": "first"},
    )
    assert isinstance(req, FindFirstRequest)


def test_find_similar_dispatch() -> None:
    req = _build_ipc_request(
        "frontprompt_find_similar",
        {"anchor_pick_id": "p1", "comment": "similar"},
    )
    assert isinstance(req, FindSimilarRequest)
    assert req.threshold == 0.7
    assert req.max_results == 50


def test_find_by_regex_dispatch() -> None:
    req = _build_ipc_request(
        "frontprompt_find_by_regex",
        {"pattern": "Alpha|Beta", "comment": "greek"},
    )
    assert isinstance(req, FindByRegexRequest)
    assert req.field == "text"
    assert req.limit == 10


def test_get_element_context_dispatch() -> None:
    req = _build_ipc_request(
        "frontprompt_get_element_context",
        {"pick_id": "p1"},
    )
    assert isinstance(req, GetElementContextRequest)
    assert req.levels_up == 2
    assert req.sibling_radius == 2


def test_pick_path_dispatch() -> None:
    req = _build_ipc_request("frontprompt_pick_path", {"pick_id": "p1"})
    assert isinstance(req, PickPathRequest)
    assert req.pick_id == "p1"


def test_relocate_picks_dispatch_no_pick_ids() -> None:
    req = _build_ipc_request("frontprompt_relocate_picks", {})
    assert isinstance(req, RelocatePicksRequest)
    assert req.pick_ids is None


def test_inspect_elements_dispatch() -> None:
    req = _build_ipc_request(
        "frontprompt_inspect_elements",
        {"pick_ids": ["p1", "p2"]},
    )
    assert isinstance(req, InspectElementsRequest)
    assert req.pick_ids == ["p1", "p2"]
    assert req.fields == ["text", "role", "visible", "enabled"]


def test_eval_js_dispatch_defaults() -> None:
    req = _build_ipc_request("frontprompt_eval_js", {"expression": "1+1"})
    assert isinstance(req, EvalJsRequest)
    assert req.mutating is False
    assert req.pick_id_arg is None


def test_dom_patch_dispatch() -> None:
    req = _build_ipc_request(
        "frontprompt_dom_patch",
        {
            "pick_id": "p1",
            "operations": [{"op": "set_attribute", "name": "data-x", "value": "1"}],
        },
    )
    assert isinstance(req, DomPatchRequest)
    assert req.pick_id == "p1"


def test_pick_by_xpath_dispatch() -> None:
    req = _build_ipc_request(
        "frontprompt_pick_by_xpath",
        {"xpath": "//div[@class='item']", "comment": "xpath items"},
    )
    assert isinstance(req, PickByXpathRequest)
    assert req.xpath == "//div[@class='item']"
    assert req.limit == 10


def test_unknown_tool_raises() -> None:
    with pytest.raises(ValueError):
        _build_ipc_request("frontprompt_does_not_exist", {})


def test_each_new_tool_has_additional_properties_false() -> None:
    tools = _build_tool_list()
    new_tools = [t for t in tools if t.name in _ALL_NEW_TOOL_NAMES]
    assert len(new_tools) == 14
    for tool in new_tools:
        schema = tool.inputSchema
        assert schema.get("additionalProperties") is False, f"tool {tool.name!r} missing additionalProperties: false"


def _desc_of(name: str) -> str:
    tools = _build_tool_list()
    name_to_desc = {t.name: t.description for t in tools}
    assert name in name_to_desc, f"tool {name!r} not in tool list"
    return name_to_desc[name] or ""


def test_find_similar_description_drops_scores_claim() -> None:
    desc = _desc_of("frontprompt_find_similar")
    assert "scores: list[float]" not in desc, f"find_similar description still claims scores list: {desc!r}"
    assert "threshold" in desc.lower(), f"find_similar description should mention threshold semantics: {desc!r}"


def test_pick_from_ref_description_has_lifecycle_hints() -> None:
    desc = _desc_of("frontprompt_pick_from_ref")
    assert "30" in desc, f"pick_from_ref description should mention 30s TTL: {desc!r}"
    lowered = desc.lower()
    assert "invalidat" in lowered, f"pick_from_ref description should mention invalidation: {desc!r}"


def test_get_page_outline_description_has_lifecycle_hint() -> None:
    desc = _desc_of("frontprompt_get_page_outline")
    lowered = desc.lower()
    has_ttl_hint = "30" in desc or "ttl" in lowered
    has_invalidation_hint = "invalidat" in lowered or "valid until" in lowered
    assert has_ttl_hint and has_invalidation_hint, (
        f"get_page_outline description should mention TTL and invalidation surface: {desc!r}"
    )


def test_get_page_html_description_advertises_hardcoded_cleanup() -> None:
    desc = _desc_of("frontprompt_get_page_html")
    lowered = desc.lower()
    assert "overlay" in lowered, f"get_page_html description should advertise the hardcoded overlay strip: {desc!r}"
    assert "semantic" in lowered or "unwrap" in lowered, (
        f"get_page_html description should mention semantic cleanup behaviour: {desc!r}"
    )


_FIND_PATH_TOOL_NAMES = [
    "frontprompt_find_one",
    "frontprompt_find_first",
    "frontprompt_find_by_regex",
    "frontprompt_find_similar",
    "frontprompt_pick_by_text",
]


def test_find_path_tools_advertise_rect_roundtrip_contract() -> None:
    """Every find-path tool description must document that the resulting Pick
    carries a real viewport rect obtained via a Playwright bounding-box
    roundtrip (rect-roundtrip contract). LLM consumers rely on this to know rect is
    populated for find-* matches, not just for pick_by_xpath / pick_by_selector.
    """
    for name in _FIND_PATH_TOOL_NAMES:
        desc = _desc_of(name).lower()
        has_rect_hint = "viewport" in desc or "bounding" in desc or "rect" in desc
        assert has_rect_hint, f"{name} description should advertise the rect roundtrip: {desc!r}"
