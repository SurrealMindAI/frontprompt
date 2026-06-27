"""Pydantic state-models — SSoT für backendState.

State classification. Phase 1: panel state + inspector state (picks). Phase 2+: annotations
beyond comment, page-history, preferences, disk persistence.

Models hier landen via :mod:`frontprompt.bridge.codegen` als Zod-schemas in
``frontend/src/_generated/state.ts`` (codegen-roots-discovery).

NICHT in :mod:`frontprompt.bridge.messages` — das modul ist für wire-frames,
hier sind die state-shapes selbst.
"""

from __future__ import annotations

from typing import Annotated, Literal, get_args
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
# Recording domain models (Phase 2 — sub-plan 01)
# ----------------------------------------------------------------------------

RecordingStatus = Literal["active", "stopped"]
"""Recording lifecycle status. 'active' während der Aufnahme, 'stopped' nach dem Stopp."""

TranscriptionStatus = Literal["none", "pending", "transcribing", "done", "failed"]
"""Transcription lifecycle status für eine Aufnahme mit Voice-Over.

- ``none``: Keine Voice-Over-Aufnahme, oder noch nicht gestartet.
- ``pending``: Audio-Datei fertig, Transkription noch nicht gestartet.
- ``transcribing``: Transkription läuft.
- ``done``: Segmente in Timeline injiziert.
- ``failed``: Transkription fehlgeschlagen; ``transcription_error`` enthält Details.

One-directional: none → pending → transcribing → done/failed.
"""

TimelineEntryKind = Literal[
    "page_event", "pick_ref", "region_ref", "relation_ref", "navigation", "assertion",
    "transcript_segment",
]
"""Discriminator für die TimelineEntry-Union. Eine pro Variant-Klasse."""

# ----------------------------------------------------------------------------
# Assertion domain types (replay + assertion authoring — sub-plan 01)
# ----------------------------------------------------------------------------

AssertionType = Literal["selector_exists", "text_equals", "text_contains", "visible", "url_equals"]
"""Art der Assertion — was geprüft wird.

- ``selector_exists``: CSS-Selektor muss im DOM vorhanden sein.
- ``text_equals``/``text_contains``: Text des Elements muss gleich/enthalten sein.
- ``visible``: Element muss sichtbar sein (kein display:none, kein visibility:hidden).
- ``url_equals``: Aktuelle URL muss übereinstimmen.
"""

AssertionComparator = Literal["equals", "contains", "regex", "none"]
"""Vergleichsoperator für Assertion-Evaluierung.

``'none'`` wird für ``selector_exists`` und ``visible`` verwendet wo ``expected`` immer None ist.
"""


class PageEventEntry(BaseModel):
    """Eine erfasste Seiten-Interaktion (click, pointerdown, keydown).

    ``wheel``/``scroll`` sind bewusst ausgeschlossen (wire-economy: bis zu 60
    Events/s würden den expose_function-Transport überlasten).
    HUD-chrome-Events (isHudChrome=true) sind excluded — die eigenen Toolbar-
    Clicks dürfen die Aufnahme nicht verschmutzen.
    """

    model_config = ConfigDict(frozen=False)

    kind: Literal["page_event"] = "page_event"
    seq: int = Field(description="Monotoner Sequence-Counter, Python-seitig gestempelt.")
    timestamp_ms: int = Field(description="Epoch ms zum Capture-Zeitpunkt.")
    event_type: Literal["click", "pointerdown", "keydown"] = Field(
        description="Event-Typ — nur durable relevante Interactions (wheel/scroll excluded)."
    )
    target: str = Field(description="tag#id.class descriptor des Zielelements.")
    target_path: list[str] = Field(
        default_factory=list,
        description="Tag-Sequenz root→Element (DOM-Pfad).",
    )
    default_prevented: bool = Field(description="Ob event.preventDefault() aufgerufen wurde.")
    key: str | None = Field(default=None, description="keydown only — gedrückte Taste.")


class PickRefEntry(BaseModel):
    """Referenz auf einen Pick, der während dieser Aufnahme erstellt wurde.

    FK-Dehydration (ADR-012): ``pick_id`` ist ein bare UUID-Fremdschlüssel,
    kein eingebettetes Objekt.
    """

    model_config = ConfigDict(frozen=False)

    kind: Literal["pick_ref"] = "pick_ref"
    seq: int
    timestamp_ms: int
    pick_id: str = Field(description="FK → Pick.pick_id (client-generated uuid4).")


