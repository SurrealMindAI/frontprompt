"""Arch test: window.__fp Namespace-Discipline (Python-side).

Spiegelung von :file:`frontend/src/__arch__/window-fp-namespace.test.ts` für die
Python-Seite. Selbe Regel:

    window.__fp ist der **einzige** erlaubte window-global im overlay.

Die Python-Seite erstellt den global indirekt — via Playwright's
``page.expose_function(name, fn)``. Der ``name``-string-literal landet als
``window.<name>`` im Browser-context. Wir schützen daher hier alle
Python-source-files gegen Token-References die ``__fp<anything>`` matchen,
außer dem expliziten Allow-list-Scaffold.

Forbidden-pattern (siehe TS-Variante für volle Tabelle):
    ``__fp_locator``, ``__fpLocator``, ``__fp1``, ``__fp-debug``, ``__FP``,
    ``__Fp_thing``, ``__fp$internal`` — alles forbidden.

Allowed:
    Bare lowercase ``__fp`` (vor ``.``, end-of-token, ``=``, ``(`` etc.)
    Plus explizit allow-list pro Datei (Playwright-scaffold im cli.py).

Verifikation: pytest scant ``src/frontprompt/`` rekursiv auf Python-files.
"""

from __future__ import annotations

import re
from pathlib import Path

import pytest

# ---------------------------------------------------------------------------
# Config
# ---------------------------------------------------------------------------

#: Source-tree-root — alle ``.py``-files darunter werden gescannt.
SRC_ROOT: Path = Path(__file__).resolve().parents[2] / "src" / "frontprompt"

#: Token-pattern — identisch zur TS-Regex (siehe ts arch test fürs Detail).
FORBIDDEN_TOKEN = re.compile(r"\b__[Ff][Pp][A-Za-z0-9_$-]*")

#: Das eine erlaubte token — bare lowercase ``__fp``.
THE_ONE_ALLOWED_TOKEN: str = "__fp"

#: Per-file allow-list — relativer pfad ab :data:`SRC_ROOT` → set erlaubter tokens.
#:
#: Jeder Eintrag MUSS einen inline-comment in der source haben, der erklärt
#: warum das Token dort gerechtfertigt ist (z.B. Migration-Pattern, scaffold-name).
ALLOW_LIST: dict[str, frozenset[str]] = {
    # show_session.py:ShowSession.run() exposes __fp_internal_state_getter as a
    # Playwright-scaffold-global (extracted from cli.py._show_async_main).
    # Wird vom overlay's setupBridge() SOFORT auf window.__fp.getState migriert
    # + via `delete` aus dem window-namespace entfernt —
    # siehe frontend/src/bridge/bridge.svelte.ts:setupBridge.
    #
    # TOCTOU-Entscheidung — accept as
    # architectural false-positive. Playwright's expose_function kann nur
    # top-level window globals registrieren (CDP-Einschränkung, kein Bug).
    # Das Fenster schließt synchron bei DOMContentLoaded; die exponierten Daten
    # (Session-picks/regions/relations) sind keine Credentials oder cross-user
    # data.
    # Für vollständige Entscheidungsrationale siehe die Known-TOCTOU-Limitations-Notiz.
    # Phase-2 Escape Hatch: UUID-named getter + page.evaluate seed statt
    # expose_function — Trigger wenn threat model auf Credentials expandiert.
    "show_session.py": frozenset({"__fp_internal_state_getter"}),
}


# ---------------------------------------------------------------------------
# Scanning logic
# ---------------------------------------------------------------------------


def _walk_python_sources() -> list[Path]:
    """Discover all .py files under SRC_ROOT (excluding __pycache__)."""
    return [p for p in SRC_ROOT.rglob("*.py") if "__pycache__" not in p.parts]


def _classify(content: str) -> tuple[bool, list[str]]:
    """Return ``(has_violation, all_matched_tokens)``.

    Allow-list NICHT hier — das ist file-level enforcement.
    Bare lowercase ``__fp`` zählt nicht als violation.
    """
    tokens = FORBIDDEN_TOKEN.findall(content)
    forbidden = any(t != THE_ONE_ALLOWED_TOKEN for t in tokens)
    return forbidden, tokens


# ---------------------------------------------------------------------------
# Tests
# ---------------------------------------------------------------------------


