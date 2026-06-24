"""Pydantic Wire-Schema (SSoT) für die Backend↔Overlay Bridge.

Dies ist die **einzige** Quelle von Wahrheit für Wire-Message-Shapes. Die
TypeScript-Zod-Schemas + Interfaces (``frontend/src/_generated/schemas.ts``)
werden via ``python -m frontprompt.build`` aus diesem Modul auto-generiert.
Hand-edits auf TS-Seite sind durch ``check-drift`` CI-Gate (Phase 2+) verboten.

Two-way bridge (see ARCHITECTURE.md): typed messages über ``expose_function`` + ``page.evaluate``.

Schema-Version
==============
Jede Envelope trägt ``schema_version: str`` — Breaking-Changes (Field
rename/remove, kind rename) erfordern Bump + Codegen-Re-Run. Forward-compatible
adds (neue *optional* Felder) ohne Bump zulässig.

Aktuell: ``0.7.0`` (+ origin_session on Pick/Region/Relation).
Vorherig: ``0.6.0`` (Region.rect page-absolute + Viewport-snapshot).
            ``0.2.0`` (Phase 1 + Inspector / Pick-Flow).
            ``0.1.0`` (Phase 1 panel-only Durchstich — siehe
:func:`~frontprompt.state.state.StateSnapshot` docstring für migration-history).

Discriminator
=============
Jede Envelope hat ``kind: Literal["..."]``. Pydantic's
``Field(discriminator="kind")`` routet O(1) zum konkreten Subtyp; ungültiges
oder fehlendes ``kind`` schlägt mit ``ValidationError`` fehl (caught im
:meth:`~frontprompt.bridge.manager.BridgeManager._on_overlay_send`).

Wire-Surface-Katalog
====================

OUTBOUND (Overlay → Python)
---------------------------

**Lifecycle**
    :class:`OverlayReady`              Overlay-mount signal (one-shot per page).
    :class:`HeartbeatAck`              Round-trip closure auf :class:`Heartbeat`.

**Panel-Mutations (existing, state-classification)**
    :class:`PanelToggleRequested`      Toggle open/closed eines panels.
    :class:`PanelResizeRequested`      Set panel-size am drag-end.
    :class:`HideAllPanelsRequested`    Bulk-hide/show aller panels.

**Inspector-Lifecycle (Phase 1)**
    :class:`InspectorActivateRequested`     Pick-mode an (toolbar-button).
    :class:`InspectorCanceledRequested`     Pick-mode aus (ESC / abort).
    :class:`InspectorPickMadeRequested`     Pick captured (atomic: append+select+deactivate).

**Pick-Mutations (Phase 1)**
    :class:`PickSelectedRequested`          Active-pick wechseln (right-panel display).
    :class:`PickCommentUpdatedRequested`    Pick.comment patchen.
    :class:`PickDeletedRequested`           Pick aus liste entfernen.

**Relation-Mutations (Schema 0.3.0+, hetero endpoints seit 0.4.0)**
    :class:`RelationCreatedRequested`       Neue gerichtete Edge zwischen zwei Nodes (Pick/Region).
    :class:`RelationDeletedRequested`       Edge aus liste entfernen.
    :class:`RelationUpdatedRequested`       Edge-kind + note atomar replacen.

**Region-Mutations (Schema 0.4.0)**
    :class:`RegionCreatedRequested`         Neue Region (rect + member-picks + note).
    :class:`RegionDeletedRequested`         Region aus liste entfernen.
    :class:`RegionUpdatedRequested`         Region-note patchen.
    :class:`RegionSelectedRequested`        Region als active_region_id setzen (für PickDetails).

INBOUND (Python → Overlay)
--------------------------

**Lifecycle**
    :class:`Heartbeat`                 Periodischer healthcheck.

**State-Broadcast**
    :class:`StateSnapshotMessage`      Authoritative state-snapshot nach jeder
                                       mutation + nach jedem ``OverlayReady``.

Per-Envelope Docstring-Konvention
=================================
Jeder Envelope-Docstring trägt:
    1. **User-Trigger** (was tut der User damit der Server diese Message sieht)
    2. **Server-Wirkung** (welche StateManager-Methode wird gerufen, was mutiert)
    3. **Optimistic-UI-Hinweis** wo relevant
    4. **Atomicity-Hinweis** wo mehrere Felder/Substores atomar mutieren
"""