class RegionRefEntry(BaseModel):
    """Referenz auf eine Region, die während dieser Aufnahme gezeichnet wurde."""

    model_config = ConfigDict(frozen=False)

    kind: Literal["region_ref"] = "region_ref"
    seq: int
    timestamp_ms: int
    region_id: str = Field(description="FK → Region.region_id.")


class RelationRefEntry(BaseModel):
    """Referenz auf eine Relation, die während dieser Aufnahme erstellt wurde."""

    model_config = ConfigDict(frozen=False)

    kind: Literal["relation_ref"] = "relation_ref"
    seq: int
    timestamp_ms: int
    relation_id: str = Field(description="FK → Relation.relation_id.")


class NavigationEntry(BaseModel):
    """Eine Page-Navigation, die vom Python-Session erfasst wurde.

    Cross-origin-Survival: Aufnahmen laufen über Navigationen hinweg —
    NavigationEntry dokumentiert den Sprung für spätere Replay-Rekonstruktion.
    """

    model_config = ConfigDict(frozen=False)

    kind: Literal["navigation"] = "navigation"
    seq: int
    timestamp_ms: int
    from_url: str = Field(description="URL vor der Navigation.")
    to_url: str = Field(description="URL nach der Navigation.")


class AssertionEntry(BaseModel):
    """Eine Assertion-Checkpoint in der Recording-Timeline (replay + assertions — sub-plan 01).

    Wird während Replay durch den ``AssertionEvaluator`` ausgewertet. Pass/Fail
    wird im ``ReplayReport`` festgehalten. Kann nachträglich auf eine gespeicherte
    Aufnahme via ``AddAssertionRequest`` oder bridge-Authoring hinzugefügt werden.

    ``assertion_id`` ist die Identität (kein UNIQUE auf description).
    ``seq`` ist Python-seitig zugewiesen (monoton, analog allen anderen Varianten).
    ``target`` ist ein CSS-Selektor für element-targeted assertions; leer für ``url_equals``.
    """

    model_config = ConfigDict(frozen=False)

    kind: Literal["assertion"] = "assertion"
    seq: int = Field(description="Monotoner Sequence-Counter, Python-seitig gestempelt.")
    timestamp_ms: int = Field(description="Epoch ms zum Erstellungszeitpunkt.")
    assertion_id: str = Field(description="Client-generated uuid4 — Identität.")
    assertion_type: AssertionType = Field(description="Art der Assertion.")
    target: str = Field(
        default="",
        description=(
            "CSS-Selektor für element-targeted assertions (tag#id.class descriptor). "
            "Leer für url_equals."
        ),
    )
    target_kind: Literal["selector", "url"] = Field(
        description="Typ des target — 'selector' für DOM-Assertions, 'url' für URL-Assertion."
    )
    expected: str | None = Field(
        default=None,
        description="Erwarteter Wert; None für selector_exists und visible.",
    )
    comparator: AssertionComparator = Field(
        description="Vergleichsoperator; 'none' für selector_exists und visible."
    )
    description: str = Field(
        default="",
        description="Human-readable Label für Report-Anzeige.",
    )


class TranscriptSegmentEntry(BaseModel):
    """Ein transkribiertes Sprachsegment in der Recording-Timeline (voice-over — sub-plan 01).

    Wird nach der Transkription durch den Post-Processor via
    ``StateManager.append_transcript_segments`` in Batches injiziert.
    Ein einziger Broadcast am Ende des Batches (nicht pro-Segment — wire-economy).

    ``timestamp_ms = recording.started_at_ms + start_ms`` — sortiert korrekt
    im chronologischen Timeline-Merge. ``seq`` ist Python-seitig gestempelt
    (monotoner Zähler, gleiche Invariante wie alle anderen Varianten).
    ``backend_id`` dokumentiert welches Backend das Segment erzeugt hat.
    """

    model_config = ConfigDict(frozen=False)

    kind: Literal["transcript_segment"] = "transcript_segment"
    seq: int = Field(description="Monotoner Sequence-Counter, Python-seitig gestempelt.")
    timestamp_ms: int = Field(description="Epoch ms = recording.started_at_ms + start_ms.")
    start_ms: int = Field(description="Segmentbeginn relativ zum Aufnahmestart in ms.")
    end_ms: int = Field(description="Segmentende relativ zum Aufnahmestart in ms.")
    text: str = Field(description="Transkribierter Text dieses Segments.")
    backend_id: str = Field(description="Backend-ID das dieses Segment erzeugt hat (z.B. 'mlx_whisper').")


