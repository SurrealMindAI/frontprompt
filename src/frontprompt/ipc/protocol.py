"""IPC Wire-Protocol (Pydantic SSoT).

Eigenes ``IPC_SCHEMA_VERSION`` — separate evolution vom Browser↔Python
wire-protocol (:file:`frontprompt/bridge/messages.py`). Beide entwickeln sich
unabhängig.

Request/Response-Format:
    Client sendet EINEN NDJSON-request, Server antwortet mit EINEM NDJSON-response,
    dann wird die connection geschlossen. Keine persistent subscriptions in Phase 1.

Discriminator: ``kind``-Field auf request-side.
"""

from __future__ import annotations

from typing import Annotated, Any, Literal

from pydantic import BaseModel, ConfigDict, Field

from frontprompt.analysis.types import DomPatchOp, FindQuery
from frontprompt.state.state import AssertionComparator, AssertionType, ReplayStatus

#: Schema-version dieses IPC-Protokolls.
#: 0.1.0 — initial read-only protocol (ping, get_snapshot, get_picks, get_pick)
#: 0.2.0 — additive: NavigateRequest (browser-action, first write-side request)
#: 0.3.0 — additive: 11 mcp scout-tool requests + 10 result-models
#: 0.4.0 — additive: 14 PageAnalyzer requests (11 high-level + 3 low-level)
#:          + screenshot return_mode + pick_by_text rewire
#: 0.5.0 — additive: get_state_summary (navigable counts+grouping overview)
#: 0.6.0 — additive: get_comments (compact agent-readable annotation surface)
#: 0.7.0 — additive: get_recordings (list RecordingMeta) + get_recording (full Recording)
#: 0.8.0 — additive: start_recording + stop_recording + run_replay + get_replay_report
#:          + list_replay_reports + add_assertion (replay-bundle write-side, sub-plan 02)
IPC_SCHEMA_VERSION: str = "0.8.0"


# ----------------------------------------------------------------------------
# Requests (Client → Server)
# ----------------------------------------------------------------------------


class PingRequest(BaseModel):
    """Liveness-check. Server antwortet mit ``{"pong": True}``."""

    model_config = ConfigDict(extra="forbid")

    kind: Literal["ping"] = "ping"
    schema_version: str = IPC_SCHEMA_VERSION


class GetSnapshotRequest(BaseModel):
    """Voller :class:`~frontprompt.state.state.StateSnapshot` (incl. inspector + panel)."""

    model_config = ConfigDict(extra="forbid")

    kind: Literal["get_snapshot"] = "get_snapshot"
    schema_version: str = IPC_SCHEMA_VERSION


class GetPicksRequest(BaseModel):
    """Nur die ``inspector_state.picks``-Liste — handy für quick CLI inspection."""

    model_config = ConfigDict(extra="forbid")

    kind: Literal["get_picks"] = "get_picks"
    schema_version: str = IPC_SCHEMA_VERSION


class GetPickRequest(BaseModel):
    """Einen einzelnen Pick by id. ``ok=False`` wenn unknown."""

    model_config = ConfigDict(extra="forbid")

    kind: Literal["get_pick"] = "get_pick"
    schema_version: str = IPC_SCHEMA_VERSION
    pick_id: str = Field(description="UUID4 des Picks (siehe :class:`Pick.pick_id`).")


class GetStateSummaryRequest(BaseModel):
    """Small navigable overview — counts + grouping, NOT the full snapshot.

    Returns a :class:`~frontprompt.state.state.StateSummary` (Schema 0.5.0): top-
    level entity counts, per-origin-session grouping, per-hostname pick grouping,
    and the owned-vs-foreign split. The overview-first surface for AI agents that
    would otherwise drown in the full :class:`GetSnapshotRequest` firehose. Drill
    down via get_snapshot / get_picks / get_pick once the slice is known.
    """

    model_config = ConfigDict(extra="forbid")

    kind: Literal["get_state_summary"] = "get_state_summary"
    schema_version: str = IPC_SCHEMA_VERSION


class GetCommentsRequest(BaseModel):
    """Return all picks with non-empty comment fields as compact AnnotationEntry list (Schema 0.6.0).

    Agent-only read surface — no frontend consumer. Returns only picks that
    have a non-empty ``comment``. Programmatic picks auto-suffix ``'[match i/N]'``
    which is non-empty, so they appear. Agents can distinguish human-authored vs
    programmatic by presence of the ``[match i/N]`` suffix.
    """

    model_config = ConfigDict(extra="forbid")

    kind: Literal["get_comments"] = "get_comments"
    schema_version: str = IPC_SCHEMA_VERSION


