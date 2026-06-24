"""Pydantic state-models — SSoT für backendState.

State classification. Phase 1: panel state + inspector state (picks). Phase 2+: annotations
beyond comment, page-history, preferences, disk persistence.

Models hier landen via :mod:`frontprompt.bridge.codegen` als Zod-schemas in
``frontend/src/_generated/state.ts`` (codegen-roots-discovery).

NICHT in :mod:`frontprompt.bridge.messages` — das modul ist für wire-frames,
hier sind die state-shapes selbst.
"""

from __future__ import annotations

from typing import Literal, get_args
from urllib.parse import urlsplit

from pydantic import BaseModel, ConfigDict, Field, model_validator

# ----------------------------------------------------------------------------
# Phase-1 snapshot-size constants
# Bound the two unbounded free-text fields so per-pick/per-region payload stays
# manageable. 50 picks x 1 000 chars = 50 KB -- practical worst-case that keeps
# the snapshot under 100 KB even with fingerprint payloads.
# Phase-2: replace full-snapshot broadcast with delta/patch protocol via a WebSocket+JSON-RPC client library.
# ----------------------------------------------------------------------------

PICK_COMMENT_MAX_LENGTH: int = 1000
"""Maximum byte-length for Pick.comment (Phase-1 mitigation)."""

REGION_NOTE_MAX_LENGTH: int = 1000
"""Maximum byte-length for Region.note (Phase-1 mitigation)."""


# ----------------------------------------------------------------------------
# Panel-State (Phase 1)
# ----------------------------------------------------------------------------

PanelId = Literal["top", "bottom", "left", "right"]
"""Discriminator für panel-state. Naming-konform (volle term-namen)."""

PANEL_IDS: tuple[PanelId, ...] = get_args(PanelId)
"""Tuple aller PanelIds — für iteration in StateManager."""


class PanelView(BaseModel):
    """View eines einzelnen panels (open/collapsed + size).

    ``size`` ist die user-set width (für left/right) oder height (für top/bottom)
    in px. Wenn ``open=False`` rendert die UI mit tab-thickness statt size.
    """

    model_config = ConfigDict(frozen=False)  # mutable für StateManager mutations

    open: bool = Field(description="Ob panel expanded ist (sonst collapsed zur lasche).")
    size: int = Field(description="User-set size in px (width für h-axis, height für v-axis).")


class PanelStateView(BaseModel):
    """View aller panels für die overlay-side mirror.

    Felder sind alle 4 panels einzeln (statt dict[PanelId, PanelView]) damit
    Pydantic JSON-schema + Zod-codegen klare typing produziert.
    """

    model_config = ConfigDict(frozen=False)

    top: PanelView
    bottom: PanelView
    left: PanelView
    right: PanelView


# ----------------------------------------------------------------------------
# Inspector-State (Phase 1) — Pick-Flow domain
# ----------------------------------------------------------------------------


class ElementRect(BaseModel):
    """Rect in viewport-Koordinaten zum Pick-Zeitpunkt.

    Float damit Browser-getBoundingClientRect() lossless round-trippen kann
    (Sub-pixel-Werte bei zoomed displays oder transforms).
    """

    model_config = ConfigDict(frozen=False)

    x: float
    y: float
    width: float
    height: float


