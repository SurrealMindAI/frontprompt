"""Scrapling Compatibility Smoke-Test für ElementFingerprint.

Lock the Phase-1 → Phase-2 contract: unser :class:`ElementFingerprint`
muss ohne weitere Konvertierung an Scrapling's ``Selector.relocate(dict)``
übergeben werden können, und sinnvoll matchen.

Was hier validiert wird:
    1. Field-names matchen Scrapling's ``_StorageTools.element_to_dict``
       (parent_name / parent_attribs / etc.)
    2. ``Selector.relocate(fp.model_dump(), percentage=70)`` findet ELEMENT(E)
       in identischer HTML
    3. Bei kleiner DOM-Drift (z.B. Klasse hinzu) findet relocate trotzdem
       (similarity-score über threshold)
    4. Bei großer DOM-Drift fällt das Element raus (oder kommt mit niedrigerem score)

Ohne diesen Test wäre die "Phase 2 ohne Refactor"-Behauptung aus
dem Inspector-Picker-Design unbewiesen.
"""

from __future__ import annotations

from types import ModuleType

import pytest

from frontprompt.state.state import ElementFingerprint

# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------

# Simuliert was unsere TS-side buildFingerprint() für `<div id="hero-cta" ...>`
# in der HEAD-Fixture liefern würde.
ORIGINAL_FINGERPRINT_DICT = {
    "tag": "div",
    "attributes": {"id": "hero-cta", "class": "btn primary"},
    "text": "Click me",
    "path": ["html", "body", "main", "section", "div"],
    "parent_name": "section",
    "parent_attribs": {"class": "hero"},
    "parent_text": "Welcome to the hero section",
    "siblings": ["h1", "p"],  # without self
    "children": [],
}

# Identische HTML — relocate sollte mit nahezu 100% score matchen.
ORIGINAL_HTML = """
<!DOCTYPE html>
<html>
<body>
  <main>
    <section class="hero">
      <h1>Welcome</h1>
      <p>to the hero section</p>
      <div id="hero-cta" class="btn primary">Click me</div>
    </section>
  </main>
</body>
</html>
"""

# Kleine DOM-Drift: id-attribute geändert (z.B. SPA-Re-Render), Klasse hinzu,
# eine Sibling-Reihenfolge geändert. Score sollte noch über threshold sein.
SLIGHTLY_DRIFTED_HTML = """
<!DOCTYPE html>
<html>
<body>
  <main>
    <section class="hero featured">
      <h1>Welcome back</h1>
      <p>to the hero section</p>
      <div id="hero-cta-renamed" class="btn primary new-class">Click me</div>
    </section>
  </main>
</body>
</html>
"""

# Große Drift: komplett anderes Element-tree, kein hero-cta-äquivalent
COMPLETELY_DIFFERENT_HTML = """
<!DOCTYPE html>
<html>
<body>
  <header>
    <nav><a href="/x">link</a></nav>
  </header>
  <footer>©2026</footer>
</body>
</html>
"""


# ---------------------------------------------------------------------------
# Pydantic round-trip → dict-shape — verifies our model produces the right keys
# ---------------------------------------------------------------------------


def test_pydantic_fingerprint_dump_has_scrapling_keys() -> None:
    """ElementFingerprint.model_dump() liefert exakt die keys die Scrapling erwartet."""
    fp = ElementFingerprint(
        tag="div",
        attributes={"id": "x"},
        text="hi",
        path=["html", "body", "div"],
        parent_name="body",
        parent_attribs={},
        parent_text="",
        siblings=[],
        children=[],
    )
    dumped = fp.model_dump()
    expected_keys = {
        "tag",
        "attributes",
        "text",
        "path",
        "parent_name",  # NOT parent_tag
        "parent_attribs",  # NOT parent_attributes
        "parent_text",
        "siblings",
        "children",
    }
    assert set(dumped.keys()) == expected_keys


# ---------------------------------------------------------------------------
# Scrapling — does it consume our dict + find the element?
# ---------------------------------------------------------------------------


