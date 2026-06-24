"""frontprompt.wire — Wire-Protocol-Package.

Enthält die discriminated-union Pydantic-Models für das frontprompt
Wire-Protokoll:

* :mod:`frontprompt.wire.events` — Daemon→Tab Push-Events (Channel 2)
* :mod:`frontprompt.wire.mutations` — Tab→Daemon POST-Mutations (Channel 3)

See ARCHITECTURE.md for the wire-protocol design.

__codegen_roots__ bestimmt welche Top-Level-Models die schema-codegen
Pipeline als Zod-Output emittiert und im Drift-Gate schützt.
Reihenfolge ist verbindlich — die Goldenfile wird in dieser
Reihenfolge committed; Änderungen hier erzwingen Goldenfile-Regeneration.
"""

from __future__ import annotations

from frontprompt.wire.events import EventEnvelope
from frontprompt.wire.mutations import MutationEnvelope

__all__ = ["EventEnvelope", "MutationEnvelope"]

# Codegen-contract — the drift-gate-ci liest diese Liste.
# Convention: nur Top-Level-Envelope-Models; Payload-Subtypen werden vom
# Codegen automatisch via $defs aufgelöst.
# Reihenfolge Events-vor-Mutations ist alphabetisch/wire-directionality-first.
__codegen_roots__ = [
    "EventEnvelope",
    "MutationEnvelope",
]