class ElementFingerprint(BaseModel):
    """Multi-faktorieller Element-Fingerprint — Scrapling-equivalent.

    Mirror von Scrapling's ``_StorageTools.element_to_dict`` shape
    (scrapling/core/utils/_utils.py:element_to_dict). **Field-Namen sind
    1:1 mit Scrapling** damit ``Selector.relocate(fp.model_dump())`` direkt
    funktioniert — verifiziert durch :file:`tests/scrapling/test_fingerprint_compatibility.py`.

    Phase 1: nur gespeichert, nicht genutzt.
    Phase 2: an Scrapling's ``Selector.relocate(fingerprint_dict, percentage=)``
    für adaptive Re-Location nach DOM-Drift / cross-origin-nav übergeben.

    Speicher-Kosten: ~1-2 KB pro Pick (text + parent_text auf 500 chars trunkiert
    client-side). Vernachlässigbar gegen den Wert: Phase-2 ohne Datenmodell-Refactor.

    Naming notes (matched to Scrapling):
        - ``parent_name`` (NICHT parent_tag) — siehe element_to_dict line 95
        - ``parent_attribs`` (NICHT parent_attributes) — line 96
        - ``siblings`` EXKLUDIERT das Element selbst (Scrapling: ``if child != element``)
    """

    model_config = ConfigDict(frozen=False)

    tag: str = Field(description="Lowercase tag-name (z.B. 'div').")
    attributes: dict[str, str] = Field(
        default_factory=dict,
        description="Volle attribs-map (id, class, data-*, aria-*, role, ...).",
    )
    text: str = Field(default="", description="textContent, client-truncated 500 chars.")
    path: list[str] = Field(
        default_factory=list,
        description="Tag-sequence root→element (z.B. ['html', 'body', 'main', 'div']).",
    )
    parent_name: str | None = Field(
        default=None,
        description="Parent tag lowercase, None für orphans. (Scrapling-Name: ``parent_name``.)",
    )
    parent_attribs: dict[str, str] = Field(
        default_factory=dict,
        description="Parent attributes. (Scrapling-Name: ``parent_attribs``.)",
    )
    parent_text: str = Field(default="", description="Parent textContent, client-truncated 500 chars.")
    siblings: list[str] = Field(
        default_factory=list,
        description="Tag-sequence der GESCHWISTER (das Element selbst EXKLUDIERT, Scrapling-Konvention).",
    )
    children: list[str] = Field(
        default_factory=list,
        description="Tag-sequence der direct children (in DOM-order).",
    )


class PickElement(BaseModel):
    """Snapshot des angeklickten DOM-Elements.

    ``selector`` ist human-readable (für list-display, debug, Phase-2-relocate-fallback).
    ``fingerprint`` ist der Scrapling-equivalent struct für adaptive Re-Location.
    ``text_snippet`` ist die UI-friendly Vorschau (max 120 chars).
    ``rect`` ist boundingClientRect zum Click-Zeitpunkt.
    """

    model_config = ConfigDict(frozen=False)

    selector: str = Field(description="CSS-selector — Firefox-style id-first → :nth-of-type chain.")
    fingerprint: ElementFingerprint = Field(description="Scrapling-equivalent multi-factor fingerprint.")
    text_snippet: str = Field(
        default="",
        description="UI-friendly preview, max 120 chars (frontend-trunkiert).",
    )
    rect: ElementRect = Field(description="boundingClientRect zum Pick-Zeitpunkt.")


class Pick(BaseModel):
    """Ein einzelner Pick — durable Eintrag in der Session-Liste.

    ``pick_id`` ist client-generated uuid4 — kein server-roundtrip nötig für
    optimistic UI. ``timestamp_ms`` ist client-clock (epoch ms) — für UI-sort.
    ``color_index`` ist ein Handle in die 32-Farben-Palette des overlays
    (Schema 0.5.0+) — jeder Pick kriegt seine eindeutige Farbe für die
    rect-border auf der Page + den Color-dot in der Liste.
    """

    model_config = ConfigDict(frozen=False)

    pick_id: str = Field(description="Client-generated uuid4.")
    url: str = Field(
        description=(
            "window.location.href zum Pick-Zeitpunkt. Unsanitised — originates from the "
            "browser's location API. TODO(Phase-2 web UI): must be HTML-escaped before "
            "rendering in any server-generated HTML surface. Safe in Phase-1 (local CLI + "
            "expose_function only)."
        ),
    )
    timestamp_ms: int = Field(description="Client-clock epoch ms.")
    element: PickElement
    comment: str = Field(
        default="",
        max_length=PICK_COMMENT_MAX_LENGTH,
        description="User-comment, initially empty.",
    )
    color_index: int = Field(
        default=0,
        ge=0,
        description=(
            "Index in der 32-Farben overlay-Palette (Schema 0.5.0+). "
            "Client assigned beim Erstellen via ``nextColorIndex(picks.length)``. "
            "Falls fehlt (alte snapshots), default 0."
        ),
    )
    origin_session: str | None = Field(
        default=None,
        description=(
            "session_id of the session that last mutated this entity "
            "(steal-on-mutate provenance via sqlite-persistence). "
            "None until first persisted."
        ),
    )