class NavigateRequest(BaseModel):
    """Navigiere den Browser zur gegebenen URL (Schema 0.2.0).

    First write-side IPC: ändert den Browser-State (current URL, DOM), NICHT den
    StateManager-State. State-classification-conform — Picks und Annotations überleben die
    Navigation; das Overlay wird beim ``framenavigated``-Event automatisch
    re-hydriert vom existing snapshot-listener im show-Prozess.

    Response (``ok=true``): ``{navigated_to: str, title: str}``.
    """

    model_config = ConfigDict(extra="forbid")

    kind: Literal["navigate"] = "navigate"
    schema_version: str = IPC_SCHEMA_VERSION
    url: str = Field(min_length=1, description="Vollständige URL inkl. scheme (z.B. https://...).")


# ── Pick-Creators (Schema 0.3.0) ────────────────────────────────────────────


class PickBySelectorRequest(BaseModel):
    """Create N single-picks per CSS-selector match, capped to ``limit``."""

    model_config = ConfigDict(extra="forbid")

    kind: Literal["pick_by_selector"] = "pick_by_selector"
    schema_version: str = IPC_SCHEMA_VERSION
    selector: str = Field(min_length=1, description="CSS selector to match.")
    comment: str = Field(min_length=1, description="Base comment; auto-suffixed '[match i/N]'.")
    parent_pick_id: str | None = Field(
        default=None,
        description="Scope query inside parent element. Stale parent → hard fail.",
    )
    limit: int = Field(default=10, ge=1, le=50, description="Max picks to create.")


class PickByTextRequest(BaseModel):
    """Create N single-picks for elements matching visible text, optionally filtered by role."""

    model_config = ConfigDict(extra="forbid")

    kind: Literal["pick_by_text"] = "pick_by_text"
    schema_version: str = IPC_SCHEMA_VERSION
    text: str = Field(min_length=1, description="Visible text to match (exact, case-sensitive).")
    role: str | None = Field(default=None, description="Optional ARIA role filter (AND-semantic).")
    comment: str = Field(min_length=1)
    parent_pick_id: str | None = None
    limit: int = Field(default=10, ge=1, le=50)


# ── Element-Readers (Schema 0.3.0) ──────────────────────────────────────────


class GetTextRequest(BaseModel):
    """Read visible text + accessible name + role + enabled/visible/focused state.

    # DEPRECATED — MCP tool removed IPC 0.6.0, IPC dispatch retained for compat.
    # Replacement: frontprompt_inspect_elements(fields=['text','role','visible','enabled','focused','accessible_name'])
    """

    model_config = ConfigDict(extra="forbid")

    kind: Literal["get_text"] = "get_text"
    schema_version: str = IPC_SCHEMA_VERSION
    pick_ids: list[str] = Field(min_length=1, max_length=50)


class GetHtmlRequest(BaseModel):
    """Read outerHTML, truncated to max_chars.

    # DEPRECATED — MCP tool removed IPC 0.6.0, IPC dispatch retained for compat.
    # Replacement: frontprompt_inspect_elements(fields=['html']) or frontprompt_get_page_html
    """

    model_config = ConfigDict(extra="forbid")

    kind: Literal["get_html"] = "get_html"
    schema_version: str = IPC_SCHEMA_VERSION
    pick_ids: list[str] = Field(min_length=1, max_length=50)
    max_chars: int = Field(default=5000, ge=100, le=100_000)


class GetAttributesRequest(BaseModel):
    """Read all HTML attributes as a dict.

    # DEPRECATED — MCP tool removed IPC 0.6.0, IPC dispatch retained for compat.
    # Replacement: frontprompt_inspect_elements(fields=['attributes'])
    """

    model_config = ConfigDict(extra="forbid")

    kind: Literal["get_attributes"] = "get_attributes"
    schema_version: str = IPC_SCHEMA_VERSION
    pick_ids: list[str] = Field(min_length=1, max_length=50)


