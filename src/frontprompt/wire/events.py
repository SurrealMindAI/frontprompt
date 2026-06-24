"""Wire-Events — Daemon→Tab Push-Events (Channel 2, WebSocket JSON-RPC).

Vier Event-Payloads mit discriminated-union über `type`-Literal-Field.
`EventEnvelope` ist der äußere Container mit Daemon-Metadaten.

Naming-Konvention: alle ambiguosen Field-Namen mandatory-prefixed:
    - `page_session_id` (nicht `session_id`)
    - `pointing_session_id` (nicht `session_id`)
    - `pick_id`, `annotation_id` (nicht bare `id`)
    - `daemon_id` (nicht bare `id`)
    - `dns_domain` (nicht bare `domain`)

Alle Models: ConfigDict(extra='forbid', frozen=True) per HARD CONSTRAINT
(Pydantic 2.13, discriminated-union-pattern).
"""

from __future__ import annotations

from typing import Annotated, Literal, NewType

from pydantic import BaseModel, ConfigDict, Field

from frontprompt.types import AnnotationId, PageSessionId, PickId, PointingSessionId

# ---- Neue NewTypes für Wire-Layer (noch nicht in types.py) ----------------

DaemonId = NewType("DaemonId", str)
"""Eindeutige Laufzeit-Identität des frontprompt-Daemon-Prozesses.

Wert: str(uuid.uuid4()) beim Daemon-Start. Über Wire: plain str.
Naming: bare 'id' ist verboten — Prefix 'daemon_' macht Ownership klar.
"""

MonotonicNs = NewType("MonotonicNs", int)
"""Monotonic-Clock-Wert in Nanosekunden — für Wire serialisiert als int.

Bedeutet: time.monotonic_ns() zum Zeitpunkt des Events. Niemals für
Wall-Clock-Anzeige nutzen (daemon wall-clock). Über Wire: plain int (JSON number).
"""


# ---- Payload-Models (4 Daemon→Tab Events) ---------------------------------

_PAYLOAD_CONFIG = ConfigDict(extra="forbid", frozen=True)


class SessionStarted(BaseModel):
    """Daemon→Tab: eine neue PageSession wurde im Daemon geöffnet.

    Wird emittiert wenn der Programmatic-Executor-BC eine neue PageSession
    initialisiert (z.B. durch MCP navigate-Tool oder Scrapling-Substrate-Boot).
    """

    model_config = _PAYLOAD_CONFIG

    type: Literal["session_started"]
    page_session_id: PageSessionId
    """ULID der neu geöffneten PageSession (naming-konform)."""
    dns_domain: str
    """DNS-Domain des initialen URL (naming — nicht bare 'domain').
    Beispiel: 'example.com'. Kein Schema, kein Pfad."""
    started_at_monotonic_ns: MonotonicNs
    """Monotonic-Timestamp zum Öffnungs-Zeitpunkt (monotonic clock, naming-konform)."""


class PageNavigated(BaseModel):
    """Daemon→Tab: die PageSession hat eine Navigation vollzogen.

    Emittiert nach jeder erfolgreichen Navigation (including forward/back).
    dom_snapshot_hash ermöglicht dem Frontend Stale-DOM-Detection.
    """

    model_config = _PAYLOAD_CONFIG

    type: Literal["page_navigated"]
    page_session_id: PageSessionId
    """ULID der navigierten PageSession (naming-konform)."""
    url: str
    """Ziel-URL nach der Navigation. Vollständiger URL-String."""
    dom_snapshot_hash: str
    """Struktureller DOM-Fingerprint nach der Navigation (per-aggregate LSN scope).
    Format: 'sha256:<hex>' oder äquivalent. Kein leeerer String."""
    navigated_at_monotonic_ns: MonotonicNs
    """Monotonic-Timestamp der Navigation (monotonic clock, naming-konform)."""


class PickAcknowledged(BaseModel):
    """Daemon→Tab: ein Pick wurde vom Interactive-Surface-BC akzeptiert.

    Der Daemon bestätigt dem Tab, dass der PickRequested-Mutation verarbeitet
    wurde und der Pick persistiert ist.
    """

    model_config = _PAYLOAD_CONFIG

    type: Literal["pick_acknowledged"]
    pick_id: PickId
    """ULID des persistierten Picks (naming-konform)."""
    pointing_session_id: PointingSessionId
    """ULID der zugehörigen PointingSession (naming-konform)."""
    acknowledged_at_monotonic_ns: MonotonicNs
    """Monotonic-Timestamp der Persistierung (monotonic clock, naming-konform)."""


class AnnotationPersisted(BaseModel):
    """Daemon→Tab: ein AnnotationDraft wurde vom Daemon persistiert.

    Der Daemon bestätigt dem Tab, dass der AnnotationDraftSubmitted-Mutation
    verarbeitet und die Annotation im PointingSession-Aggregate gespeichert ist.
    """

    model_config = _PAYLOAD_CONFIG

    type: Literal["annotation_persisted"]
    annotation_id: AnnotationId
    """ULID der persistierten Annotation (naming-konform)."""
    pointing_session_id: PointingSessionId
    """ULID der zugehörigen PointingSession (naming-konform)."""
    persisted_at_monotonic_ns: MonotonicNs
    """Monotonic-Timestamp der Persistierung (monotonic clock, naming-konform)."""


# ---- Discriminated-Union Alias ---------------------------------------------

EventPayload = Annotated[
    SessionStarted | PageNavigated | PickAcknowledged | AnnotationPersisted,
    Field(discriminator="type"),
]
"""Discriminated Union aller Payload-Typen.

Pydantic wählt den konkreten Subtyp via `type`-Literal-Field.
Neues Event hinzufügen: Union-Member ergänzen, fertig — Envelope bleibt stabil.
"""


# ---- Äußerer Envelope (Daemon-Metadaten + Payload) ------------------------


class EventEnvelope(BaseModel):
    """Äußerer Container für alle Daemon→Tab Wire-Events (Channel 2).

    Enthält Daemon-Metadaten (`daemon_id`, `schema_version`,
    `emitted_at_monotonic_ns`) plus den discriminated-union `payload`.

    Wire-Serialisierung: `model_dump(mode='json')` → JSON-RPC params-Objekt.
    Wire-Deserialisierung: `EventEnvelope.model_validate(raw_dict)`.
    """

    model_config = ConfigDict(extra="forbid", frozen=True)

    schema_version: Literal[1]
    """Wire-Protokoll-Version. Literal[1] — nur erhöhen bei breaking changes."""
    daemon_id: DaemonId
    """Laufzeit-Identität des sendenden Daemons (naming-konform)."""
    emitted_at_monotonic_ns: MonotonicNs
    """Monotonic-Timestamp des Emit-Zeitpunkts (monotonic clock, naming-konform)."""
    payload: EventPayload
    """Discriminated-union Payload — Pydantic wählt Subtyp via `type`."""


__all__ = [
    "AnnotationPersisted",
    "DaemonId",
    "EventEnvelope",
    "EventPayload",
    "MonotonicNs",
    "PageNavigated",
    "PickAcknowledged",
    "SessionStarted",
]