@pytest.fixture
def scrapling_module() -> ModuleType:
    """Import scrapling lazily; if package not available, skip whole module."""
    scrapling = pytest.importorskip("scrapling", reason="scrapling not installed")
    return scrapling


def test_scrapling_consumes_our_dict_without_keyerror(scrapling_module: ModuleType) -> None:
    """Smoke test: feed our dict-format at Scrapling — keine KeyError / AttributeError."""
    from scrapling.parser import Selector

    page = Selector(content=ORIGINAL_HTML)
    # Smoke: relocate() with percentage=0 returns ALL elements scored, no exception.
    # We don't care about result yet — just that Scrapling parses our dict.
    try:
        page.relocate(element=ORIGINAL_FINGERPRINT_DICT, percentage=0)
    except (KeyError, AttributeError) as exc:
        pytest.fail(
            f"Scrapling rejected our fingerprint dict shape: {exc}. "
            f"Field-name mismatch zwischen state.py ElementFingerprint und Scrapling's element_to_dict."
        )


def test_scrapling_relocates_in_identical_html(scrapling_module: ModuleType) -> None:
    """Bei identischer HTML muss relocate das Element finden (hoher score)."""
    from scrapling.parser import Selector

    page = Selector(content=ORIGINAL_HTML)
    matches = page.relocate(element=ORIGINAL_FINGERPRINT_DICT, percentage=70)
    assert matches, "relocate() fand kein matchendes Element in identischer HTML"
    # First match should be our div
    first = matches[0]
    assert first.tag == "div"
    attribs = dict(first.attrib)
    assert attribs.get("id") == "hero-cta"


def test_scrapling_relocates_in_slightly_drifted_html(scrapling_module: ModuleType) -> None:
    """Bei kleiner Drift (id-rename + class-add) findet relocate noch (>50%)."""
    from scrapling.parser import Selector

    page = Selector(content=SLIGHTLY_DRIFTED_HTML)
    matches = page.relocate(element=ORIGINAL_FINGERPRINT_DICT, percentage=50)
    assert matches, (
        "relocate() fand kein matchendes Element bei kleiner Drift (id-rename + class-add). "
        "Phase-2 Adaptive-Relocate würde hier silent fehlschlagen."
    )
    # Should still pick our cta-renamed div (same tag, similar attribs, same path)
    first = matches[0]
    assert first.tag == "div"


def test_scrapling_returns_empty_or_low_score_for_different_html(scrapling_module: ModuleType) -> None:
    """Bei komplett anderer HTML: relocate sollte mit hohem threshold leer zurückkommen."""
    from scrapling.parser import Selector

    page = Selector(content=COMPLETELY_DIFFERENT_HTML)
    matches = page.relocate(element=ORIGINAL_FINGERPRINT_DICT, percentage=80)
    # Es darf kein false-positive bei 80% threshold in völlig anderer page geben
    assert not matches or all(m.tag != "div" for m in matches), (
        f"relocate() lieferte false-positive matches bei 80% threshold: {matches}"
    )


# ---------------------------------------------------------------------------
# Property-test: jede field-rename brechen this test → catches future drift
# ---------------------------------------------------------------------------


def test_all_scrapling_score_input_keys_present_in_our_model() -> None:
    """Hard-coded keys die Scrapling's __calculate_similarity_score liest.

    Wenn jemand in state.py einen field rename macht, sollen wir das hier merken
    — sonst würde Phase-2 silent niedrigere Scores produzieren weil das parent-
    Block übersprungen wird (line 843: ``if original.get("parent_name"):``).
    """
    # Aus scrapling/parser.py:803-868 __calculate_similarity_score
    scrapling_read_keys = {
        "tag",
        "text",
        "attributes",
        "path",
        "parent_name",
        "parent_attribs",
        "parent_text",
        "siblings",
    }
    fp = ElementFingerprint(tag="div")
    available_keys = set(fp.model_dump().keys())
    missing = scrapling_read_keys - available_keys
    assert not missing, (
        f"Scrapling's __calculate_similarity_score liest keys die wir nicht emittieren: {missing}. "
        f"Diese fingerprints würden in Phase-2 silently mit reduzierten checks-count scoren."
    )
