"""Relocator tests — alive / recovered / stale classification."""

from __future__ import annotations

from frontprompt.analysis._impl.scrapling_bridge import parse_html
from frontprompt.analysis.relocator import Relocator
from frontprompt.state.state import (
    ElementFingerprint,
    ElementRect,
    Pick,
    PickElement,
)

_HTML_ORIGINAL = """<html><body>
  <button id="submit-btn" class="primary">Submit</button>
</body></html>"""

_HTML_CLASS_MUTATED = """<html><body>
  <button id="submit-btn" class="primary active">Submit</button>
</body></html>"""

_HTML_ELEMENT_GONE = """<html><body>
  <p>No button here</p>
</body></html>"""


def _make_pick_for_button() -> Pick:
    fp = ElementFingerprint(
        tag="button",
        attributes={"id": "submit-btn", "class": "primary"},
        text="Submit",
        path=["html", "body"],
        parent_name="body",
        parent_attribs={},
        parent_text="",
        siblings=[],
        children=[],
    )
    return Pick(
        pick_id="test-pick",
        url="https://example.com/",
        timestamp_ms=1_700_000_000_000,
        element=PickElement(
            selector="button#submit-btn",
            fingerprint=fp,
            text_snippet="Submit",
            rect=ElementRect(x=0.0, y=0.0, width=80.0, height=32.0),
        ),
        comment="submit button",
    )


def test_relocate_alive_exact_match() -> None:
    doc = parse_html(_HTML_ORIGINAL)
    pick = _make_pick_for_button()
    relocator = Relocator()
    results = relocator.relocate(doc, [pick])
    assert len(results) == 1
    assert results[0].pick_id == "test-pick"
    assert results[0].status == "alive"


def test_relocate_stale_element_gone() -> None:
    doc = parse_html(_HTML_ELEMENT_GONE)
    pick = _make_pick_for_button()
    relocator = Relocator()
    results = relocator.relocate(doc, [pick])
    assert results[0].status == "stale"


def test_relocate_recovered_with_similarity() -> None:
    """Mutated class — original selector still matches but fingerprint drift.

    With class mutation, CSS selector (id-based) still resolves. The
    fingerprint similarity may flag it as recovered or alive depending on
    bridge impl. Test that it is NOT stale.
    """
    doc = parse_html(_HTML_CLASS_MUTATED)
    pick = _make_pick_for_button()
    relocator = Relocator()
    results = relocator.relocate(doc, [pick])
    assert results[0].status in ("alive", "recovered")
    if results[0].status == "recovered":
        assert results[0].similarity is not None
        assert results[0].similarity > 0.5
