"""CI drift gate — schützt den wire-events SSoT-Vertrag.

ZWECK
=====
CI führt ``pytest -m drift`` aus. Wenn das committed ``wire-events.gen.ts``
nicht mehr dem entspricht, was die Pipeline heute erzeugen würde, schlägt
dieser Test mit einem unified diff fehl. Das bedeutet: jemand hat ein
Pydantic-Wire-Model geändert, aber vergessen, das Goldenfile zu regenerieren.

Das ist exakt die ``regenerate -> git diff --quiet``-Disziplin des
drift-gate-Patterns.

LOKALER DEV-WORKFLOW
====================
Fehlgeschlagen? Ausführen:

    uv run pydantic-zod-codegen generate frontprompt.wire \\
        --output tests/goldenfile/wire-events.gen.ts

dann ``git diff tests/goldenfile/wire-events.gen.ts`` prüfen und committen.

bun muss im PATH sein (``bunx json-schema-to-typescript`` wird intern gerufen).

REFERENZ
========
- Das drift-gate-Pattern: regeneriere den Goldenfile und schlage fehl, wenn
  der Diff nicht leer ist.
"""

from __future__ import annotations

from pathlib import Path

import pytest

_GOLDENFILE = Path(__file__).parent / "goldenfile" / "wire-events.gen.ts"


@pytest.mark.drift
def test_wire_events_goldenfile_matches_pipeline() -> None:
    """Drift gate: wire-events SSoT — regenerieren und gegen committed file vergleichen.

    Ein einziger Test, ein einziges Goldenfile. Ein Protocol, ein Gate.
    """
    from pydantic_zod_codegen import check_drift

    drift_detected, diff_text = check_drift(
        "frontprompt.wire",
        _GOLDENFILE,
    )
    assert drift_detected is False, (
        "wire-events.gen.ts hat gedriftet!\n"
        "Fix: uv run pydantic-zod-codegen generate frontprompt.wire "
        "--output tests/goldenfile/wire-events.gen.ts && git add tests/goldenfile/wire-events.gen.ts\n\n"
        f"Diff:\n{diff_text}"
    )
