"""MCP tool surface tests for v0.3.0 scout tools.

Pure unit tests — no socket, no browser. Calls _build_tool_list() and
_build_ipc_request() directly to verify the tool surface is correct.
"""

from __future__ import annotations

import pytest

from frontprompt.ipc.protocol import (
    GetPageInfoRequest,
    PickBySelectorRequest,
    PickByTextRequest,
    ScreenshotElementRequest,
    ScreenshotPageRequest,
    ScrollToRequest,
)
from frontprompt.mcp_server import _build_ipc_request, _build_tool_list

_ALL_NEW_TOOL_NAMES = [
    "frontprompt_pick_by_selector",
    "frontprompt_pick_by_text",
    # get_text, get_html, get_attributes, get_state, get_outline removed in IPC 0.6.0
    "frontprompt_screenshot_element",
    "frontprompt_get_page_info",
    "frontprompt_screenshot_page",
    "frontprompt_scroll_to",
]

_REMOVED_V0_4_0_TOOL_NAMES = [
    "frontprompt_get_text",
    "frontprompt_get_html",
    "frontprompt_get_attributes",
    "frontprompt_get_state",
    "frontprompt_get_outline",
]


def test_tool_list_has_at_least_17_tools() -> None:
    # v0.4.0 extended to 31 tools + fp_status = 32 — exact count owned by test_tool_surface_v0_4_0.py
    # After IPC 0.6.0 removal of 5 deprecated tools the count is 29.
    tools = _build_tool_list()
    assert len(tools) >= 17


def test_tool_list_contains_surviving_v0_3_0_names() -> None:
    """The 6 surviving v0.3.0 tools (pick-creators + page-level) are still present."""
    tools = _build_tool_list()
    names = {t.name for t in tools}
    for name in _ALL_NEW_TOOL_NAMES:
        assert name in names, f"missing surviving v0.3.0 tool: {name}"


def test_removed_v0_3_0_tools_absent() -> None:
    """The 5 deprecated v0.3.0 element-readers are no longer in the tool list."""
    names = {t.name for t in _build_tool_list()}
    for name in _REMOVED_V0_4_0_TOOL_NAMES:
        assert name not in names, f"Removed tool {name!r} still present in tool list"


def test_pick_by_selector_dispatch() -> None:
    req = _build_ipc_request("frontprompt_pick_by_selector", {"selector": ".btn", "comment": "x"})
    assert isinstance(req, PickBySelectorRequest)
    assert req.selector == ".btn"
    assert req.comment == "x"
    assert req.limit == 10
    assert req.parent_pick_id is None


def test_pick_by_selector_with_limit() -> None:
    req = _build_ipc_request("frontprompt_pick_by_selector", {"selector": ".x", "comment": "y", "limit": 25})
    assert isinstance(req, PickBySelectorRequest)
    assert req.limit == 25


def test_pick_by_text_dispatch() -> None:
    req = _build_ipc_request("frontprompt_pick_by_text", {"text": "Submit", "comment": "x"})
    assert isinstance(req, PickByTextRequest)
    assert req.text == "Submit"
    assert req.role is None


def test_pick_by_text_with_role() -> None:
    req = _build_ipc_request("frontprompt_pick_by_text", {"text": "OK", "role": "button", "comment": "x"})
    assert isinstance(req, PickByTextRequest)
    assert req.role == "button"


def test_get_text_dispatch_raises_after_removal() -> None:
    """frontprompt_get_text removed from MCP in IPC 0.6.0 — raises ValueError."""
    with pytest.raises(ValueError, match="unknown tool"):
        _build_ipc_request("frontprompt_get_text", {"pick_ids": ["p1", "p2"]})


def test_get_html_dispatch_raises_after_removal() -> None:
    """frontprompt_get_html removed from MCP in IPC 0.6.0 — raises ValueError."""
    with pytest.raises(ValueError, match="unknown tool"):
        _build_ipc_request("frontprompt_get_html", {"pick_ids": ["p1"]})


def test_get_attributes_dispatch_raises_after_removal() -> None:
    """frontprompt_get_attributes removed from MCP in IPC 0.6.0 — raises ValueError."""
    with pytest.raises(ValueError, match="unknown tool"):
        _build_ipc_request("frontprompt_get_attributes", {"pick_ids": ["p1"]})


def test_get_state_dispatch_raises_after_removal() -> None:
    """frontprompt_get_state removed from MCP in IPC 0.6.0 — raises ValueError."""
    with pytest.raises(ValueError, match="unknown tool"):
        _build_ipc_request("frontprompt_get_state", {"pick_ids": ["p1"]})


def test_get_outline_dispatch_raises_after_removal() -> None:
    """frontprompt_get_outline removed from MCP in IPC 0.6.0 — raises ValueError."""
    with pytest.raises(ValueError, match="unknown tool"):
        _build_ipc_request("frontprompt_get_outline", {"pick_ids": ["p1"]})


def test_screenshot_element_dispatch_default_padding() -> None:
    req = _build_ipc_request("frontprompt_screenshot_element", {"pick_ids": ["p1"]})
    assert isinstance(req, ScreenshotElementRequest)
    assert req.padding == 8


def test_get_page_info_dispatch() -> None:
    req = _build_ipc_request("frontprompt_get_page_info", {})
    assert isinstance(req, GetPageInfoRequest)


def test_screenshot_page_dispatch_default() -> None:
    req = _build_ipc_request("frontprompt_screenshot_page", {})
    assert isinstance(req, ScreenshotPageRequest)
    assert req.full_page is False


def test_screenshot_page_full() -> None:
    req = _build_ipc_request("frontprompt_screenshot_page", {"full_page": True})
    assert isinstance(req, ScreenshotPageRequest)
    assert req.full_page is True


def test_scroll_to_dispatch() -> None:
    req = _build_ipc_request("frontprompt_scroll_to", {"pick_id": "p1"})
    assert isinstance(req, ScrollToRequest)
    assert req.pick_id == "p1"


def test_scroll_to_empty_pick_id_raises() -> None:
    with pytest.raises(ValueError):
        _build_ipc_request("frontprompt_scroll_to", {"pick_id": ""})


def test_unknown_tool_raises() -> None:
    with pytest.raises(ValueError):
        _build_ipc_request("frontprompt_does_not_exist", {})


def test_each_surviving_v0_3_0_tool_has_additional_properties_false() -> None:
    """The 6 surviving v0.3.0 tools all carry additionalProperties: false."""
    tools = _build_tool_list()
    new_tools = [t for t in tools if t.name in _ALL_NEW_TOOL_NAMES]
    assert len(new_tools) == 6
    for tool in new_tools:
        schema = tool.inputSchema
        assert schema.get("additionalProperties") is False, f"tool {tool.name!r} missing additionalProperties: false"