class Viewport(BaseModel):
    """Snapshot von Page-scroll + viewport- + document-Dimensionen zum
    Zeitpunkt einer rect-Aufnahme.

    Schema 0.6.0+ — wird mit :class:`Region.viewport_snapshot` mitgespeichert,
    damit page-absolute coords im :class:`Region.rect` reproducible bleiben:

    - **screenshot-extraction**: ``document_w`` / ``document_h`` reicht aus,
      um zu wissen "wie groß war die canvas damals" (für Skalierungs-detection
      bei page-resize seit draw-time).
    - **layout-drift detection** (Phase 2): wenn current document_w deutlich
      von ``viewport_snapshot.document_w`` abweicht → warne dass die Region
      eventuell nicht mehr am ursprünglichen content liegt.

    Alle Werte: float (Sub-pixel-Werte bei zoomed displays oder transforms).
    """

    model_config = ConfigDict(frozen=False)

    scroll_x: float = Field(description="window.scrollX")
    scroll_y: float = Field(description="window.scrollY")
    viewport_w: float = Field(description="window.innerWidth")
    viewport_h: float = Field(description="window.innerHeight")
    document_w: float = Field(description="document.documentElement.scrollWidth")
    document_h: float = Field(description="document.documentElement.scrollHeight")


class Region(BaseModel):
    """Eine räumliche Region auf der Page — Container über Picks.

    User zieht eine bounding-box auf der Page; alle DOM-elements innerhalb des
    rect werden automatisch zu Picks (mit fingerprint-dedupe gegen existing).
    Diese pick_ids landen in ``member_pick_ids``. Region selbst hat ``rect``
    (drawn bounding-box) + optional ``note``.

    Region ist ein **First-class node** im Relation-Graph: Relations können
    pick↔pick, pick↔region, region↔pick, oder region↔region sein (siehe
    :class:`Relation.source_kind` / :class:`Relation.target_kind`).

    **Coordinate-system (Schema 0.6.0+)**: ``rect`` ist in **PAGE-absoluten
    Koordinaten** (``window.scrollX + clientX``, etc.) statt viewport-relativ.
    Begründung: das overlay-rendering kann via member-pick live-bbox
    semantically anchored werden (folgt reflow), aber wenn das mal fehlschlägt
    (cross-origin, alle members weg), liefert ``rect - currentScroll`` immer
    noch den ursprünglich gezeichneten viewport-position. Screenshot-API
    (zukünftig via Playwright ``page.screenshot({clip: rect})``) braucht ohnehin
    page-Koordinaten — page-absolute storage ist direkt usable.

    Schema-history:
        - 0.4.0: Region als first-class entity (rect viewport-relativ)
        - 0.5.0: + color_index
        - 0.6.0: rect semantisch zu page-absolute migriert + viewport_snapshot
    """

    model_config = ConfigDict(frozen=False)

    region_id: str = Field(description="Client-generated uuid4.")
    rect: ElementRect = Field(
        description=(
            "Bounding-box auf der page in **page-absoluten Koordinaten** "
            "(``window.scrollX + clientX``, Schema 0.6.0+). Drawn-rect-snapshot, "
            "immutable. Render-overlay konsultiert primär member-pick live-bbox; "
            "fallback ist ``rect - currentScroll``."
        ),
    )
    member_pick_ids: list[str] = Field(
        default_factory=list,
        description="Pick-IDs die innerhalb des rect liegen (auto-collected beim region-draw).",
    )
    note: str | None = Field(
        default=None,
        max_length=REGION_NOTE_MAX_LENGTH,
        description="Optional user-text.",
    )
    timestamp_ms: int = Field(description="Client-clock epoch ms zum Erstellungszeitpunkt.")
    color_index: int = Field(
        default=0,
        ge=0,
        description=(
            "Index in der 32-Farben overlay-Palette (Schema 0.5.0+). "
            "Client assigned beim Erstellen via ``nextColorIndex(regions.length)``. "
            "Falls fehlt (alte snapshots), default 0."
        ),
    )
    viewport_snapshot: Viewport | None = Field(
        default=None,
        description=(
            "Snapshot von page-scroll + viewport-/document-dimensionen zum "
            "Zeichen-Zeitpunkt (Schema 0.6.0+). Optional für backward-compat "
            "mit Schema-0.5.0-Regionen. Caller-use: screenshot-canvas-sizing, "
            "layout-drift-detection."
        ),
    )
    origin_session: str | None = Field(
        default=None,
        description=(
            "session_id of the session that last mutated this entity "
            "(steal-on-mutate provenance via sqlite-persistence). "
            "None until first persisted."
        ),
    )


