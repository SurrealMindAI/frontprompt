"""Pydantic-validation tests for IPC Schema 0.3.0 (11 new Request classes)."""

from __future__ import annotations

import pytest
from pydantic import ValidationError

from frontprompt.ipc.protocol import (
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
)


def test_schema_version_bumped() -> None:
    # Version assertion moved to tests/ipc/test_protocol_v0_4_0.py
    pass


# ── Pick-Creators ──────────────────────────────────────────────────────────────


def test_pick_by_selector_minimal() -> None:
    r = PickBySelectorRequest(selector=".btn", comment="submit-buttons")
    assert r.kind == "pick_by_selector"
    assert r.limit == 10
    assert r.parent_pick_id is None


def test_pick_by_selector_with_parent_and_limit() -> None:
    r = PickBySelectorRequest(
        selector=".btn",
        comment="x",
        parent_pick_id="p1",
        limit=25,
    )
    assert r.parent_pick_id == "p1"
    assert r.limit == 25


def test_pick_by_selector_rejects_empty_selector() -> None:
    with pytest.raises(ValidationError):
        PickBySelectorRequest(selector="", comment="x")


def test_pick_by_selector_rejects_limit_zero() -> None:
    with pytest.raises(ValidationError):
        PickBySelectorRequest(selector=".x", comment="y", limit=0)


def test_pick_by_selector_rejects_limit_over_50() -> None:
    with pytest.raises(ValidationError):
        PickBySelectorRequest(selector=".x", comment="y", limit=51)


def test_pick_by_selector_rejects_extra_fields() -> None:
    with pytest.raises(ValidationError):
        PickBySelectorRequest(selector=".x", comment="y", weird="z")


def test_pick_by_text_minimal() -> None:
    r = PickByTextRequest(text="Submit", comment="submit-link")
    assert r.role is None
    assert r.limit == 10


def test_pick_by_text_with_role() -> None:
    r = PickByTextRequest(text="Submit", role="button", comment="x")
    assert r.role == "button"


# ── Element-Readers ───────────────────────────────────────────────────────────


@pytest.mark.parametrize("cls", [GetTextRequest, GetAttributesRequest, GetStateRequest])
def test_simple_reader_minimal(cls: type) -> None:
    r = cls(pick_ids=["p1"])
    assert r.pick_ids == ["p1"]


@pytest.mark.parametrize(
    "cls",
    [
        GetTextRequest,
        GetHtmlRequest,
        GetAttributesRequest,
        GetStateRequest,
        GetOutlineRequest,
        ScreenshotElementRequest,
    ],
)
def test_reader_rejects_empty_pick_ids(cls: type) -> None:
    with pytest.raises(ValidationError):
        cls(pick_ids=[])


@pytest.mark.parametrize(
    "cls",
    [
        GetTextRequest,
        GetHtmlRequest,
        GetAttributesRequest,
        GetStateRequest,
        GetOutlineRequest,
        ScreenshotElementRequest,
    ],
)
def test_reader_rejects_over_50_pick_ids(cls: type) -> None:
    with pytest.raises(ValidationError):
        cls(pick_ids=[f"p{i}" for i in range(51)])


def test_get_html_max_chars_bounds() -> None:
    GetHtmlRequest(pick_ids=["p1"], max_chars=100)
    GetHtmlRequest(pick_ids=["p1"], max_chars=100_000)
    with pytest.raises(ValidationError):
        GetHtmlRequest(pick_ids=["p1"], max_chars=99)
    with pytest.raises(ValidationError):
        GetHtmlRequest(pick_ids=["p1"], max_chars=100_001)


def test_get_outline_bounds() -> None:
    GetOutlineRequest(pick_ids=["p1"], max_depth=1, max_nodes=1)
    GetOutlineRequest(pick_ids=["p1"], max_depth=10, max_nodes=1000)
    with pytest.raises(ValidationError):
        GetOutlineRequest(pick_ids=["p1"], max_depth=11)
    with pytest.raises(ValidationError):
        GetOutlineRequest(pick_ids=["p1"], max_nodes=1001)


def test_screenshot_element_padding_bounds() -> None:
    ScreenshotElementRequest(pick_ids=["p1"], padding=0)
    ScreenshotElementRequest(pick_ids=["p1"], padding=100)
    with pytest.raises(ValidationError):
        ScreenshotElementRequest(pick_ids=["p1"], padding=-1)
    with pytest.raises(ValidationError):
        ScreenshotElementRequest(pick_ids=["p1"], padding=101)


# ── Page-level ────────────────────────────────────────────────────────────────


def test_get_page_info_no_required_fields() -> None:
    r = GetPageInfoRequest()
    assert r.kind == "get_page_info"


def test_screenshot_page_default_viewport() -> None:
    r = ScreenshotPageRequest()
    assert r.full_page is False


def test_screenshot_page_full() -> None:
    r = ScreenshotPageRequest(full_page=True)
    assert r.full_page is True


def test_scroll_to_requires_single_pick_id() -> None:
    r = ScrollToRequest(pick_id="p1")
    assert r.pick_id == "p1"


def test_scroll_to_rejects_empty_pick_id() -> None:
    with pytest.raises(ValidationError):
        ScrollToRequest(pick_id="")