class GetStateRequest(BaseModel):
    """Read computed visibility/enabled/checked/focused/in_viewport state.

    # DEPRECATED — MCP tool removed IPC 0.6.0, IPC dispatch retained for compat.
    # Replacement: frontprompt_inspect_elements(fields=['visible','enabled','checked','focused','in_viewport'])
    """

    model_config = ConfigDict(extra="forbid")

    kind: Literal["get_state"] = "get_state"
    schema_version: str = IPC_SCHEMA_VERSION
    pick_ids: list[str] = Field(min_length=1, max_length=50)


class GetOutlineRequest(BaseModel):
    """Read recursive child-tag outline, depth- and node-capped.

    # DEPRECATED — MCP tool removed IPC 0.6.0, IPC dispatch retained for compat.
    # Replacement: frontprompt_inspect_elements(fields=['outline']) or frontprompt_get_page_outline
    """

    model_config = ConfigDict(extra="forbid")

    kind: Literal["get_outline"] = "get_outline"
    schema_version: str = IPC_SCHEMA_VERSION
    pick_ids: list[str] = Field(min_length=1, max_length=50)
    max_depth: int = Field(default=3, ge=1, le=10)
    max_nodes: int = Field(default=200, ge=1, le=1000)


class ScreenshotElementRequest(BaseModel):
    """Element-cropped PNG screenshot with optional padding, 2MB cap."""

    model_config = ConfigDict(extra="forbid")

    kind: Literal["screenshot_element"] = "screenshot_element"
    schema_version: str = IPC_SCHEMA_VERSION
    pick_ids: list[str] = Field(min_length=1, max_length=50)
    padding: int = Field(default=8, ge=0, le=100, description="Extra px around bounding box.")


# ── Page-Level Actions (Schema 0.3.0) ────────────────────────────────────────


class GetPageInfoRequest(BaseModel):
    """Read URL, title, viewport, scroll position, readyState."""

    model_config = ConfigDict(extra="forbid")

    kind: Literal["get_page_info"] = "get_page_info"
    schema_version: str = IPC_SCHEMA_VERSION


class ScreenshotPageRequest(BaseModel):
    """Full-viewport or full-page PNG screenshot, 2MB cap."""

    model_config = ConfigDict(extra="forbid")

    kind: Literal["screenshot_page"] = "screenshot_page"
    schema_version: str = IPC_SCHEMA_VERSION
    full_page: bool = Field(default=False, description="True → full scrollable page; False → viewport only.")


class ScrollToRequest(BaseModel):
    """Scroll single pick into viewport. Returns final in_viewport + scroll position."""

    model_config = ConfigDict(extra="forbid")

    kind: Literal["scroll_to"] = "scroll_to"
    schema_version: str = IPC_SCHEMA_VERSION
    pick_id: str = Field(min_length=1)


# ── PageAnalyzer — High-level (Schema 0.4.0) ─────────────────────────────────


class GetPageOutlineRequest(BaseModel):
    """Return structural page outline (headings, links, buttons, inputs, forms,
    landmarks) as opaque OutlineRefs. Use pick_from_ref to materialise picks."""

    model_config = ConfigDict(extra="forbid")

    kind: Literal["get_page_outline"] = "get_page_outline"
    schema_version: str = IPC_SCHEMA_VERSION
    include_headings: bool = True
    include_links: bool = True
    include_buttons: bool = True
    include_inputs: bool = True
    include_forms: bool = True
    include_landmarks: bool = True
    max_items_per_kind: int = Field(default=50, ge=1, le=200)


class GetPageHtmlRequest(BaseModel):
    """Return condensed page HTML (scripts/styles/svg stripped by default)."""

    model_config = ConfigDict(extra="forbid")

    kind: Literal["get_page_html"] = "get_page_html"
    schema_version: str = IPC_SCHEMA_VERSION
    strip_scripts: bool = True
    strip_styles: bool = True
    strip_comments: bool = True
    strip_svg: bool = True
    collapse_whitespace: bool = True
    max_chars: int = Field(default=50_000, ge=1_000, le=500_000)


class PickFromRefRequest(BaseModel):
    """Materialise an OutlineRef as a Pick."""

    model_config = ConfigDict(extra="forbid")

    kind: Literal["pick_from_ref"] = "pick_from_ref"
    schema_version: str = IPC_SCHEMA_VERSION
    ref_id: str = Field(min_length=1)
    snapshot_id: str = Field(min_length=1)
    comment: str = Field(min_length=1)