from __future__ import annotations

from typing import Annotated, Literal

from pydantic import BaseModel, Field

# Wire/domain coupling — intentional, not a smell (see ARCHITECTURE.md):
# The imports of Pick, Region, and Relation from frontprompt.state.state are deliberate.
# The bridge design intends the payload to be the full Pick-Domain-Objekt.
# Wire shapes = domain shapes is an explicit Phase-1 design decision — it eliminates a
# translation layer that would add complexity without benefit at this stage.
# Phase-2 migration path: if the domain diverges from the wire contract (e.g. when
# Pick grows fields that should not be sent over the wire), introduce dedicated
# WirePick / WireRegion / WireRelation DTOs and map from domain here. Until then,
# do NOT add a translation layer — YAGNI.
from frontprompt.state.state import PanelId, Pick, Region, Relation, RelationKind, StateSnapshot

# ============================================================================
# Schema-Version — bumped on breaking changes (Field add/remove, kind rename)
# ============================================================================

SCHEMA_VERSION: str = "0.7.0"


# ============================================================================
# OUTBOUND: Overlay → Python
# ============================================================================

# ---------------------------------------------------------------------------
# Section A — Lifecycle (mount + heartbeat)
# ---------------------------------------------------------------------------


class OverlayReady(BaseModel):
    """Overlay-mount signal (one-shot per page-load).

    **User-Trigger**: passiert automatisch nachdem das Bundle gemounted hat.
    **Server-Wirkung**: :class:`~frontprompt.bridge.manager.BridgeManager`
    setzt ``_ready_event``, broadcasten einen frischen :class:`StateSnapshotMessage`
    für re-hydration (cross-origin nav-recovery).
    """

    kind: Literal["overlay_ready"] = "overlay_ready"
    schema_version: str = SCHEMA_VERSION
    bundle_build_session: str = Field(
        description="FRONTPROMPT_BUILD_SESSION-UUID des installed bundles — "
        "Python cross-checked gegen den eigenen build-manifest um drift "
        "(stale bundle vs server-binary) zu detektieren."
    )


class HeartbeatAck(BaseModel):
    """Overlay-Antwort auf einen inbound :class:`Heartbeat`.

    **User-Trigger**: keiner — automatisches roundtrip-closure.
    **Server-Wirkung**: Latenz-messung via ``server_send_time_ns`` Korrelation.
    """

    kind: Literal["heartbeat_ack"] = "heartbeat_ack"
    schema_version: str = SCHEMA_VERSION
    heartbeat_seq: int = Field(description="Echoed seq aus dem Heartbeat.")
    client_recv_time_ms: float = Field(description="``Date.now()`` zum Zeitpunkt des heartbeat-receipts im Overlay.")


# ---------------------------------------------------------------------------
# Section B — Panel-Mutations (state-classification)
# ---------------------------------------------------------------------------


class PanelToggleRequested(BaseModel):
    """User clickte den panel-tab — toggle open/closed.

    **User-Trigger**: Click auf :svelte:`PanelTab`.
    **Server-Wirkung**: :meth:`~frontprompt.state.StateManager.toggle_panel`
    flippt ``panel_state.panels[id].open`` + broadcast snapshot.
    **Optimistic-UI**: overlay updated lokales mirror sofort beim click;
    StateSnapshot-broadcast reconciles falls divergent.
    """

    kind: Literal["panel_toggle_requested"] = "panel_toggle_requested"
    schema_version: str = SCHEMA_VERSION
    panel_id: PanelId = Field(description="Welcher panel toggled wird (top/bottom/left/right).")


