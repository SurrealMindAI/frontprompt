"""Inspect tests — static (snapshot) + dynamic (live page) hybrid.

Static-only tests: no PageController, pure lxml.
Dynamic tests: FakeInspectController returns canned evaluate results.
"""

from __future__ import annotations

import pytest

from frontprompt.analysis._impl.scrapling_bridge import parse_html
from frontprompt.analysis.inspect import DYNAMIC_FIELDS, STATIC_FIELDS, Inspector
from frontprompt.state.state import (
    ElementFingerprint,
    ElementRect,
    Pick,
    PickElement,
)

_HTML = """<html><body>
  <button id="save" class="btn primary" role="button">Save</button>
  <input type="text" name="email" value="user@example.com" />
</body></html>"""


def _make_pick(selector: str, tag: str, text: str, pick_id: str = "p1") -> Pick:
    fp = ElementFingerprint(tag=tag, attributes={"id": selector.lstrip("#")}, text=text)
    return Pick(
        pick_id=pick_id,
        url="https://x.com/",
        timestamp_ms=1_700_000_000_000,
        element=PickElement(
            selector=selector,
            fingerprint=fp,
            text_snippet=text[:120],
            rect=ElementRect(x=0.0, y=0.0, width=80.0, height=32.0),
        ),
        comment="test",
    )


class _FakeEvaluateController:
    """Returns canned dynamic-field data per pick_id."""

    def __init__(self, data: dict) -> None:
        self._data = data  # pick_id -> dict of dynamic fields

    async def evaluate_pick_dynamic_fields(self, pick: Pick, fields: list[str]) -> dict:
        return self._data.get(pick.pick_id, {"error": "stale_pick"})


def test_inspect_static_fields_text_and_role() -> None:
    doc = parse_html(_HTML)
    pick = _make_pick("#save", "button", "Save")
    inspector = Inspector()
    results = inspector.inspect_static(doc, [pick], fields=["text", "role"])
    assert len(results) == 1
    result = results[0]
    assert result.pick_id == "p1"
    assert result.error is None
    assert result.text is not None
    assert "Save" in result.text


def test_inspect_static_stale_pick() -> None:
    doc = parse_html(_HTML)
    pick = _make_pick("#nonexistent", "div", "gone")
    inspector = Inspector()
    results = inspector.inspect_static(doc, [pick], fields=["text"])
    assert results[0].error == "stale_pick"


def test_inspect_static_fields_constant_sets() -> None:
    """STATIC_FIELDS and DYNAMIC_FIELDS are frozensets with expected members."""
    assert "text" in STATIC_FIELDS
    assert "role" in STATIC_FIELDS
    assert "attributes" in STATIC_FIELDS
    assert "visible" in DYNAMIC_FIELDS
    assert "enabled" in DYNAMIC_FIELDS
    assert "focused" in DYNAMIC_FIELDS


@pytest.mark.anyio
async def test_inspect_dynamic_fields_via_fake_controller() -> None:
    doc = parse_html(_HTML)
    pick = _make_pick("#save", "button", "Save")
    fake_ctrl = _FakeEvaluateController(
        {
            "p1": {"visible": True, "enabled": True, "focused": False},
        }
    )
    inspector = Inspector()
    results = await inspector.inspect_dynamic(doc, [pick], fields=["visible", "enabled"], page_controller=fake_ctrl)
    assert results[0].visible is True
    assert results[0].enabled is True


@pytest.mark.anyio
async def test_inspect_mixed_fields_merged() -> None:
    doc = parse_html(_HTML)
    pick = _make_pick("#save", "button", "Save")
    fake_ctrl = _FakeEvaluateController(
        {
            "p1": {"visible": True, "enabled": True},
        }
    )
    inspector = Inspector()
    results = await inspector.inspect(doc, [pick], fields=["text", "visible", "enabled"], page_controller=fake_ctrl)
    result = results[0]
    assert result.error is None
    assert result.text is not None
    assert result.visible is True


@pytest.mark.anyio
async def test_inspect_dynamic_stale_pick_via_controller() -> None:
    doc = parse_html(_HTML)
    pick = _make_pick("#save", "button", "Save")
    fake_ctrl = _FakeEvaluateController(
        {
            "p1": {"error": "stale_pick"},
        }
    )
    inspector = Inspector()
    results = await inspector.inspect_dynamic(doc, [pick], fields=["visible"], page_controller=fake_ctrl)
    assert results[0].error == "stale_pick"