class FindOneRequest(BaseModel):
    """Find exactly one element matching query; error if ambiguous or not found."""

    model_config = ConfigDict(extra="forbid")

    kind: Literal["find_one"] = "find_one"
    schema_version: str = IPC_SCHEMA_VERSION
    query: FindQuery
    comment: str = Field(min_length=1)
    parent_pick_id: str | None = None


class FindFirstRequest(BaseModel):
    """Find the first matching element; return pick + total match count."""

    model_config = ConfigDict(extra="forbid")

    kind: Literal["find_first"] = "find_first"
    schema_version: str = IPC_SCHEMA_VERSION
    query: FindQuery
    comment: str = Field(min_length=1)
    parent_pick_id: str | None = None


class FindSimilarRequest(BaseModel):
    """Find elements structurally similar to an anchor pick."""

    model_config = ConfigDict(extra="forbid")

    kind: Literal["find_similar"] = "find_similar"
    schema_version: str = IPC_SCHEMA_VERSION
    anchor_pick_id: str = Field(min_length=1)
    threshold: float = Field(default=0.7, ge=0.0, le=1.0)
    max_results: int = Field(default=50, ge=1, le=200)
    comment: str = Field(min_length=1)


class FindByRegexRequest(BaseModel):
    """Find elements whose text/attribute matches a regex pattern."""

    model_config = ConfigDict(extra="forbid")

    kind: Literal["find_by_regex"] = "find_by_regex"
    schema_version: str = IPC_SCHEMA_VERSION
    pattern: str = Field(min_length=1)
    field: Literal["text", "attribute", "any"] = "text"
    parent_pick_id: str | None = None
    comment: str = Field(min_length=1)
    limit: int = Field(default=10, ge=1, le=50)


class GetElementContextRequest(BaseModel):
    """Return structural neighbourhood of a picked element."""

    model_config = ConfigDict(extra="forbid")

    kind: Literal["get_element_context"] = "get_element_context"
    schema_version: str = IPC_SCHEMA_VERSION
    pick_id: str = Field(min_length=1)
    levels_up: int = Field(default=2, ge=1, le=10)
    sibling_radius: int = Field(default=2, ge=0, le=10)


class PickPathRequest(BaseModel):
    """Return the DOM path from root to the picked element."""

    model_config = ConfigDict(extra="forbid")

    kind: Literal["pick_path"] = "pick_path"
    schema_version: str = IPC_SCHEMA_VERSION
    pick_id: str = Field(min_length=1)


class RelocatePicksRequest(BaseModel):
    """Attempt adaptive relocation of picks after DOM changes."""

    model_config = ConfigDict(extra="forbid")

    kind: Literal["relocate_picks"] = "relocate_picks"
    schema_version: str = IPC_SCHEMA_VERSION
    pick_ids: list[str] | None = Field(
        default=None,
        description="Picks to relocate. None = all picks in state.",
    )


class InspectElementsRequest(BaseModel):
    """Unified element inspection (replaces get_text + get_attributes + get_state)."""

    model_config = ConfigDict(extra="forbid")

    kind: Literal["inspect_elements"] = "inspect_elements"
    schema_version: str = IPC_SCHEMA_VERSION
    pick_ids: list[str] = Field(min_length=1, max_length=50)
    fields: list[str] = Field(
        default_factory=lambda: ["text", "role", "visible", "enabled"],
        description="Which fields to return. See InspectField literal.",
    )


# ── Low-level escape-hatch (Schema 0.4.0) ────────────────────────────────────


class PickByXpathRequest(BaseModel):
    """Low-level XPath picker. Use CSS/text/role finders when possible."""

    model_config = ConfigDict(extra="forbid")

    kind: Literal["pick_by_xpath"] = "pick_by_xpath"
    schema_version: str = IPC_SCHEMA_VERSION
    xpath: str = Field(min_length=1)
    comment: str = Field(min_length=1)
    parent_pick_id: str | None = None
    limit: int = Field(default=10, ge=1, le=50)


class EvalJsRequest(BaseModel):
    """Execute arbitrary JavaScript. Use only when no higher-level tool applies."""

    model_config = ConfigDict(extra="forbid")

    kind: Literal["eval_js"] = "eval_js"
    schema_version: str = IPC_SCHEMA_VERSION
    expression: str = Field(min_length=1)
    pick_id_arg: str | None = Field(
        default=None,
        description="Bind live ElementHandle to `el` in JS context.",
    )
    mutating: bool = Field(
        default=False,
        description="True → invalidates snapshot after execution.",
    )


