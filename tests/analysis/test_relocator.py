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


# ---------------------------------------------------------------------------
# Branch coverage: sim < 0.7 with CSS still resolving (line 54)
# ---------------------------------------------------------------------------


def test_relocate_css_matches_but_sim_below_threshold_still_recovered() -> None:
    """When CSS selector resolves but fingerprint sim < 0.7, status is 'recovered' (line 54).

    Monkeypatching fingerprint_similarity to return 0.5 forces the third branch
    in _relocate_one where sim < _RECOVERED_THRESHOLD (0.7).
    """
    from unittest.mock import patch

    doc = parse_html(_HTML_ORIGINAL)  # has button#submit-btn → CSS resolves
    pick = _make_pick_for_button()

    with patch("frontprompt.analysis.relocator.fingerprint_similarity", return_value=0.5):
        relocator = Relocator()
        results = relocator.relocate(doc, [pick])

    assert results[0].status == "recovered"
    assert results[0].similarity == 0.5


# ---------------------------------------------------------------------------
# Branch coverage: CSS fails, scrapling fallback with sim >= 0.7 (lines 64-66)
# ---------------------------------------------------------------------------


def test_relocate_fallback_recovered_when_scrapling_finds_similar() -> None:
    """When CSS selector fails but scrapling fallback finds a similar element (lines 64-66).

    Uses an HTML where 'button#submit-btn' doesn't exist, but monkeypatches
    relocate_element to return a fake match with sim = 0.75 (>= 0.7 threshold).
    """
    from unittest.mock import MagicMock, patch

    doc = parse_html(_HTML_ELEMENT_GONE)  # no button#submit-btn → CSS returns []
    pick = _make_pick_for_button()

    fake_match = MagicMock()
    fake_match.css_selector = "p.fallback-found"

    with (
        patch("frontprompt.analysis.relocator.relocate_element", return_value=fake_match),
        patch("frontprompt.analysis.relocator.fingerprint_similarity", return_value=0.75),
    ):
        relocator = Relocator()
        results = relocator.relocate(doc, [pick])

    assert results[0].status == "recovered"
    assert results[0].new_selector == "p.fallback-found"
    assert results[0].similarity == 0.75