class PanelResizeRequested(BaseModel):
    """User finished resize-drag — set neue panel-size.

    **User-Trigger**: pointerup nach drag auf :svelte:`PanelResizer`.
    **Server-Wirkung**: :meth:`~frontprompt.state.StateManager.resize_panel`
    clampt zu [min,max] + setzt ``panel_state.panels[id].size``.

    *Wire-economy*: NUR am drag-end gesendet, nicht pro pointermove — sonst
    überschwemmt der wire bei jedem px-step.
    """

    kind: Literal["panel_resize_requested"] = "panel_resize_requested"
    schema_version: str = SCHEMA_VERSION
    panel_id: PanelId = Field(description="Welcher panel resized wurde.")
    new_size: int = Field(description="Neue size in px. Backend clamped zu [min, max] pro panel.")


class HideAllPanelsRequested(BaseModel):
    """User clickte hide-all/show-all toolbar-button — bulk-toggle.

    **User-Trigger**: Click auf den toolbar-button im top-panel.
    **Server-Wirkung**: :meth:`~frontprompt.state.StateManager.set_all_panels_open`
    setzt alle 4 panels.open auf ``target_open``.
    """

    kind: Literal["hide_all_panels_requested"] = "hide_all_panels_requested"
    schema_version: str = SCHEMA_VERSION
    target_open: bool = Field(description="True = 'show all' (alle open), False = 'hide all' (alle collapsed).")


# ---------------------------------------------------------------------------
# Section C — Inspector-Lifecycle (Phase 1)
# ---------------------------------------------------------------------------


class InspectorActivateRequested(BaseModel):
    """User clickte Inspector-Toggle (off → on) — Pick-mode an.

    **User-Trigger**: Click auf "inspect"-button in :svelte:`LeftPanelTools`.
    **Server-Wirkung**: ``inspector_state.active = True``.
    **UI-Folge**: panels retracten via derived cross-store
    (:meth:`PanelState.effectiveOpenWith` liest ``inspector.active``);
    :svelte:`InspectorLayer` mountet als sibling-Komponente.

    Payload: keine — singleton-action.
    """

    kind: Literal["inspector_activate_requested"] = "inspector_activate_requested"
    schema_version: str = SCHEMA_VERSION


class InspectorCanceledRequested(BaseModel):
    """User cancelled inspector ohne Pick — Pick-mode aus.

    **User-Trigger**: ESC während InspectorLayer aktiv, oder click auf nicht-
    pickbarem Hintergrund.
    **Server-Wirkung**: ``inspector_state.active = False``. Picks-Liste
    unverändert (kein Pick wurde captured).
    **UI-Folge**: panels kommen via derived cross-store automatisch in den
    Original-Zustand zurück (panel.open untouched).
    """

    kind: Literal["inspector_canceled_requested"] = "inspector_canceled_requested"
    schema_version: str = SCHEMA_VERSION


class InspectorPickMadeRequested(BaseModel):
    """User clickte DOM-Element im Inspector-Mode — Pick captured.

    **User-Trigger**: pointerdown auf ein pickbares Element im
    :svelte:`InspectorLayer`. Client baut den Pick lokal (uuid4 ``pick.pick_id``,
    ``element.selector`` + ``element.fingerprint`` via element-locator service).
    **Server-Wirkung**: :meth:`~frontprompt.state.StateManager.add_pick(msg.pick)` —
    **atomar**: ``picks.append(pick)`` + ``active_pick_id = pick.pick_id``
    + ``inspector.active = False``. EINE snapshot-broadcast, kein
    Zwischenzustand sichtbar.
    **Idempotency**: re-send mit identischer ``pick.pick_id`` ersetzt den existing
    pick (last-write-wins) — schützt vor double-click-races.

    *Design note*: payload ist das volle :class:`Pick`-Domain-Objekt, NICHT dezomponierte
    Felder. So bleibt das Wire-Schema zu jeder Pick-Erweiterung (z.B. Tags, Labels)
    forward-kompatibel ohne Envelope-Bump.
    """

    kind: Literal["inspector_pick_made_requested"] = "inspector_pick_made_requested"
    schema_version: str = SCHEMA_VERSION
    pick: Pick = Field(
        description="Volles :class:`Pick`-Domain-Objekt — client-generated mit uuid4 ``pick_id``, "
        "captured ``url``/``timestamp_ms``, Scrapling-equivalent ``element.fingerprint``, "
        '``element.selector`` (Firefox-style), und ``comment`` (initial ``""``).'
    )