TimelineEntry = Annotated[
    PageEventEntry | PickRefEntry | RegionRefEntry | RelationRefEntry | NavigationEntry | AssertionEntry
    | TranscriptSegmentEntry,
    Field(discriminator="kind"),
]
"""Discriminated union aller Timeline-Einträge. Discriminator-Feld: ``kind``.

``seq`` ist global monoton über ALLE Entry-Arten einer Aufnahme — ein Zähler
für alle (page_event, pick_ref, region_ref, relation_ref, navigation, assertion,
transcript_segment). Python-seitig gestempelt als ``len(recording.entries)`` in
``append_timeline_entry`` atomisch innerhalb des Locks — nie durch das Frontend
vergeben. Voice-over-Segmente werden in Batches injiziert (append_transcript_segments).
"""


class ParameterDeclaration(BaseModel):
    """Benannter Parameter-Deklaration auf einem Recording (replay sub-plan 01).

    Parameter werden zur Recording-Authoring-Zeit deklariert und beim Replay-Aufruf
    an konkrete Werte gebunden. Substitutions-Syntax: ``{{param_name}}`` in
    Navigations-URLs, keydown-Text-Werten und Assertion-Targets.

    ``name`` ist der Substitutions-Schlüssel (z.B. ``"login_url"``, ``"username"``).
    Name-Eindeutigkeit wird vom ``StateManager.add_parameter()`` erzwungen.
    """

    model_config = ConfigDict(frozen=False)

    name: str = Field(description="Substitutions-Schlüssel (eindeutig innerhalb der Aufnahme).")
    param_type: Literal["string", "url", "selector"] = Field(description="Parameter-Typ.")
    description: str = Field(default="", description="Human-readable Beschreibung.")
    default_value: str | None = Field(
        default=None,
        description="Default-Wert wenn nicht beim Replay-Aufruf übergeben; None = kein Default.",
    )


class RecordingMeta(BaseModel):
    """Leichtgewichtige Zusammenfassung eines Recordings — ohne ``entries``.

    Enthalten in jedem StateSnapshot-Broadcast (``RecordingsState.recordings``).
    Wird im Recordings-Tab und im MCP-Listing-Tool verwendet.
    """

    model_config = ConfigDict(frozen=False)

    recording_id: str = Field(description="Client-generated uuid4.")
    name: str = Field(description="User-vergebener Name.")
    description: str = Field(default="", description="Optionale Beschreibung.")
    status: RecordingStatus
    started_at_ms: int = Field(description="Client-clock epoch ms zum Start.")
    ended_at_ms: int | None = Field(default=None, description="None solange aktiv.")
    entry_count: int = Field(ge=0, description="Anzahl Timeline-Einträge (≥0).")
    # Voice-over fields (Schema 0.10.0 — additive, backward-compat via defaults)
    has_voice_over: bool = Field(
        default=False,
        description="True wenn eine Voice-Over-Aufnahme für dieses Recording vorliegt.",
    )
    audio_path: str | None = Field(
        default=None,
        description="Absoluter Pfad zur WAV-Datei. None bis Datei finalisiert.",
    )
    transcription_status: TranscriptionStatus = Field(
        default="none",
        description="Transkriptions-Status der Voice-Over-Aufnahme.",
    )