RelationKind = Literal["relates_to", "triggers", "part_of"]
"""Discriminator für Relation-typen — Phase 1.

- ``relates_to``: symmetric semantic link (rendered ohne arrowhead).
- ``triggers``: directed action — A löst B aus.
- ``part_of``: directed containment — A ist Teil von B.

Phase-2-Erweiterung (additiv): ``depends_on`` für ordering-constraints.
Erweiterung = Literal extenden + Schema-bump + renderer-case + ein-Zeilen-
Migration in den UI-pickern.
"""

RELATION_KINDS: tuple[RelationKind, ...] = get_args(RelationKind)
"""Tuple aller RelationKinds — für UI-dropdown-iteration."""


RelationEndpointKind = Literal["pick", "region"]
"""Discriminator: ist ein Relation-endpoint ein Pick oder eine Region?

Heterogeneous-Graph-Refactor (Schema 0.4.0): Relations können jetzt Picks
ODER Regions als source/target haben. Davor (0.3.0): nur Pick↔Pick.
"""

RELATION_ENDPOINT_KINDS: tuple[RelationEndpointKind, ...] = get_args(RelationEndpointKind)


class Relation(BaseModel):
    """Directed edge zwischen zwei Nodes (Picks oder Regions).

    Heterogeneous Graph (Schema 0.4.0): source + target können pick_id ODER
    region_id sein, discriminiert via ``source_kind`` / ``target_kind``.
    Klassisches Graph-Edge-Modell aber mit node-type-discriminator.

    Vernon-Regel: cross-Aggregate-refs via Identifier-String, nicht
    Object-Pointer. Display "Relations für Pick/Region X" wird derived via
    Frontend-LookupService.

    ``kind`` ist ein closed Literal (Phase 1: 3 kinds: relates_to/triggers/
    part_of). Erweiterung additiv + Schema-bump.

    ``note`` ist optional — user-text. Self-loops verboten via model-validator.
    """

    model_config = ConfigDict(frozen=False)

    relation_id: str = Field(description="Client-generated uuid4.")
    source_id: str = Field(description="FK auf Pick.pick_id ODER Region.region_id (siehe source_kind).")
    source_kind: RelationEndpointKind = Field(description="Endpoint-Type des source.")
    target_id: str = Field(description="FK auf Pick.pick_id ODER Region.region_id (siehe target_kind).")
    target_kind: RelationEndpointKind = Field(description="Endpoint-Type des target.")
    kind: RelationKind = Field(description="Relation-Typ-Discriminator.")
    note: str | None = Field(default=None, description="Optional user-text.")
    timestamp_ms: int = Field(description="Client-clock epoch ms zum Erstellungszeitpunkt.")
    origin_session: str | None = Field(
        default=None,
        description=(
            "session_id of the session that last mutated this entity "
            "(steal-on-mutate provenance via sqlite-persistence). "
            "None until first persisted."
        ),
    )

    @model_validator(mode="after")
    def _no_self_loop(self) -> Relation:
        if self.source_id == self.target_id and self.source_kind == self.target_kind:
            raise ValueError(
                f"Relation source and target must differ — got "
                f"({self.source_kind!r}, {self.source_id!r}) for both "
                f"(no self-loops in Phase 1)."
            )
        return self


