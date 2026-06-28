"""NullPageController unit tests — verifies every method raises NotImplementedError.

Covers the 14 missing statements in ipc/page_controller.py (lines 177, 180, 183,
186, 189, 192, 195, 198, 201, 209, 217, 224, 232, 239) — the NotImplementedError
raiser body of each NullPageController method.
"""

from __future__ import annotations

import pytest

from frontprompt.ipc.page_controller import NullPageController
from frontprompt.state.state import (
    ElementFingerprint,
    ElementRect,
    Pick,
    PickElement,
)


def _make_pick(pick_id: str = "test-pick") -> Pick:
    fp = ElementFingerprint(
        tag="button",
        attributes={"id": "btn"},
        text="Click",
        path=["html", "body"],
        parent_name="body",
        parent_attribs={},
        parent_text="",
        siblings=[],
        children=[],
    )
    return Pick(
        pick_id=pick_id,
        url="https://example.com/",
        timestamp_ms=1_700_000_000_000,
        element=PickElement(
            selector="button#btn",
            fingerprint=fp,
            text_snippet="Click",
            rect=ElementRect(x=0.0, y=0.0, width=80.0, height=30.0),
        ),
        comment="test pick",
    )


@pytest.mark.anyio
async def test_null_navigate_raises() -> None:
    ctrl = NullPageController()
    with pytest.raises(NotImplementedError, match="no live browser"):
        await ctrl.navigate("https://example.com")


@pytest.mark.anyio
async def test_null_get_text_raises() -> None:
    ctrl = NullPageController()
    with pytest.raises(NotImplementedError, match="no live browser"):
        await ctrl.get_text([_make_pick()])


@pytest.mark.anyio
async def test_null_get_html_raises() -> None:
    ctrl = NullPageController()
    with pytest.raises(NotImplementedError, match="no live browser"):
        await ctrl.get_html([_make_pick()], max_chars=500)


@pytest.mark.anyio
async def test_null_get_attributes_raises() -> None:
    ctrl = NullPageController()
    with pytest.raises(NotImplementedError, match="no live browser"):
        await ctrl.get_attributes([_make_pick()])


@pytest.mark.anyio
async def test_null_get_state_raises() -> None:
    ctrl = NullPageController()
    with pytest.raises(NotImplementedError, match="no live browser"):
        await ctrl.get_state([_make_pick()])


@pytest.mark.anyio
async def test_null_get_outline_raises() -> None:
    ctrl = NullPageController()
    with pytest.raises(NotImplementedError, match="no live browser"):
        await ctrl.get_outline([_make_pick()], max_depth=3, max_nodes=50)


@pytest.mark.anyio
async def test_null_screenshot_element_raises() -> None:
    ctrl = NullPageController()
    with pytest.raises(NotImplementedError, match="no live browser"):
        await ctrl.screenshot_element([_make_pick()], padding=4)


@pytest.mark.anyio
async def test_null_screenshot_page_raises() -> None:
    ctrl = NullPageController()
    with pytest.raises(NotImplementedError, match="no live browser"):
        await ctrl.screenshot_page(full_page=False)


@pytest.mark.anyio
async def test_null_get_page_info_raises() -> None:
    ctrl = NullPageController()
    with pytest.raises(NotImplementedError, match="no live browser"):
        await ctrl.get_page_info()


@pytest.mark.anyio
async def test_null_scroll_to_raises() -> None:
    ctrl = NullPageController()
    with pytest.raises(NotImplementedError, match="no live browser"):
        await ctrl.scroll_to(_make_pick())


@pytest.mark.anyio
async def test_null_query_selector_all_raises() -> None:
    ctrl = NullPageController()
    with pytest.raises(NotImplementedError, match="no live browser"):
        await ctrl.query_selector_all("button", parent_pick=None, limit=10)


@pytest.mark.anyio
async def test_null_eval_js_raises() -> None:
    ctrl = NullPageController()
    with pytest.raises(NotImplementedError, match="no live browser"):
        await ctrl.eval_js("document.title", pick_id_arg=None, mutating=False)


@pytest.mark.anyio
async def test_null_dom_patch_raises() -> None:
    ctrl = NullPageController()
    with pytest.raises(NotImplementedError, match="no live browser"):
        await ctrl.dom_patch(_make_pick(), operations=[{"op": "set_text", "value": "hi"}])


@pytest.mark.anyio
async def test_null_pick_by_xpath_raw_raises() -> None:
    ctrl = NullPageController()
    with pytest.raises(NotImplementedError, match="no live browser"):
        await ctrl.pick_by_xpath_raw("//button", parent_pick=None, limit=5)


@pytest.mark.anyio
async def test_null_evaluate_pick_dynamic_fields_raises() -> None:
    ctrl = NullPageController()
    with pytest.raises(NotImplementedError, match="no live browser"):
        await ctrl.evaluate_pick_dynamic_fields(_make_pick(), fields=["visible"])
