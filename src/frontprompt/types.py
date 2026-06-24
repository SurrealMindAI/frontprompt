"""Zentrale ID-NewType-Definitionen für alle Aggregate-Boundaries.

Alle Identifier sind ``str``-basierte NewTypes (UUID4-Format im Laufzeit-Wert).
NewType verhindert versehentliches Mischen: ``TaskId`` ist nicht ``PageSessionId``,
obwohl beide zur Laufzeit ``str`` sind.

Import-Regel: Dieses Modul importiert nichts aus ``frontprompt.bc`` — es ist der
gemeinsame Boden, von dem beide BCs aufwärts importieren. Zirkuläre Imports
sind damit strukturell unmöglich.

Laufzeit-Konvention: Caller erzeugen IDs via ``str(uuid.uuid4())``.
Dieses Modul stellt kein Factory-Callable bereit (YAGNI — bis ein Consumer
eine Factory braucht).
"""

from __future__ import annotations

from typing import NewType

# ---- Daemon-interne Concurrency-Identität --------------------------------
# TaskId identifiziert den anyio-Task, der als Single-Writer eines Aggregates agiert.
# Wird beim Nursery-Spawn gesetzt; wird von assert_owner() verglichen.
TaskId = NewType("TaskId", str)

# ---- Programmatic Executor BC -------------------------------------------
PageSessionId = NewType("PageSessionId", str)
InteractionFlowId = NewType("InteractionFlowId", str)
InteractionFlowStepId = NewType("InteractionFlowStepId", str)

# ---- Interactive Surface BC ----------------------------------------------
PointingSessionId = NewType("PointingSessionId", str)
PickId = NewType("PickId", str)
AnnotationId = NewType("AnnotationId", str)
