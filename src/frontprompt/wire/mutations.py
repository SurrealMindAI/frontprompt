"""Wire-Mutations — Tab→Daemon POST-Mutations (Channel 3, HTTP POST).

Zwei Mutation-Payloads mit discriminated-union über `type`-Literal-Field.
`MutationEnvelope` ist der äußere Container mit Empfangs-Metadaten.

`IdempotencyKey` NewType + `IDEMPOTENCY_TTL_NS` Konstante sind der
Anker für den Idempotency-Replay-Cache.

Naming-Konvention: alle ambiguosen Field-Namen mandatory-prefixed.
`AnnotationDraftSubmitted` trägt optionale dehydrated IDs
    für die ACL-Validierung im Interactive-Surface-BC.
"""

from __future__ import annotations

from typing import Annotated, Literal, NewType

from pydantic import BaseModel, ConfigDict, Field

from frontprompt.types import InteractionFlowStepId, PageSessionId, PointingSessionId

# ---- Neue NewTypes für Wire-Layer -----------------------------------------

IdempotencyKey = NewType("IdempotencyKey", str)
"""Opaque Idempotency-Key vom Tab — idempotency F-7 scope.

Wert: UUID4-String oder äquivalent, generiert vom Tab-Client.
Scope: (PointingSessionId, IdempotencyKey) — per-Session eindeutig.
Der Idempotency-Replay-Cache keyed auf (IdempotencyKey, PointingSessionId).
"""

#: TTL für den Idempotency-Replay-Cache in Nanosekunden — idempotency F-7 scope.
#: 300 Sekunden = 5 Minuten. Anker für DaemonClock.idempotency_ttl_expired().
IDEMPOTENCY_TTL_NS: int = 300 * 1_000_000_000


# ---- Payload-Models (2 Tab→Daemon Mutations) -------------------------------

_PAYLOAD_CONFIG = ConfigDict(extra="forbid", frozen=True)


class PickRequested(BaseModel):
    """Tab→Daemon: Tab fordert einen Pick-Vorgang vom Daemon an.

    Der Daemon startet daraufhin den interaktiven Pick-Prozess:
    eine neue Pick-Entity im PointingSession-Aggregate anlegen,
    DOM-Capture via Scrapling triggern.
    """

    model_config = _PAYLOAD_CONFIG

    type: Literal["pick_requested"]
    pointing_session_id: PointingSessionId
    """ULID der zugehörigen PointingSession (naming-konform)."""
    selector: str
    """CSS/XPath-Selector des angeklickten Elements. Darf nicht leer sein."""
    score: str
    """Scrapling-Confidence-Score als String (z.B. '0.95'). Kein float on wire."""
    idempotency_key: IdempotencyKey
    """Opaque Key vom Tab — idempotency F-7 scope. Replay-safe."""


class AnnotationDraftSubmitted(BaseModel):
    """Tab→Daemon: Tab reicht einen Annotations-Draft ein.

    Der Daemon validiert via ACL (ACL), persistiert die Annotation
    im PointingSession-Aggregate, und emittiert AnnotationPersisted.

    Optionale dehydrated IDs (dehydrated identifier fields):
    Alle None wenn der Tab keine Programmatic-Executor-Informationen hatte.
    """

    model_config = _PAYLOAD_CONFIG

    type: Literal["annotation_draft_submitted"]
    pointing_session_id: PointingSessionId
    """ULID der PointingSession, zu der die Annotation gehört (naming-konform)."""
    content: str
    """Annotations-Text. Darf nicht leer sein."""
    idempotency_key: IdempotencyKey
    """Opaque Key vom Tab — idempotency F-7 scope. Replay-safe."""

    # Dehydrated IDs — alle optional; None = 'nicht bekannt beim Tab'
    page_session_id: PageSessionId | None = None
    """Optionale ULID der PageSession im Programmatic-Executor-BC (naming-konform).
    None wenn der Tab zum Annotations-Zeitpunkt keine aktive PageSession hatte."""
    interaction_flow_step_id: InteractionFlowStepId | None = None
    """Optionale ULID des InteractionFlow-Steps (naming-konform).
    None wenn die Annotation nicht in einem Capture-Flow entstand."""
    dom_snapshot_hash: str | None = None
    """Optionaler DOM-Fingerprint zum Pick-Zeitpunkt (per-aggregate LSN scope).
    None wenn kein DOM-Snapshot verfügbar war."""


# ---- Discriminated-Union Alias ---------------------------------------------

MutationPayload = Annotated[
    PickRequested | AnnotationDraftSubmitted,
    Field(discriminator="type"),
]
"""Discriminated Union aller Mutation-Payload-Typen.

Pydantic wählt den konkreten Subtyp via `type`-Literal-Field.
"""


# ---- Äußerer Envelope (Empfangs-Metadaten + Payload) ----------------------


class MutationEnvelope(BaseModel):
    """Äußerer Container für alle Tab→Daemon Wire-Mutations (Channel 3).

    Enthält Empfangs-Metadaten (`schema_version`, `received_at_monotonic_ns`)
    plus den discriminated-union `payload`.

    Kein `daemon_id` hier — der Daemon empfängt die Mutation (er sendet sie
    nicht). `received_at_monotonic_ns` wird vom HTTP-Endpoint beim
    Deserialisieren gesetzt (Aufgabe des Endpoints, nicht des Envelope-Models).

    Wire-Deserialisierung: `MutationEnvelope.model_validate(raw_dict)`.
    """

    model_config = ConfigDict(extra="forbid", frozen=True)

    schema_version: Literal[1]
    """Wire-Protokoll-Version. Literal[1] — nur erhöhen bei breaking changes."""
    received_at_monotonic_ns: int
    """Monotonic-Timestamp des HTTP-Empfangs — gesetzt vom HTTP-Endpoint beim Deserialisieren.
    Nicht vom Tab geliefert (Anti-Tampering: Daemon bestimmt Empfangszeit)."""
    payload: MutationPayload
    """Discriminated-union Payload — Pydantic wählt Subtyp via `type`."""


__all__ = [
    "IDEMPOTENCY_TTL_NS",
    "AnnotationDraftSubmitted",
    "IdempotencyKey",
    "MutationEnvelope",
    "MutationPayload",
    "PickRequested",
]