class DomPatchRequest(BaseModel):
    """Apply structured DOM mutations to a picked element."""

    model_config = ConfigDict(extra="forbid")

    kind: Literal["dom_patch"] = "dom_patch"
    schema_version: str = IPC_SCHEMA_VERSION
    pick_id: str = Field(min_length=1)
    operations: list[DomPatchOp] = Field(min_length=1)


# ── Recording read-side (Schema 0.7.0) ───────────────────────────────────────


class GetRecordingsRequest(BaseModel):
    """Return list of RecordingMeta for all recordings in this session (Schema 0.7.0).

    Returns the lightweight RecordingMeta list — without full entry timelines.
    Use GetRecordingRequest to fetch a full Recording with its entries.
    """

    model_config = ConfigDict(extra="forbid")

    kind: Literal["get_recordings"] = "get_recordings"
    schema_version: str = IPC_SCHEMA_VERSION


class GetRecordingRequest(BaseModel):
    """Return a specific recording with its full timeline (Schema 0.7.0).

    Returns the full Recording object including all TimelineEntry items.
    Returns {ok: false, error: "recording not found: <id>"} when the id is unknown.
    """

    model_config = ConfigDict(extra="forbid")

    kind: Literal["get_recording"] = "get_recording"
    schema_version: str = IPC_SCHEMA_VERSION
    recording_id: str = Field(min_length=1, description="UUID4 of the recording to retrieve.")


# ── Recording write-side + Replay execution (Schema 0.8.0) ──────────────────


class StartRecordingRequest(BaseModel):
    """Startet eine neue Aufnahme (agent-initiiert, Schema 0.8.0).

    Response: ``{ok: true, recording_id: str, name: str, started_at_ms: int}``.
    Der agent-Write-Surface für ``frontprompt show`` — bisher nur via UI möglich.
    """

    model_config = ConfigDict(extra="forbid")

    kind: Literal["start_recording"] = "start_recording"
    schema_version: str = IPC_SCHEMA_VERSION
    name: str = Field(default="New Recording", description="Benutzer-vergebener Name der Aufnahme.")
    description: str = Field(default="", description="Optionale Beschreibung.")


class StopRecordingRequest(BaseModel):
    """Beendet eine laufende Aufnahme (agent-initiiert, Schema 0.8.0).

    Response: ``{ok: true}`` oder ``{ok: false, error: "recording not found: <id>"}``.
    """

    model_config = ConfigDict(extra="forbid")

    kind: Literal["stop_recording"] = "stop_recording"
    schema_version: str = IPC_SCHEMA_VERSION
    recording_id: str = Field(min_length=1, description="UUID der zu stoppenden Aufnahme.")


class RunReplayRequest(BaseModel):
    """Führt eine Aufnahme als Replay aus (synchron, Schema 0.8.0).

    Blockiert bis der Replay abgeschlossen (oder timeout/fehler) ist.
    Response: voller ``ReplayReport``-JSON.

    ``dry_run=True`` loggt alle intendierten Aktionen ohne Ausführung.
    ``real_time=True`` hält die Zeitabstände zwischen Events ein; ``False``
    (default) führt so schnell wie möglich aus.
    """

    model_config = ConfigDict(extra="forbid")

    kind: Literal["run_replay"] = "run_replay"
    schema_version: str = IPC_SCHEMA_VERSION
    recording_id: str = Field(min_length=1, description="UUID der auszuführenden Aufnahme.")
    parameters: dict[str, str] = Field(
        default_factory=dict,
        description="Parameter-Bindings: Substitutions-Schlüssel → konkreter Wert.",
    )
    real_time: bool = Field(
        default=False,
        description="True = Timestamp-Deltas als Sleep-Intervalle einhalten; False = max speed.",
    )
    dry_run: bool = Field(
        default=False,
        description="True = alle Aktionen loggen ohne Browser-State zu ändern.",
    )


class GetReplayReportRequest(BaseModel):
    """Ruft einen gespeicherten ReplayReport ab (Schema 0.8.0).

    Response: ``ReplayReport``-JSON oder ``{ok: false, error: "replay report not found: <id>"}``.
    """

    model_config = ConfigDict(extra="forbid")

    kind: Literal["get_replay_report"] = "get_replay_report"
    schema_version: str = IPC_SCHEMA_VERSION
    replay_id: str = Field(min_length=1, description="UUID4 des Replay-Reports.")


