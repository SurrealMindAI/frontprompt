# Phase-2: Two-BC nursery code, dormant since the architecture reset (see ARCHITECTURE.md).
"""PointingSession — Aggregate Root der Interactive-Surface-BC.

Enthält Entities ``Pick`` und ``Annotation`` (Pick-Annotation-Aggregate, see ARCHITECTURE.md).

Pick-Invarianten (I-PA-1 bis I-PA-3) und Annotation-Validierung
über ACL (ProgrammaticReferenceValidator) kommen in späteren Bundles.
Dieser Sub-Plan liefert nur die strukturellen Skelette.
"""

from __future__ import annotations

from datetime import datetime
from typing import TYPE_CHECKING

from pydantic import BaseModel, ConfigDict, Field, PrivateAttr

from frontprompt.types import (
    AnnotationId,
    InteractionFlowStepId,
    PageSessionId,
    PickId,
    PointingSessionId,
    TaskId,
)

if TYPE_CHECKING:
    pass  # Platzhalter für künftige TYPE_CHECKING-Imports


class Pick(BaseModel):
    """Entity: ein einzelner DOM-Element-Pick innerhalb einer PointingSession.

    Konsistenz-Grenze liegt beim Eltern-Aggregat ``PointingSession``, nicht
    bei ``Pick`` selbst (Pick ist Entity, nicht Aggregate Root).
    Die ULID-Identity (``id``) ermöglicht globale Referenzierbarkeit im
    Audit-Log und über die Wire-API, ohne dass ``Pick`` eine eigene
    Nursery oder einen eigenen Single-Writer benötigt.
    """

    model_config = ConfigDict(frozen=False, arbitrary_types_allowed=False)

    id: PickId
    """ULID-Identity. Global eindeutig, aber konsistenz-grenzüberschreitend
    nur über die URL-Schema ``/pointing_sessions/{psid}/picks/{pid}``."""

    selector: str
    """CSS-Selector, der das geklickte DOM-Element identifiziert."""

    score: str
    """Konfidenz-/Relevanz-Score (opaker String in dieser Version;
    Semantik wird in späteren Bundles geschärft)."""

    timestamp: datetime
    """UTC-Zeitstempel der Pick-Erstellung. Display-only (daemon wall-clock)."""


class Annotation(BaseModel):
    """Entity: eine Benutzer-Annotation innerhalb einer PointingSession.

    Optionale Felder ``page_session_id``, ``interaction_flow_step_id`` und
    ``dom_snapshot_hash`` sind dehydrierte Identifier auf Programmatic-Executor-Daten.
    Sie werden zur Construction-Zeit durch ``ProgrammaticReferenceValidator``
    validiert — das ACL-Interface lebt im Nachbar-Modul dieses Packages.

    Diese Felder sind nach Construction unveränderlich (Annotation-Update ist
    kein Use-Case in v1). Mutierbarkeit ist technisch möglich (frozen=False),
    aber semantisch nicht vorgesehen.
    """

    model_config = ConfigDict(frozen=False, arbitrary_types_allowed=False)

    id: AnnotationId
    """ULID-Identity. Global eindeutig."""

    content: str
    """Freitext-Inhalt der Annotation."""

    # ---- Dehydrierte Cross-BC-Identifier (alle optional) -----------------
    page_session_id: PageSessionId | None = None
    """Auf welcher PageSession der Anker-Selector aufgenommen wurde.
    ``None`` wenn kein Programmatic-BC-Kontext vorliegt."""

    interaction_flow_step_id: InteractionFlowStepId | None = None
    """Schritt-Identity wenn die Annotation während eines aktiven Capture-
    Vorgangs entstand. ``None`` sonst."""

    dom_snapshot_hash: str | None = None
    """Struktureller DOM-Fingerprint zum Pick-Zeitpunkt (per-aggregate LSN analog).
    ``None`` wenn kein Snapshot vorhanden."""


class PointingSession(BaseModel):
    """Aggregate Root: eine interaktive Zeige-Session in der Interactive-Surface-BC.

    Besitzt geordnete Collections von ``Pick``-Entities und ``Annotation``-Entities.
    Single-Writer ist der Task der InteractiveSurfaceNursery.

    Lebenszyklus: ``open`` → ``closed`` (Zustände kommen in späteren Bundles).
    F-7-Discriminator-Scope für Idempotency-Key-Replay ist ``PointingSessionId``.
    """

    model_config = ConfigDict(frozen=False, arbitrary_types_allowed=False)

    id: PointingSessionId
    """Stabile ULID-Identity. Unveränderlich nach Konstruktion."""

    picks: list[Pick] = Field(default_factory=list)
    """Append-only Collection von Pick-Entities. Direkte Mutation nur durch
    den Single-Writer-Task (via assert_owner() in künftigen Mutations-Methoden)."""

    annotations: list[Annotation] = Field(default_factory=list)
    """Collection von Annotation-Entities. Direkte Mutation nur durch den
    Single-Writer-Task."""

    _owner_task_id: TaskId | None = PrivateAttr(default=None)
    """anyio-Task-ID des Single-Writers. Framework-intern — nicht serialisiert."""

    def assert_owner(self, current_task_id: TaskId) -> None:
        """Wirft ``PermissionError`` wenn ``current_task_id`` nicht der Owner ist.

        Jede Mutations-Methode (z.B. ``add_pick()``, ``add_annotation()``) MUSS
        ``self.assert_owner(current_task_id)`` als erste Zeile aufrufen.

        Raises:
            PermissionError: wenn Owner nicht gesetzt oder Mismatch.
        """
        if self._owner_task_id is None:
            raise PermissionError(f"PointingSession {self.id}: kein Owner-Task gesetzt")
        if self._owner_task_id != current_task_id:
            raise PermissionError(
                f"PointingSession {self.id}: Owner-Task-Mismatch — "
                f"erwartet {self._owner_task_id!r}, got {current_task_id!r}"
            )