class InspectorState(BaseModel):
    """Inspector-feature backend-state.

    ``active`` = Pick-Mode toggle. ``picks`` = ordered list of captured picks
    (newest appended). ``active_pick_id`` = which pick the right-panel displays.
    ``regions`` = ordered list of regions (containers über picks, Schema 0.4.0+).
    ``active_region_id`` = which region the right-panel displays (None if a
    pick is active or nothing).
    ``relations`` = parallel list of directed edges zwischen Nodes (Picks oder
    Regions, heterogeneous via source_kind/target_kind).

    UI-Preferences (visibility-toggles, hover-highlights) gehören NICHT in dieses
    Modell — die leben Frontend-only in ``local-state/ui-prefs.svelte.ts``.

    Phase 1: in-memory only (verloren bei CLI-Restart). Phase 2: SQLite-persisted.
    """

    model_config = ConfigDict(frozen=False)

    active: bool = Field(default=False, description="Inspector pick-mode toggle.")
    picks: list[Pick] = Field(default_factory=list, description="Captured picks (newest last).")
    active_pick_id: str | None = Field(
        default=None,
        description="Pick-id derzeit im right-panel angezeigt, oder None.",
    )
    regions: list[Region] = Field(
        default_factory=list,
        description="Räumliche Container über Picks (Schema 0.4.0+).",
    )
    active_region_id: str | None = Field(
        default=None,
        description="Region-id derzeit im right-panel angezeigt, oder None. "
        "Mutually exclusive mit active_pick_id (only one details-target).",
    )
    relations: list[Relation] = Field(
        default_factory=list,
        description="Directed edges zwischen Picks/Regions (heterogeneous, typed, optional note).",
    )


# ----------------------------------------------------------------------------
# StateSnapshot — top-level wire-payload
# ----------------------------------------------------------------------------


class StateSnapshot(BaseModel):
    """Voller authoritative-state-snapshot, gesendet von Python ans Overlay.

    Wire-trigger: nach jedem ``OverlayReady`` empfangen (re-hydration nach
    cross-origin-navigation) + nach jeder authoritative mutation
    (broadcast-update).

    Schema-Version:
        - 0.1.0: nur panel_state
        - 0.2.0: + inspector_state (picks-flow)
        - 0.3.0: + inspector_state.relations (additive)
        - 0.4.0: heterogeneous Relations (source_id+source_kind+target_id+target_kind
          statt source_pick_id+target_pick_id) + inspector_state.regions +
          inspector_state.active_region_id. BREAKING change am Relation shape.
        - 0.5.0: + Pick.color_index + Region.color_index (additive — old snapshots
          default 0). Overlay rendert pro-pick / pro-region eindeutige Farbe aus
          der 32-color palette.
        - 0.6.0: Region.rect semantisch zu **page-absoluten Koordinaten** migriert
          (vorher viewport-relativ). Plus :class:`Viewport`-snapshot field für
          screenshot-extraction-context. Backwards-additiv am wire-shape, aber
          coords sind nicht mehr direkt vergleichbar — bewusster bump.
        - 0.7.0: + ``origin_session`` on Pick/Region/Relation (additive — persistence provenance).
    """

    # Read-only wire-payload — constructed by snapshot(), never mutated after construction.
    # frozen=True surfaces accidental mutation as immediate ValidationError.
    model_config = ConfigDict(frozen=True)

    schema_version: str = Field(
        default="0.7.0",
        description="Forward-compat tag — bump bei breaking changes.",
    )
    panel_state: PanelStateView = Field(description="Aktueller authoritative panel-state.")
    inspector_state: InspectorState = Field(
        default_factory=InspectorState,
        description="Aktueller inspector-state — active toggle + picks-list.",
    )


# ----------------------------------------------------------------------------
# StateSummary — navigable overview (firehose mitigation)
# ----------------------------------------------------------------------------

#: Stable short label for ``data:`` URLs — we never expand the (potentially huge)
#: blob into the summary, only this constant marker.
DATA_URL_HOSTNAME: str = "data:"


def hostname_for_url(url: str) -> str:
    """Derive a stable, compact hostname label from a Pick's ``url``.

    - ``https://example.com/path`` → ``"example.com"``.
    - ``data:text/html,<blob...>`` → :data:`DATA_URL_HOSTNAME` (never the blob —
      a data-URL body can be hundreds of KB and would defeat the whole purpose
      of the summary).
    - URLs without a host (``about:blank``, ``file:///...``, malformed) fall back
      to the scheme (``"about:"`` / ``"file:"``) or, if even that is missing, the
      sentinel ``"(unknown)"``.
    """
    split = urlsplit(url)
    if split.scheme == "data":
        return DATA_URL_HOSTNAME
    if split.hostname:
        return split.hostname
    if split.scheme:
        return f"{split.scheme}:"
    return "(unknown)"