class ListReplayReportsRequest(BaseModel):
    """Listet verfügbare ReplayReports als leichtgewichtige Meta-Einträge (Schema 0.8.0).

    ``recording_id=None`` = alle Reports dieser Session.
    Response: ``list[ReplayReportMeta]``-JSON.
    """

    model_config = ConfigDict(extra="forbid")

    kind: Literal["list_replay_reports"] = "list_replay_reports"
    schema_version: str = IPC_SCHEMA_VERSION
    recording_id: str | None = Field(
        default=None,
        description="UUID der Aufnahme zum Filtern; None = alle Reports der Session.",
    )


class AddAssertionRequest(BaseModel):
    """Fügt eine Assertion direkt via IPC zur Aufnahme hinzu (agent-write-side, Schema 0.8.0).

    Das IPC-Pendant zu :class:`~frontprompt.bridge.messages.AssertionAddedToRecordingRequested`
    (UI). Agents nutzen AddAssertionRequest; die UI sendet die bridge message.

    Response: ``{ok: true, assertion_id: str, seq: int}``.
    ``assertion_id`` ist vom Server generiert (uuid4). ``seq`` ist der zugewiesene
    monotone Sequence-Counter in der Timeline.
    """

    model_config = ConfigDict(extra="forbid")

    kind: Literal["add_assertion"] = "add_assertion"
    schema_version: str = IPC_SCHEMA_VERSION
    recording_id: str = Field(min_length=1, description="UUID der Aufnahme.")
    assertion_type: AssertionType = Field(description="Art der Assertion.")
    target: str = Field(
        default="",
        description="CSS-Selektor für element-targeted assertions; leer für url_equals.",
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
    insert_after_seq: int | None = Field(
        default=None,
        description="None = append; Integer = insert nach dem Eintrag mit diesem seq.",
    )


IpcRequest = Annotated[
    PingRequest
    | GetSnapshotRequest
    | GetPicksRequest
    | GetPickRequest
    | GetStateSummaryRequest
    | GetCommentsRequest
    | NavigateRequest
    | PickBySelectorRequest
    | PickByTextRequest
    | GetTextRequest
    | GetHtmlRequest
    | GetAttributesRequest
    | GetStateRequest
    | GetOutlineRequest
    | ScreenshotElementRequest
    | GetPageInfoRequest
    | ScreenshotPageRequest
    | ScrollToRequest
    # ── Schema 0.4.0 ──
    | GetPageOutlineRequest
    | GetPageHtmlRequest
    | PickFromRefRequest
    | FindOneRequest
    | FindFirstRequest
    | FindSimilarRequest
    | FindByRegexRequest
    | GetElementContextRequest
    | PickPathRequest
    | RelocatePicksRequest
    | InspectElementsRequest
    | PickByXpathRequest
    | EvalJsRequest
    | DomPatchRequest
    # ── Schema 0.7.0 ──
    | GetRecordingsRequest
    | GetRecordingRequest
    # ── Schema 0.8.0 ──
    | StartRecordingRequest
    | StopRecordingRequest
    | RunReplayRequest
    | GetReplayReportRequest
    | ListReplayReportsRequest
    | AddAssertionRequest,
    Field(discriminator="kind"),
]
"""Discriminated union aller IPC-requests. Server routet via ``kind``."""


# ----------------------------------------------------------------------------
# Response (Server → Client)
# ----------------------------------------------------------------------------


class IpcResponse(BaseModel):
    """Antwort vom Server. ``ok=True`` → ``data``; ``ok=False`` → ``error``.

    ``data`` ist je nach request-kind unterschiedlich strukturiert
    (StateSnapshot-dict, list[Pick-dict], etc.) — Caller weiß das anhand des
    Request-typs.
    """

    model_config = ConfigDict(extra="forbid")

    ok: bool
    data: Any | None = None
    error: str | None = None


# ── Result models (Schema 0.3.0) — used by PageController return values ─────


class TextReaderResult(BaseModel):
    model_config = ConfigDict(extra="forbid")
    pick_id: str
    error: Literal["stale_pick"] | None = None
    text: str | None = None
    accessible_name: str | None = None
    role: str | None = None
    is_visible: bool = False
    is_enabled: bool = False
    is_focused: bool = False


class HtmlReaderResult(BaseModel):
    model_config = ConfigDict(extra="forbid")
    pick_id: str
    error: Literal["stale_pick"] | None = None
    html: str | None = None
    truncated: bool = False


class AttributesReaderResult(BaseModel):
    model_config = ConfigDict(extra="forbid")
    pick_id: str
    error: Literal["stale_pick"] | None = None
    attributes: dict[str, str] = Field(default_factory=dict)


class StateReaderResult(BaseModel):
    model_config = ConfigDict(extra="forbid")
    pick_id: str
    error: Literal["stale_pick"] | None = None
    visible: bool = False
    enabled: bool = False
    checked: bool | None = None
    focused: bool = False
    in_viewport: bool = False


class OutlineNode(BaseModel):
    model_config = ConfigDict(extra="forbid")
    tag: str
    text: str | None = None
    children: list[OutlineNode] = Field(default_factory=list)


OutlineNode.model_rebuild()  # required for self-referential model


class OutlineReaderResult(BaseModel):
    model_config = ConfigDict(extra="forbid")
    pick_id: str
    error: Literal["stale_pick"] | None = None
    outline: OutlineNode | None = None
    truncated: bool = False


class ScreenshotResult(BaseModel):
    model_config = ConfigDict(extra="forbid")
    pick_id: str | None = None  # None for screenshot_page
    error: Literal["stale_pick", "screenshot_too_large"] | None = None
    image_base64: str | None = None
    format: Literal["png"] | None = None
    width: int | None = None
    height: int | None = None


class PageInfoResult(BaseModel):
    model_config = ConfigDict(extra="forbid")
    url: str
    title: str
    viewport_w: int
    viewport_h: int
    scroll_x: float
    scroll_y: float
    ready_state: str


class ScrollToResult(BaseModel):
    model_config = ConfigDict(extra="forbid")
    is_in_viewport: bool
    scroll_x: float
    scroll_y: float


class PickCreatorResult(BaseModel):
    model_config = ConfigDict(extra="forbid")
    pick_ids: list[str]
    total_matches: int
    captured: int


# ── Result models (Schema 0.4.0) ──────────────────────────────────────────────


class PageOutlineResult(BaseModel):
    """Serialisable result for GetPageOutlineRequest.

    Contains the full PageOutline. Callers use OutlineRef.ref_id +
    snapshot_id to call pick_from_ref.
    """

    model_config = ConfigDict(extra="forbid")
    outline: dict[str, Any]  # PageOutline.model_dump()


class CondensedHtmlResult(BaseModel):
    model_config = ConfigDict(extra="forbid")
    html: str
    truncated: bool = False
    original_chars: int
    stripped_chars: int


class PickFromRefResult(BaseModel):
    model_config = ConfigDict(extra="forbid")
    pick_id: str | None = None
    error: Literal["ref_expired", "ref_not_found"] | None = None


class FindOneResult(BaseModel):
    model_config = ConfigDict(extra="forbid")
    pick_id: str | None = None
    error: Literal["not_found", "ambiguous"] | None = None
    total_matches: int = 0


class FindFirstResult(BaseModel):
    model_config = ConfigDict(extra="forbid")
    pick_id: str | None = None
    error: Literal["not_found"] | None = None
    total_matches: int = 0


class FindMultiResult(BaseModel):
    """Shared result shape for find_similar, find_by_regex, pick_by_xpath."""

    model_config = ConfigDict(extra="forbid")
    pick_ids: list[str]
    total_matches: int
    captured: int


class ElementContextResult(BaseModel):
    model_config = ConfigDict(extra="forbid")
    pick_id: str
    error: Literal["stale_pick"] | None = None
    context: dict[str, Any] | None = None  # ElementContext.model_dump()


class PickPathResult(BaseModel):
    model_config = ConfigDict(extra="forbid")
    pick_id: str
    error: Literal["stale_pick"] | None = None
    path: list[dict[str, Any]] = Field(default_factory=list)


class RelocatePicksResult(BaseModel):
    model_config = ConfigDict(extra="forbid")
    results: list[dict[str, Any]]  # list[RelocationResult.model_dump()]


class InspectElementsResult(BaseModel):
    model_config = ConfigDict(extra="forbid")
    results: list[dict[str, Any]]  # list[InspectResult.model_dump()]


class EvalJsResult(BaseModel):
    model_config = ConfigDict(extra="forbid")
    ok: bool
    result: Any | None = None
    error: str | None = None


class DomPatchResult(BaseModel):
    model_config = ConfigDict(extra="forbid")
    ok: bool
    results: list[dict[str, Any]] = Field(default_factory=list)
    error: str | None = None


# ── Result models (Schema 0.6.0) ──────────────────────────────────────────────


class AnnotationEntry(BaseModel):
    """Compact pick annotation shape returned by GetCommentsRequest.

    One entry per Pick that has a non-empty ``comment``. Provides the minimal
    locator (selector + url) so agents can correlate a comment with a page
    element without needing a full snapshot.
    """

    model_config = ConfigDict(extra="forbid")

    pick_id: str
    comment: str
    selector: str
    url: str


# ── Result models (Schema 0.8.0) ──────────────────────────────────────────────


class ReplayReportMeta(BaseModel):
    """Leichtgewichtige Zusammenfassung eines Replay-Reports (Schema 0.8.0).

    Returned by :class:`ListReplayReportsRequest` — keine ``step_results``
    (die sind im vollen :class:`~frontprompt.state.state.ReplayReport` via
    :class:`GetReplayReportRequest`). Agents nutzen dies für eine schnelle Übersicht.
    """

    model_config = ConfigDict(extra="forbid")

    replay_id: str = Field(description="UUID des Replay-Runs.")
    recording_id: str = Field(description="UUID der zugrundeliegenden Aufnahme.")
    status: ReplayStatus = Field(description="Abschluss-Status des Replays.")
    started_at_ms: int = Field(description="Epoch ms bei Replay-Start.")
    ended_at_ms: int | None = Field(
        default=None,
        description="Epoch ms bei Replay-Ende; None für aborted replays.",
    )
    step_count: int = Field(description="Gesamtanzahl der Steps (alle Timeline-Einträge).")
    passed_assertions: int = Field(description="Anzahl bestandener Assertions.")
    failed_assertions: int = Field(description="Anzahl fehlgeschlagener Assertions.")


__all__ = [
    "IPC_SCHEMA_VERSION",
    "AnnotationEntry",
    "AttributesReaderResult",
    "CondensedHtmlResult",
    "DomPatchRequest",
    "DomPatchResult",
    "ElementContextResult",
    "EvalJsRequest",
    "EvalJsResult",
    "FindByRegexRequest",
    "FindFirstRequest",
    "FindFirstResult",
    "FindMultiResult",
    "FindOneRequest",
    "FindOneResult",
    "FindSimilarRequest",
    "GetAttributesRequest",
    "GetCommentsRequest",
    "GetElementContextRequest",
    "GetHtmlRequest",
    "GetOutlineRequest",
    "GetPageHtmlRequest",
    "GetPageInfoRequest",
    "GetPageOutlineRequest",
    "GetPickRequest",
    "GetPicksRequest",
    "GetRecordingRequest",
    "GetRecordingsRequest",
    "GetSnapshotRequest",
    "GetStateRequest",
    "GetStateSummaryRequest",
    "GetTextRequest",
    "HtmlReaderResult",
    "InspectElementsRequest",
    "InspectElementsResult",
    "IpcRequest",
    "IpcResponse",
    "NavigateRequest",
    "OutlineNode",
    "OutlineReaderResult",
    "PageInfoResult",
    "PageOutlineResult",
    "PickBySelectorRequest",
    "PickByTextRequest",
    "PickByXpathRequest",
    "PickCreatorResult",
    "PickFromRefRequest",
    "PickFromRefResult",
    "PickPathRequest",
    "PickPathResult",
    "PingRequest",
    "RelocatePicksRequest",
    "RelocatePicksResult",
    "ScreenshotElementRequest",
    "ScreenshotPageRequest",
    "ScreenshotResult",
    "ScrollToRequest",
    "ScrollToResult",
    "StateReaderResult",
    "TextReaderResult",
    # Schema 0.8.0 — replay write-side
    "AddAssertionRequest",
    "GetReplayReportRequest",
    "ListReplayReportsRequest",
    "ReplayReportMeta",
    "RunReplayRequest",
    "StartRecordingRequest",
    "StopRecordingRequest",
]