# ---------------------------------------------------------------------------
# Section D — Pick-Mutations (Phase 1)
# ---------------------------------------------------------------------------


class PickSelectedRequested(BaseModel):
    """User clickte einen Pick in der Liste — wechsel active-pick.

    **User-Trigger**: Click auf :svelte:`PickItem` in :svelte:`PicksTab`.
    **Server-Wirkung**: :meth:`~frontprompt.state.StateManager.select_pick`
    setzt ``inspector_state.active_pick_id = pick_id``. Wenn ``pick_id``
    unbekannt: no-op (idempotente rehydrate-broadcast trotzdem).
    **UI-Folge**: :svelte:`RightPanel` rendert PickDetails + CommentEditor
    für den neu selektierten Pick.
    """

    kind: Literal["pick_selected_requested"] = "pick_selected_requested"
    schema_version: str = SCHEMA_VERSION
    pick_id: str = Field(description="``pick_id`` des zu selektierenden Picks.")


class PickCommentUpdatedRequested(BaseModel):
    """User clickte Save im CommentEditor — neuer Kommentar persistieren.

    **User-Trigger**: Click auf 'Speichern'-button in :svelte:`CommentEditor`
    nachdem ``dirty=true`` ist.
    **Server-Wirkung**: :meth:`~frontprompt.state.StateManager.update_pick_comment`
    patcht ``Pick.comment`` in-place. Wenn ``pick_id`` unbekannt: no-op
    (idempotente rehydrate trotzdem).
    """

    kind: Literal["pick_comment_updated_requested"] = "pick_comment_updated_requested"
    schema_version: str = SCHEMA_VERSION
    pick_id: str = Field(description="``pick_id`` des zu patchenden Picks.")
    comment: str = Field(description="Neuer Kommentar-Text. Leer-String ist gültig (= Kommentar entfernen).")


class PickDeletedRequested(BaseModel):
    """User clickte Delete bei einem Pick — entfernen aus Liste.

    **User-Trigger**: Click auf den x-button in :svelte:`PickItem`.
    **Server-Wirkung**: :meth:`~frontprompt.state.StateManager.delete_pick`
    entfernt den Pick. Wenn er der ``active_pick_id`` war, wird der auf
    ``None`` gesetzt. **Cascade**: alle Relations mit dem Pick als source ODER
    target werden in derselben atomaren Mutation entfernt. Wenn ``pick_id``
    unbekannt: no-op.
    """

    kind: Literal["pick_deleted_requested"] = "pick_deleted_requested"
    schema_version: str = SCHEMA_VERSION
    pick_id: str = Field(description="``pick_id`` des zu löschenden Picks.")


# ---------------------------------------------------------------------------
# Section E — Relation-Mutations (Phase 1, Schema 0.3.0)
# ---------------------------------------------------------------------------


class RelationCreatedRequested(BaseModel):
    """User finished die Creation-UI im :svelte:`RelationsTab` — Edge persistieren.

    **User-Trigger**: Click auf "Create" im :svelte:`RelationsTab` nachdem
    Source- + Target-PickItem via DnD gefüllt + kind gewählt wurden.
    **Server-Wirkung**: :meth:`~frontprompt.state.StateManager.add_relation` —
    last-write-wins by ``relation.relation_id``. Validates beide endpoints
    existieren in der Picks-Liste; sonst silent reject + warning-log.
    **Atomicity**: eine snapshot pro mutation (single-writer).

    *Design note*: payload ist das volle :class:`Relation`-Domain-Objekt
    (analog zu :class:`InspectorPickMadeRequested`). Forward-kompatibel zu
    späteren Feld-Erweiterungen (Phase 2 metadata-dict) ohne Envelope-Bump.
    """

    kind: Literal["relation_created_requested"] = "relation_created_requested"
    schema_version: str = SCHEMA_VERSION
    relation: Relation = Field(
        description="Volles :class:`Relation`-Domain-Objekt — client-generated mit uuid4 "
        "``relation_id``, ``source_pick_id``/``target_pick_id`` (existing pick_ids), "
        "``kind`` (Phase-1: relates_to/triggers/part_of) und optional ``note``."
    )