class SummaryCounts(BaseModel):
    """Top-level entity counts."""

    model_config = ConfigDict(frozen=True)

    picks: int = Field(ge=0)
    regions: int = Field(ge=0)
    relations: int = Field(ge=0)


class OriginSessionGroup(BaseModel):
    """Per-origin-session breakdown (provenance grouping, Schema 0.7.0+)."""

    model_config = ConfigDict(frozen=True)

    session: str = Field(description="origin_session id ('(none)' for never-persisted entities).")
    picks: int = Field(ge=0)
    regions: int = Field(ge=0)
    relations: int = Field(ge=0)


class HostnameGroup(BaseModel):
    """Per-hostname pick breakdown (derived from each Pick.url)."""

    model_config = ConfigDict(frozen=True)

    hostname: str = Field(description="Compact host label (see hostname_for_url).")
    picks: int = Field(ge=0)


class OwnedVsForeign(BaseModel):
    """Pick provenance split relative to the current session.

    ``owned`` = picks whose ``origin_session`` equals the current session id.
    ``foreign`` = everything else (including never-persisted ``None``).
    """

    model_config = ConfigDict(frozen=True)

    owned: int = Field(ge=0)
    foreign: int = Field(ge=0)


class StateSummary(BaseModel):
    """Small, navigable overview of the authoritative state — counts + grouping.

    The full :class:`StateSnapshot` is a firehose for an AI agent: a few hundred
    picks serialize to hundreds of KB. ``StateSummary`` is the overview-first
    surface — an agent reads counts + per-session + per-hostname grouping +
    owned-vs-foreign split here, then drills down via ``get_picks`` / ``get_pick``
    / ``get_snapshot`` only on the slice it cares about.

    Groups are sorted deterministically (descending pick-count, then name) so the
    output is stable across calls.
    """

    model_config = ConfigDict(frozen=True)

    schema_version: str = Field(description="Mirrors the StateSnapshot schema_version.")
    current_session_id: str = Field(description="The session id this summary was computed against.")
    active_pick_id: str | None = None
    active_region_id: str | None = None
    counts: SummaryCounts
    by_origin_session: list[OriginSessionGroup] = Field(default_factory=list)
    by_hostname: list[HostnameGroup] = Field(default_factory=list)
    owned_vs_foreign: OwnedVsForeign


# ----------------------------------------------------------------------------
# Codegen-roots — was via pydantic-zod-codegen emittiert wird
# ----------------------------------------------------------------------------

__codegen_roots__ = [
    "PanelView",
    "PanelStateView",
    # ElementRect intentionally NOT a root — nested in Pick.element.rect AND
    # Region.rect, both already emit it inline. Adding it as a root triggers
    # pydantic-zod-codegen $defs-duplication (ElementRect1 mit broken Zod-
    # augmentation, see ``feedback_lib_first_when_pattern_recurs``).
    "ElementFingerprint",
    "PickElement",
    "Pick",
    "Viewport",
    "Region",
    # pydantic-zod-codegen emittiert Literal-aliases als ``export type X = "a" | "b";``
    # (seit pydantic-zod-codegen 3e6bbf2a). Vorher musste das frontend
    # ``type RelationKind = Relation['kind']`` als workaround derive — jetzt direct.
    "RelationKind",
    "RelationEndpointKind",
    "Relation",
    "InspectorState",
    "StateSnapshot",
]

__all__ = [
    "DATA_URL_HOSTNAME",
    "PANEL_IDS",
    "PICK_COMMENT_MAX_LENGTH",
    "REGION_NOTE_MAX_LENGTH",
    "RELATION_ENDPOINT_KINDS",
    "RELATION_KINDS",
    "ElementFingerprint",
    "ElementRect",
    "HostnameGroup",
    "InspectorState",
    "OriginSessionGroup",
    "OwnedVsForeign",
    "PanelId",
    "PanelStateView",
    "PanelView",
    "Pick",
    "PickElement",
    "Region",
    "Relation",
    "RelationEndpointKind",
    "RelationKind",
    "StateSnapshot",
    "StateSummary",
    "SummaryCounts",
    "Viewport",
    "hostname_for_url",
]