def test_source_scan_no_forbidden_tokens_outside_allow_list() -> None:
    """Real-source scan: kein ``__fp<anything>`` außer dem ALLOW_LIST-Scaffold."""
    files = _walk_python_sources()
    assert files, f"Keine Python-files unter {SRC_ROOT} — broken test setup?"

    violations: list[tuple[str, int, str, str]] = []  # (file, line, token, snippet)

    for file in files:
        rel = file.relative_to(SRC_ROOT).as_posix()
        content = file.read_text(encoding="utf-8")
        allowed = ALLOW_LIST.get(rel, frozenset())

        for match in FORBIDDEN_TOKEN.finditer(content):
            token = match.group(0)
            # Bare lowercase __fp — the one true global, always allowed
            if token == THE_ONE_ALLOWED_TOKEN:
                continue
            # Per-file scaffold allow-list
            if token in allowed:
                continue

            line_no = content.count("\n", 0, match.start()) + 1
            snippet = content.splitlines()[line_no - 1].strip() if line_no <= len(content.splitlines()) else ""
            violations.append((rel, line_no, token, snippet))

    if violations:
        report = "\n\n".join(
            f"    {rel}:{line}\n        token:   {token}\n        context: {snippet}"
            for rel, line, token, snippet in violations
        )
        pytest.fail(
            "\n"
            + "═" * 75
            + "\nARCH-VIOLATION: window.__fp namespace discipline (Python-side)\n"
            + "═" * 75
            + "\n\n"
            + "Nur EIN window-global ist erlaubt: window.__fp\n\n"
            + "Verboten: __fp_<anything> (z.B. __fp_locator, __fp_debug)\n"
            + "Auch nicht via page.expose_function('__fp_x', …) — Playwright\n"
            + "scaffolds nur mit Migration+Delete-Pattern (siehe cli.py + bridge.svelte.ts).\n\n"
            + f"Verstöße:\n{report}\n\n"
            + "See: docs/wire-protocol.md\n"
            + "Allow-list: tests/arch/test_window_fp_namespace.py:ALLOW_LIST\n"
        )


def test_allow_list_no_dangling_references() -> None:
    """Allow-list-Einträge müssen tatsächlich in der referenzierten Datei vorkommen."""
    dangling: list[str] = []
    for rel, tokens in ALLOW_LIST.items():
        full = SRC_ROOT / rel
        if not full.is_file():
            dangling.append(f"{rel} (Datei existiert nicht)")
            continue
        content = full.read_text(encoding="utf-8")
        for token in tokens:
            if token not in content:
                dangling.append(f"{rel} → {token} (in ALLOW_LIST aber nicht in Datei)")
    assert not dangling, "ALLOW_LIST hat veraltete Einträge — Datei umbenannt oder Token entfernt:\n" + "\n".join(
        dangling
    )


# ---------------------------------------------------------------------------
# Regex Self-Test — explizit jede Variante die im TS-equivalent abgedeckt ist
# ---------------------------------------------------------------------------

_FORBIDDEN_VARIANTS: list[tuple[str, str]] = [
    ("underscore suffix", 'page.expose_function("__fp_locator", fn)'),
    ("camelCase suffix in string", 'fn_name = "__fpLocator"'),
    ("single digit", 'page.expose_function("__fp1", fn)'),
    ("multi-digit", "name = '__fp123'"),
    ("dash in attr-string", "el.setAttribute('__fp-debug', '1')"),
    ("dollar suffix", 'name = "__fp$internal"'),
    ("uppercase bare", "GLOBAL_NAME = '__FP'"),
    ("uppercase with suffix", 'name = "__FP_LOCATOR"'),
    ("mixed case prefix", 'attr = "__Fp_Thing"'),
    ("snake_case suffix", 'page.expose_function("__fp_internal_debug_helpers", fn)'),
    ("single-letter suffix __fpa", 'name = "__fpa"'),
    ("trailing underscore alone", 'name = "__fp_"'),
    ("comment reference to forbidden", "# don't use __fp_locator anywhere"),
]

_ALLOWED_VARIANTS: list[tuple[str, str]] = [
    ("bare __fp in eval-string", "page.evaluate('window.__fp.dispatch(p)')"),
    ("constant assignment", 'WINDOW_NAMESPACE: str = "__fp"'),
    ("comment with __fp.method", "# window.__fp.getState() is called pre-mount"),
    ("__fp followed by paren", "f'window.__fp({msg})'"),
    ("__fp followed by equals", "window.__fp = value"),
    ("__fp followed by close-paren", "result = window.__fp"),
    ("inside-longer-identifier no boundary", "abc__fp_x = 1"),
    ("totally unrelated code", "some_var = 'hello world'"),
]


@pytest.mark.parametrize(
    "_label,source",
    _FORBIDDEN_VARIANTS,
    ids=[label for label, _ in _FORBIDDEN_VARIANTS],
)
def test_regex_catches_forbidden_variant(_label: str, source: str) -> None:
    forbidden, tokens = _classify(source)
    assert forbidden, f"expected violation for: {source!r}, but got tokens={tokens}"


@pytest.mark.parametrize(
    "_label,source",
    _ALLOWED_VARIANTS,
    ids=[label for label, _ in _ALLOWED_VARIANTS],
)
def test_regex_allows_legitimate_variant(_label: str, source: str) -> None:
    forbidden, tokens = _classify(source)
    assert not forbidden, f"unexpected violation for: {source!r}, tokens={tokens}"