class RelationDeletedRequested(BaseModel):
    """User clickte Delete bei einer Relation — entfernen aus Liste.

    **User-Trigger**: Click auf den x-button in :svelte:`RelationItem` ODER
    auf den delete-button neben einer Relation in :svelte:`PickDetails`.
    **Server-Wirkung**: :meth:`~frontprompt.state.StateManager.delete_relation`
    entfernt die Relation. No-op + idempotente rehydrate-broadcast wenn id
    unbekannt.
    """

    kind: Literal["relation_deleted_requested"] = "relation_deleted_requested"
    schema_version: str = SCHEMA_VERSION
    relation_id: str = Field(description="``relation_id`` der zu löschenden Relation.")


class RelationUpdatedRequested(BaseModel):
    """User editierte kind und/oder note einer existing Relation.

    **User-Trigger**: Click auf "Save" im inline-edit-popover des
    :svelte:`RelationItem`.
    **Server-Wirkung**: :meth:`~frontprompt.state.StateManager.update_relation`
    replacet ``kind`` und ``note`` atomar. Beide Felder sind pflicht im Payload
    — auch wenn nur eines geändert wurde, sendet das Frontend immer den
    aktuellen Snapshot beider. Vermeidet partial-update-races.

    *Naming-note*: ``relation_kind`` (nicht ``kind``) um Kollision mit dem
    discriminator-Feld ``kind`` zu vermeiden.
    """

    kind: Literal["relation_updated_requested"] = "relation_updated_requested"
    schema_version: str = SCHEMA_VERSION
    relation_id: str = Field(description="``relation_id`` der zu patchenden Relation.")
    relation_kind: RelationKind = Field(description="Neuer kind (relates_to/triggers/part_of).")
    note: str | None = Field(description="Neuer note (None = note entfernen).")


# ---------------------------------------------------------------------------
# Section F — Region-Mutations (Phase 2, Schema 0.4.0)
# ---------------------------------------------------------------------------


class RegionCreatedRequested(BaseModel):
    """User finished die Region-draw — Region persistieren.

    **User-Trigger**: pointerup nach drag-rect auf der page im Region-Mode.
    Client baut die Region lokal (uuid4 ``region_id``, ``rect`` aus drag-bounds,
    ``member_pick_ids`` aus DOM-elements-im-rect via fingerprint-dedupe/-create).
    **Server-Wirkung**: :meth:`~frontprompt.state.StateManager.add_region` —
    last-write-wins by ``region.region_id``. Filtert unknown members.
    Setzt active_region_id (clears active_pick_id, mutually exclusive).

    *Design note*: payload ist das volle :class:`Region`-Domain-Objekt — analog
    zu Pick/Relation. Forward-kompatibel zu Phase-2-Feldern (z.B. shape-polygon
    statt rect) ohne Envelope-Bump.
    """

    kind: Literal["region_created_requested"] = "region_created_requested"
    schema_version: str = SCHEMA_VERSION
    region: Region = Field(
        description="Volles :class:`Region`-Domain-Objekt — client-generated mit uuid4 "
        "``region_id``, ``rect`` (bounding-box auf page), ``member_pick_ids`` "
        "(picks innerhalb des rect, mit fingerprint-dedupe), und optional ``note``."
    )


class RegionDeletedRequested(BaseModel):
    """User clickte Delete bei einer Region.

    **Server-Wirkung**: :meth:`~frontprompt.state.StateManager.delete_region`
    entfernt Region. **Cascade**: alle Relations mit der Region als
    source/target werden mitgelöscht. Picks die in member_pick_ids waren
    bleiben — Region ist Container, kein owner. No-op + idempotente
    rehydrate wenn id unbekannt.
    """

    kind: Literal["region_deleted_requested"] = "region_deleted_requested"
    schema_version: str = SCHEMA_VERSION
    region_id: str = Field(description="``region_id`` der zu löschenden Region.")