class Recording(BaseModel):
    """Vollständiges Recording-Aggregat mit Timeline-Einträgen.

    Nicht in jedem StateSnapshot-Broadcast enthalten — nur in
    ``RecordingsState.detail_recording`` wenn ``active_detail_recording_id``
    gesetzt ist. ``entries`` sind append-only, geordnet nach ``seq``.

    ``origin_session`` folgt der steal-on-mutate-Provenance-Convention
    von Pick/Region/Relation (sqlite-persistence).
    """

    model_config = ConfigDict(frozen=False)

    recording_id: str = Field(description="Client-generated uuid4 — Identität (keine UNIQUE auf name).")
    name: str
    description: str = Field(default="")
    status: RecordingStatus
    started_at_ms: int = Field(description="Client-clock epoch ms.")
    ended_at_ms: int | None = Field(default=None)
    entries: list[TimelineEntry] = Field(
        default_factory=list,
        description="Timeline-Einträge append-only, geordnet nach seq.",
    )
    parameters: list[ParameterDeclaration] = Field(
        default_factory=list,
        description=(
            "Benannte Parameter-Deklarationen für Replay-Parametrisierung (sub-plan 01). "
            "Additive field — alte Clients ignorieren unbekannte Felder. "
            "Name-Eindeutigkeit wird vom StateManager enforced."
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
    # Voice-over fields (Schema 0.10.0 — additive, backward-compat via defaults)
    has_voice_over: bool = Field(
        default=False,
        description="True wenn eine Voice-Over-Aufnahme für dieses Recording vorliegt.",
    )
    audio_path: str | None = Field(
        default=None,
        description=(
            "Absoluter Pfad zur WAV-Datei im Session-Verzeichnis "
            "(~/.cache/frontprompt/sessions/<session_id>/recording-<recording_id>.wav). "
            "None bis Datei finalisiert."
        ),
    )
    transcription_status: TranscriptionStatus = Field(
        default="none",
        description="Transkriptions-Status — one-directional: none→pending→transcribing→done/failed.",
    )
    transcription_error: str | None = Field(
        default=None,
        description="Fehlermeldung wenn transcription_status='failed'. Nur auf Recording (nicht RecordingMeta).",
    )


# ----------------------------------------------------------------------------
# Replay domain models (sub-plan 01)
# ----------------------------------------------------------------------------

ReplayStatus = Literal["completed", "failed", "aborted"]
"""Status eines abgeschlossenen Replay-Laufs.

- ``completed``: Alle Schritte ausgeführt (Assertions können fehlgeschlagen sein, Lauf fertig).
- ``failed``: Nicht-wiederherstellbarer Fehler (Page-crash, Nav-timeout) hat Ausführung gestoppt.
- ``aborted``: Explizit abgebrochen via StopReplayRequest (zukünftig) oder Timeout.
"""


class ReplayStepResult(BaseModel):
    """Per-step Ergebnis innerhalb eines ReplayReport.

    Ein Eintrag pro TimelineEntry-Versuch beim Replay.
    ``ok=True AND assertion_passed=False`` ist valid — Schritt lief, aber Assertion schlug fehl.
    ``ok=False`` bedeutet, dass der Schritt selbst nicht ausgeführt werden konnte.
    """

    model_config = ConfigDict(frozen=False)

    seq: int = Field(description="seq des zugehörigen TimelineEntry.")
    kind: str = Field(description="kind des TimelineEntry (mirrors TimelineEntry.kind).")
    ok: bool = Field(description="True = Schritt erfolgreich ausgeführt.")
    skipped: bool = Field(description="True für pick_ref/region_ref/relation_ref im MVP.")
    skipped_reason: str | None = Field(default=None, description="Grund für das Überspringen.")
    error: str | None = Field(default=None, description="Fehlermeldung wenn ok=False.")
    assertion_passed: bool | None = Field(
        default=None,
        description="None für Nicht-Assertions; True/False für Assertion-Schritte.",
    )
    assertion_actual: str | None = Field(
        default=None,
        description="Tatsächlicher Wert für Diagnose (nur bei assertion-Schritten).",
    )
    duration_ms: int = Field(description="Ausführungszeit dieses Schritts in ms.")


class ReplayReport(BaseModel):
    """Dauerhaftes Ergebnis eines einzelnen Replay-Laufs.

    Erzeugt vom ReplayPlayer, in SQLite persistiert.
    Nicht im StateSnapshot-Broadcast enthalten — nur ReplayProgress (leichtgewichtig)
    ist in RecordingsState während eines aktiven Laufs. Vollständiger ReplayReport
    wird via GetReplayReportRequest abgerufen.
    """

    model_config = ConfigDict(frozen=False)

    replay_id: str = Field(description="uuid4 — Identität.")
    recording_id: str = Field(description="FK → Recording.recording_id.")
    parameters: dict[str, str] = Field(
        default_factory=dict,
        description="Beim Aufruf gebundene Parameter (leeres dict wenn keine Parameter).",
    )
    status: ReplayStatus
    started_at_ms: int = Field(description="Epoch ms zum Start.")
    ended_at_ms: int | None = Field(default=None, description="None wenn aborted vor Ende.")
    step_results: list[ReplayStepResult] = Field(default_factory=list)
    error: str | None = Field(
        default=None,
        description="Top-level Fehler für aborted-Replays.",
    )
    origin_session: str | None = Field(
        default=None,
        description="session_id der Session die den Replay initiiert hat (Provenance).",
    )


class ReplayReportMeta(BaseModel):
    """Leichtgewichtige Zusammenfassung eines ReplayReport — ohne step_results.

    Für List-Views (list_replay_reports_meta). Analog RecordingMeta für Recordings.
    """

    model_config = ConfigDict(frozen=False)

    replay_id: str = Field(description="uuid4 — Identität.")
    recording_id: str = Field(description="FK → Recording.recording_id.")
    status: ReplayStatus
    started_at_ms: int
    ended_at_ms: int | None = Field(default=None)
    step_count: int = Field(ge=0, description="Anzahl step_results.")
    passed_assertions: int = Field(ge=0, description="Anzahl bestandener Assertions.")
    failed_assertions: int = Field(ge=0, description="Anzahl fehlgeschlagener Assertions.")


class ReplayProgress(BaseModel):
    """Leichtgewichtiger Fortschritts-Snapshot während eines aktiven Replays.

    In RecordingsState.active_replay_progress während einer aktiven Replay-Ausführung.
    Ermöglicht Live-Fortschrittsanzeige im Overlay ohne den vollen ReplayReport zu senden.
    ``active_replay_progress`` ist backendState — Replay läuft über Cross-Origin-Navigationen
    weiter; Progress muss Page-Destruction überleben.
    """

    model_config = ConfigDict(frozen=False)

    replay_id: str = Field(description="FK → ReplayReport.replay_id.")
    recording_id: str = Field(description="FK → Recording.recording_id.")
    current_seq: int = Field(description="seq des aktuell ausgeführten Schritts.")
    total_steps: int = Field(description="Gesamtzahl der Timeline-Schritte.")
    passed_assertions: int = Field(ge=0)
    failed_assertions: int = Field(ge=0)


class RecordingsState(BaseModel):
    """Recording-feature Backend-State — Teil des StateSnapshot.

    ``active_recording_id`` überlebt cross-origin-Navigationen (backendState).
    ``active_detail_recording_id`` ist ebenfalls backendState (analog zu
    ``active_pick_id`` / ``active_region_id`` — right-panel Detail-Selektion
    persistiert nach Nav). ADR-018 verbietet nur ephemere UI-States (hover,
    drag), nicht durable Selektionszustände.

    ``detail_recording`` wird nur befüllt wenn ``active_detail_recording_id``
    gesetzt ist — vollständige Timeline inklusive. Nicht in jedem Broadcast
    enthalten wenn None.
    """

    model_config = ConfigDict(frozen=False)

    active_recording_id: str | None = Field(
        default=None,
        description="ID der laufenden Aufnahme, None = nicht aufnehmend.",
    )
    recordings: list[RecordingMeta] = Field(
        default_factory=list,
        description="Lightweight Zusammenfassungen aller Recordings.",
    )
    active_detail_recording_id: str | None = Field(
        default=None,
        description="ID der im right-panel angezeigten Aufnahme (detail-Ansicht).",
    )
    detail_recording: Recording | None = Field(
        default=None,
        description="Vollständiges Recording mit Timeline (nur wenn active_detail_recording_id gesetzt).",
    )
    active_replay_progress: ReplayProgress | None = Field(
        default=None,
        description=(
            "Fortschritts-Snapshot eines aktiven Replay-Laufs (sub-plan 01, Schema 0.9.0+). "
            "None wenn kein Replay läuft. Additive field — alte Overlays ignorieren unbekannte Felder. "
            "backendState: Replay läuft über Cross-Origin-Navigationen weiter."
        ),
    )


# ----------------------------------------------------------------------------
# Voice-over state models (Schema 0.10.0 — sub-plan 01)
# ----------------------------------------------------------------------------


class MicrophoneDevice(BaseModel):
    """Ein einzelnes Eingabegerät aus dem sounddevice-Katalog.

    ``device_id`` ist der sounddevice-Index — stabil innerhalb einer laufenden
    Sitzung, kann aber nach einem Geräte-Reconnect anders sein.
    """

    model_config = ConfigDict(frozen=False)

    device_id: int = Field(description="sounddevice-Index des Mikrofons.")
    name: str = Field(description="Anzeigename des Geräts.")
    channels: int = Field(description="Maximale Anzahl der Eingangskanäle.")
    default_sample_rate: float = Field(description="Standard-Samplerate in Hz.")


class MicrophoneState(BaseModel):
    """Aktueller Zustand der Mikrofon-Enumeration.

    ``devices`` und ``system_default_device_id`` sind In-Process-State —
    re-enumeriert durch den Mic-Watcher-Task bei Topologie-Änderungen.
    ``selected_device_id`` ist die dauerhafte User-Präferenz — persistiert
    via ``StateManager.set_mic_device(device_id)`` in der ``settings``-Tabelle.

    Initial (vor dem ersten Watcher-Cycle): devices=[] ist valid.
    """

    model_config = ConfigDict(frozen=False)

    devices: list[MicrophoneDevice] = Field(
        default_factory=list,
        description="Alle verfügbaren Eingangsgeräte (leer bis erster Watcher-Cycle).",
    )
    selected_device_id: int | None = Field(
        default=None,
        description="User-gewähltes Gerät (None = System-Default). Durable — Settings-Tabelle.",
    )
    system_default_device_id: int | None = Field(
        default=None,
        description="Aktuelles System-Default-Gerät von sounddevice. Nicht durable.",
    )


class TranscriptionModelSpec(BaseModel):
    """Statischer Katalog-Eintrag für ein mlx-whisper Modell.

    Lebt in :class:`TranscriptionBackendInfo`.available_models — nicht persisted
    (Katalog ist statischer Code). ``default=True`` markiert das Modell das
    verwendet wird wenn kein User-Selection vorhanden ist.

    Cache-Subdir-Pfad wird zur Laufzeit aus ``hf_repo_id`` abgeleitet
    (``models--`` Prefix + ``/`` → ``--`` Substitution) — nicht gespeichert.
    """

    model_config = ConfigDict(frozen=True)

    model_id: str = Field(description="Stabiler machine-readable Bezeichner (z.B. 'whisper-base-mlx').")
    display_name: str = Field(description="Anzeigename in der UI (z.B. 'Whisper Base (MLX)').")
    hf_repo_id: str = Field(description="HuggingFace Repo-ID (z.B. 'mlx-community/whisper-base-mlx').")
    default: bool = Field(description="True für das Standard-Modell (genau eines je Katalog).")


class SettingsState(BaseModel):
    """Dauerhafte User-Einstellungen für das Voice-Over-Feature.

    Alle Felder sind durable — persistiert in der ``settings``-Key-Value-Tabelle.
    ``selected_mic_device_id`` lebt NICHT hier sondern in
    :class:`MicrophoneState`.selected_device_id (co-location von Mic-Concerns).
    """

    model_config = ConfigDict(frozen=False)

    voice_over_enabled: bool = Field(
        default=False,
        description="Voice-Over-Feature aktiviert (User-Opt-In).",
    )
    selected_transcription_backend_id: str | None = Field(
        default=None,
        description="Gewähltes Backend (None = Auto — erstes 'ready'-Backend).",
    )
    mlx_whisper_model_id: str | None = Field(
        default=None,
        description=(
            "Gewähltes mlx-whisper Modell (None = Standard-Modell aus MODEL_CATALOG). "
            "Persistiert in der settings-Tabelle. Schema 0.11.0+."
        ),
    )


TranscriptionBackendStatus = Literal[
    "unavailable", "missing_dep", "needs_download", "downloading", "ready", "error"
]
"""Verfügbarkeitsstatus eines Transkriptions-Backends.

- ``unavailable``: Plattform nicht unterstützt (z.B. non-Apple-Silicon für mlx_whisper).
- ``missing_dep``: Optional-Extra nicht installiert (``uv pip install frontprompt[voice]``).
- ``needs_download``: Dep installiert, Modell noch nicht heruntergeladen.
- ``downloading``: Modell-Download läuft.
- ``ready``: Bereit für Transkription.
- ``error``: Initialisierungsfehler (siehe ``error_message``).
"""


class TranscriptionBackendInfo(BaseModel):
    """Status-Info für ein Transkriptions-Backend (z.B. mlx_whisper).

    ``download_progress`` ist ephemer (In-Process, nicht in SQLite).
    Das Overlay rendert eine Fortschrittsanzeige während des Downloads.

    ``available_models`` enthält den statischen Modell-Katalog dieses Backends
    (aus MODEL_CATALOG in :mod:`frontprompt.voice.backends.mlx_whisper`).
    ``selected_model_id`` ist die aktuell gewählte Modell-ID (aus persistierter
    Settings oder Default-Modell). Beide Felder sind In-Process-State (Schema 0.11.0+).
    """

    model_config = ConfigDict(frozen=False)

    backend_id: str = Field(description="Backend-Bezeichner (z.B. 'mlx_whisper').")
    display_name: str = Field(description="Lesbares Label (z.B. 'mlx-whisper (Apple Silicon)').")
    status: TranscriptionBackendStatus = Field(description="Aktueller Verfügbarkeitsstatus.")
    download_progress: float | None = Field(
        default=None,
        description="0.0–1.0 während Download; None sonst. Ephemer (nicht persistiert).",
    )
    error_message: str | None = Field(
        default=None,
        description="Fehlermeldung bei status='error'.",
    )
    available_models: list[TranscriptionModelSpec] = Field(
        default_factory=list,
        description=(
            "Statischer Modell-Katalog dieses Backends (Schema 0.11.0+). "
            "In-Process-State — rebuilt from catalog on each session start. Nicht persistiert."
        ),
    )
    selected_model_id: str | None = Field(
        default=None,
        description=(
            "Aktuell gewählte Modell-ID (Schema 0.11.0+). "
            "Derived at session start from settings_state.mlx_whisper_model_id. "
            "In-Process-State — nicht separat persistiert."
        ),
    )


class TranscriptionState(BaseModel):
    """Aggregierter Status aller bekannten Transkriptions-Backends.

    Python-authoritative — Backend bestimmt Verfügbarkeit via probe_status().
    Nicht in SQLite persistiert (Neustart → erneutes Probing korrekt).
    """

    model_config = ConfigDict(frozen=False)

    backends: list[TranscriptionBackendInfo] = Field(
        default_factory=list,
        description="Liste aller bekannten Backends mit ihrem Status.",
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
        - 0.8.0: + ``recordings_state`` (additive — Recording-feature domain, sub-plan 01).
          Default ``RecordingsState()`` makes this forward-compatible: old overlays
          ignore the new field; old Python payloads missing the field default to empty.
        - 0.9.0: + ``AssertionEntry`` TimelineEntry-Variante, + ``Recording.parameters``
          (ParameterDeclaration list), + ``RecordingsState.active_replay_progress``
          (ReplayProgress | None, additive — None-default macht es forward-compat).
        - 0.10.0: + Voice-Over-Domain (sub-plan 01). ``TranscriptSegmentEntry`` als
          7. TimelineEntry-Variante. Voice-over-Felder auf Recording/RecordingMeta
          (has_voice_over, audio_path, transcription_status, transcription_error).
          Neue StateSnapshot-Felder: ``microphone_state``, ``settings_state``,
          ``transcription_state`` (alle additive mit default_factory — backward-compat
          mit alten Overlays die unbekannte Felder ignorieren).
        - 0.11.0: + ``TranscriptionModelSpec`` (model catalog entry). Neues Feld
          ``SettingsState.mlx_whisper_model_id`` (durable User-Modell-Selektion).
          Neue Felder auf ``TranscriptionBackendInfo``: ``available_models`` und
          ``selected_model_id`` (beide additive, In-Process-State). Ermöglicht
          modell-wechsel zur Laufzeit ohne Neustart.
    """

    # Read-only wire-payload — constructed by snapshot(), never mutated after construction.
    # frozen=True surfaces accidental mutation as immediate ValidationError.
    model_config = ConfigDict(frozen=True)

    schema_version: str = Field(
        default="0.11.0",
        description="Forward-compat tag — bump bei breaking changes.",
    )
    panel_state: PanelStateView = Field(description="Aktueller authoritative panel-state.")
    inspector_state: InspectorState = Field(
        default_factory=InspectorState,
        description="Aktueller inspector-state — active toggle + picks-list.",
    )
    recordings_state: RecordingsState = Field(
        default_factory=RecordingsState,
        description="Recording-feature state — active recording + list + detail (Schema 0.8.0+).",
    )
    microphone_state: MicrophoneState = Field(
        default_factory=MicrophoneState,
        description=(
            "Mikrofon-Enumeration — verfügbare Geräte + User-Präferenz (Schema 0.10.0+). "
            "Additive field — alte Overlays ignorieren unbekannte Felder."
        ),
    )
    settings_state: SettingsState = Field(
        default_factory=SettingsState,
        description=(
            "Dauerhafte Voice-Over-Einstellungen (Schema 0.10.0+). "
            "Additive field — alte Overlays ignorieren unbekannte Felder."
        ),
    )
    transcription_state: TranscriptionState = Field(
        default_factory=TranscriptionState,
        description=(
            "Transkriptions-Backend-Status (Schema 0.10.0+). "
            "Additive field — alte Overlays ignorieren unbekannte Felder."
        ),
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
    # Recording-feature domain (Schema 0.8.0, sub-plan 01)
    "RecordingStatus",
    "TimelineEntryKind",
    "PageEventEntry",
    "PickRefEntry",
    "RegionRefEntry",
    "RelationRefEntry",
    "NavigationEntry",
    "RecordingMeta",
    "Recording",
    "RecordingsState",
    # Replay + assertion domain (Schema 0.9.0, sub-plan 01)
    "AssertionType",
    "AssertionComparator",
    "AssertionEntry",
    "ParameterDeclaration",
    "ReplayStatus",
    "ReplayStepResult",
    "ReplayReport",
    "ReplayReportMeta",
    "ReplayProgress",
    # Voice-over domain (Schema 0.10.0, sub-plan 01)
    "TranscriptionStatus",
    "TranscriptSegmentEntry",
    "MicrophoneDevice",
    "MicrophoneState",
    "SettingsState",
    "TranscriptionBackendStatus",
    "TranscriptionBackendInfo",
    "TranscriptionState",
    # Model catalog (Schema 0.11.0, sub-plan 01)
    "TranscriptionModelSpec",
]

__all__ = [
    "DATA_URL_HOSTNAME",
    "PANEL_IDS",
    "PICK_COMMENT_MAX_LENGTH",
    "REGION_NOTE_MAX_LENGTH",
    "RELATION_ENDPOINT_KINDS",
    "RELATION_KINDS",
    "AssertionComparator",
    "AssertionEntry",
    "AssertionType",
    "ElementFingerprint",
    "ElementRect",
    "HostnameGroup",
    "InspectorState",
    "MicrophoneDevice",
    "MicrophoneState",
    "NavigationEntry",
    "OriginSessionGroup",
    "OwnedVsForeign",
    "PageEventEntry",
    "PanelId",
    "PanelStateView",
    "PanelView",
    "ParameterDeclaration",
    "Pick",
    "PickElement",
    "PickRefEntry",
    "Recording",
    "RecordingMeta",
    "RecordingStatus",
    "RecordingsState",
    "RegionRefEntry",
    "Region",
    "RelationRefEntry",
    "Relation",
    "RelationEndpointKind",
    "RelationKind",
    "ReplayProgress",
    "ReplayReport",
    "ReplayReportMeta",
    "ReplayStatus",
    "ReplayStepResult",
    "SettingsState",
    "StateSnapshot",
    "StateSummary",
    "SummaryCounts",
    "TimelineEntry",
    "TimelineEntryKind",
    "TranscriptSegmentEntry",
    "TranscriptionBackendInfo",
    "TranscriptionBackendStatus",
    "TranscriptionModelSpec",
    "TranscriptionState",
    "TranscriptionStatus",
    "Viewport",
    "hostname_for_url",
]