class RegionUpdatedRequested(BaseModel):
    """User editierte die note einer existing Region.

    Phase 2-of-Region (Phase 1 of feature): nur ``note`` patchbar. Rect bleibt
    immutable (Region-rect ändern würde Member-recomputation triggern — separate
    feature ggf. später).
    """

    kind: Literal["region_updated_requested"] = "region_updated_requested"
    schema_version: str = SCHEMA_VERSION
    region_id: str = Field(description="``region_id`` der zu patchenden Region.")
    note: str | None = Field(description="Neuer note (None = note entfernen).")


class RegionSelectedRequested(BaseModel):
    """User clickte eine Region in der Liste — wechsel active-region.

    **Server-Wirkung**: :meth:`~frontprompt.state.StateManager.select_region`
    setzt ``inspector_state.active_region_id = region_id`` UND clears
    ``active_pick_id`` (mutually exclusive — right-panel zeigt entweder pick
    ODER region, nicht beides).
    """

    kind: Literal["region_selected_requested"] = "region_selected_requested"
    schema_version: str = SCHEMA_VERSION
    region_id: str = Field(description="``region_id`` der zu selektierenden Region.")


# ---------------------------------------------------------------------------
# Discriminated Union — Outbound
# ---------------------------------------------------------------------------

OutboundMessage = Annotated[
    OverlayReady
    | HeartbeatAck
    | PanelToggleRequested
    | PanelResizeRequested
    | HideAllPanelsRequested
    | InspectorActivateRequested
    | InspectorCanceledRequested
    | InspectorPickMadeRequested
    | PickSelectedRequested
    | PickCommentUpdatedRequested
    | PickDeletedRequested
    | RelationCreatedRequested
    | RelationDeletedRequested
    | RelationUpdatedRequested
    | RegionCreatedRequested
    | RegionDeletedRequested
    | RegionUpdatedRequested
    | RegionSelectedRequested,
    Field(discriminator="kind"),
]
"""Discriminated union aller Overlay → Python messages. Pydantic routet via ``kind``.

Wenn du eine neue Outbound-Envelope hinzufügst:
    1. Klasse hier definieren (mit ``Literal[...]``-kind + docstring-convention)
    2. In dieser Union als variant aufnehmen
    3. In :data:`__codegen_roots__` aufnehmen (sonst kein TS-Type)
    4. In :data:`__all__` aufnehmen (sonst kein re-export)
    5. Handler in :func:`~frontprompt.cli._show_async_main` registrieren
       (``bridge.on(NewEnvelope, _on_new_handler)``)
    6. :func:`~tests.bridge.test_outbound_collection_complete` muss grün bleiben
"""


# ============================================================================
# INBOUND: Python → Overlay
# ============================================================================

# ---------------------------------------------------------------------------
# Section E — Inbound (Lifecycle + State-Broadcast)
# ---------------------------------------------------------------------------


class Heartbeat(BaseModel):
    """Periodischer healthcheck — Python sendet, Overlay antwortet mit Ack.

    **Trigger**: ``_heartbeat_sender`` task in :func:`~frontprompt.cli._show_async_main`
    sendet alle 5s. Overlay antwortet mit :class:`HeartbeatAck`.
    """

    kind: Literal["heartbeat"] = "heartbeat"
    schema_version: str = SCHEMA_VERSION
    seq: int = Field(description="Monotonic counter — overlay echoed im Ack.")
    server_send_time_ns: int = Field(
        description="``time.monotonic_ns()`` zum Zeitpunkt des sends. Korrelations-key "
        "für Latenz-messung beim Ack-receipt."
    )


class StateSnapshotMessage(BaseModel):
    """Wire-wrapper für :class:`~frontprompt.state.state.StateSnapshot`.

    **Trigger**: gesendet nach JEDEM :class:`OverlayReady`-receive (cross-origin
    re-hydration) UND nach jeder authoritative mutation (snapshot-listener
    in StateManager → broadcast). Eine snapshot pro mutation, keine
    Zwischenzustände (atomarity-garantie der StateManager-methoden).
    """

    kind: Literal["state_snapshot"] = "state_snapshot"
    schema_version: str = SCHEMA_VERSION
    snapshot: StateSnapshot = Field(
        description="Voller authoritative state snapshot (panel + inspector + zukünftig mehr)."
    )
    integrity_token: str | None = Field(
        default=None,
        description=(
            "32-byte hex string generated once at Python startup via secrets.token_hex(32). "
            "Delivered to the overlay during setupBridge() initialisation via the initial "
            "getState() seed (pre-mount hydration path). The TS dispatcher validates this "
            "field before accepting any state_snapshot envelope — a mismatch emits an "
            "integrity_token_mismatch error event and the snapshot is discarded. "
            "None means the session was started without token enforcement "
            "(backward-compat / test harness)."
        ),
    )


# ---------------------------------------------------------------------------
# Discriminated Union — Inbound
# ---------------------------------------------------------------------------

InboundMessage = Annotated[
    Heartbeat | StateSnapshotMessage,
    Field(discriminator="kind"),
]
"""Discriminated union aller Python → Overlay messages."""


# ============================================================================
# Codegen roots — was nach TS emittiert wird (pydantic-zod-codegen scope)
# ============================================================================
#
# Discoverer liest diese Liste statt das Modul zu scannen — gibt uns
# Kontrolle was als top-level TS-Type generiert wird. Variants (z.B. OverlayReady
# für sich) bleiben implizit verfügbar via die unions.

__codegen_roots__ = [
    # Outbound — Lifecycle
    "OverlayReady",
    "HeartbeatAck",
    # Outbound — Panel
    "PanelToggleRequested",
    "PanelResizeRequested",
    "HideAllPanelsRequested",
    # Outbound — Inspector-Lifecycle
    "InspectorActivateRequested",
    "InspectorCanceledRequested",
    "InspectorPickMadeRequested",
    # Outbound — Pick-Mutations
    "PickSelectedRequested",
    "PickCommentUpdatedRequested",
    "PickDeletedRequested",
    # Outbound — Relation-Mutations
    "RelationCreatedRequested",
    "RelationDeletedRequested",
    "RelationUpdatedRequested",
    # Outbound — Region-Mutations (Schema 0.4.0)
    "RegionCreatedRequested",
    "RegionDeletedRequested",
    "RegionUpdatedRequested",
    "RegionSelectedRequested",
    # Inbound
    "Heartbeat",
    "StateSnapshotMessage",
]


__all__ = [  # noqa: RUF022 — topical grouping (Lifecycle / Panel / Inspector / Pick / Relation / Region / Inbound / Unions) is intentional and load-bearing for developer orientation
    "SCHEMA_VERSION",
    # Outbound — Lifecycle
    "OverlayReady",
    "HeartbeatAck",
    # Outbound — Panel
    "PanelToggleRequested",
    "PanelResizeRequested",
    "HideAllPanelsRequested",
    # Outbound — Inspector-Lifecycle
    "InspectorActivateRequested",
    "InspectorCanceledRequested",
    "InspectorPickMadeRequested",
    # Outbound — Pick-Mutations
    "PickSelectedRequested",
    "PickCommentUpdatedRequested",
    "PickDeletedRequested",
    # Outbound — Relation-Mutations
    "RelationCreatedRequested",
    "RelationDeletedRequested",
    "RelationUpdatedRequested",
    # Outbound — Region-Mutations (Schema 0.4.0)
    "RegionCreatedRequested",
    "RegionDeletedRequested",
    "RegionUpdatedRequested",
    "RegionSelectedRequested",
    # Inbound
    "Heartbeat",
    "StateSnapshotMessage",
    # Unions
    "OutboundMessage",
    "InboundMessage",
]
