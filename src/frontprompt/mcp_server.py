"""MCP stdio server — 31 tools (1 diagnostic + 7 read-only v0.1+0.2+0.6 + 6 scout v0.3.0 + 14 refinement v0.4.0 + 1 state-summary v0.5.0 + 2 recording v0.7.0).

Each MCP-daemon process owns exactly one browser-session (spawned as
``frontprompt show`` child). This module exposes 29 MCP tools that
operate exclusively on that owned session, routing through the existing
:func:`frontprompt.ipc.query` Unix-Socket-IPC client.

The browser is spawned **lazily on first tool-call** via :class:`SessionProvider`
abstraction — daemon start no longer triggers a chromium window; only an actual
tool invocation does. The provider also handles teardown on daemon shutdown.

Read-only tools (Phase 1, Schema 0.2.0):

- ``frontprompt_ping`` — liveness check on the IPC socket
- ``frontprompt_get_session_info`` — cached SessionMetadata (no IPC roundtrip)
- ``frontprompt_get_state_summary`` — small navigable overview (counts + grouping); start here
- ``frontprompt_get_snapshot`` — full StateSnapshot (panel + inspector + …); the firehose
- ``frontprompt_get_picks`` — list of all Picks
- ``frontprompt_get_pick`` — single Pick by UUID
- ``frontprompt_navigate`` — navigate the owned browser to a URL

Scout tools (Phase 2, Schema 0.3.0):

- ``frontprompt_pick_by_selector`` — create N Picks per CSS-selector match
- ``frontprompt_pick_by_text`` — create N Picks by visible text (+ optional role)
- ``frontprompt_screenshot_element`` — capture PNG screenshot of each Pick's element
- ``frontprompt_get_page_info`` — read page-level metadata
- ``frontprompt_screenshot_page`` — capture PNG screenshot of the current page
- ``frontprompt_scroll_to`` — scroll a single Pick into the viewport

Refinement tools (v0.4.0, Schema 0.4.0):

- ``frontprompt_get_page_outline`` — structural page outline (headings/links/buttons/inputs/forms/landmarks)
- ``frontprompt_get_page_html`` — condensed page HTML (scripts/styles stripped)
- ``frontprompt_pick_from_ref`` — materialise an OutlineRef as a Pick
- ``frontprompt_find_one`` — find exactly one element; error on ambiguous/not-found
- ``frontprompt_find_first`` — find first element + total match count
- ``frontprompt_find_similar`` — find structurally similar elements
- ``frontprompt_find_by_regex`` — find elements by regex pattern on text/attributes
- ``frontprompt_get_element_context`` — ancestors/siblings/landmark context
- ``frontprompt_pick_path`` — DOM path from root to picked element
- ``frontprompt_relocate_picks`` — adaptive relocation after DOM changes
- ``frontprompt_inspect_elements`` — unified inspection (replaces deprecated readers)
- ``frontprompt_eval_js`` — execute arbitrary JavaScript (escape hatch)
- ``frontprompt_dom_patch`` — structured DOM mutations on a picked element
- ``frontprompt_pick_by_xpath`` — XPath-based picker (escape hatch)

Diagnostic tools (Phase 1):

- ``fp_status`` — structured healthcheck: schema_version, phase, capabilities_available,
  capabilities_deferred. Extension point: register additional providers via
  ``from frontprompt.mcp_server import _DIAGNOSTICS; _DIAGNOSTICS.register(provider)``.

See ARCHITECTURE.md for the tool enumeration and their IPC-mapping.
"""

from __future__ import annotations

import json
import os
from pathlib import Path
from typing import Any, Protocol, runtime_checkable

import anyio
import anyio.abc
import structlog
from anyio.streams.memory import MemoryObjectReceiveStream, MemoryObjectSendStream
from mcp import types
from mcp.server import NotificationOptions, Server
from mcp.server.models import InitializationOptions
from mcp.server.stdio import stdio_server
from mcp.shared.message import SessionMessage

from frontprompt.bridge.messages import SCHEMA_VERSION
from frontprompt.ipc import (
    DomPatchRequest,
    EvalJsRequest,
    FindByRegexRequest,
    FindFirstRequest,
    FindOneRequest,
    FindSimilarRequest,
    GetCommentsRequest,
    GetElementContextRequest,
    GetPageHtmlRequest,
    GetPageInfoRequest,
    GetPageOutlineRequest,
    GetPickRequest,
    GetPicksRequest,
    GetRecordingRequest,
    GetRecordingsRequest,
    GetSnapshotRequest,
    GetStateSummaryRequest,
    InspectElementsRequest,
    IpcConnectError,
    NavigateRequest,
    PickBySelectorRequest,
    PickByTextRequest,
    PickByXpathRequest,
    PickFromRefRequest,
    PickPathRequest,
    PingRequest,
    RelocatePicksRequest,
    ScreenshotElementRequest,
    ScreenshotPageRequest,
    ScrollToRequest,
    SessionMetadata,
    query,
)
from frontprompt.ipc.protocol import IpcRequest
from frontprompt.mcp_spawn import (
    ShowSpawnError,
    spawn_show_child_unmanaged,
    terminate_show_child,
)

_LOG: structlog.stdlib.BoundLogger = structlog.get_logger("frontprompt.mcp")


# ----------------------------------------------------------------------------
# DiagnosticsRegistry — extension point for internal healthcheck providers.
# Future callers: from frontprompt.mcp_server import _DIAGNOSTICS; _DIAGNOSTICS.register(p)
# ----------------------------------------------------------------------------


@runtime_checkable
class DiagnosticsProvider(Protocol):
    """Protocol for a diagnostics provider that contributes to fp_status output.

    Implement ``collect()`` to return a flat dict of JSON-serializable values.
    Register via ``_DIAGNOSTICS.register(provider)``.
    """

    def collect(self) -> dict[str, object]:
        """Return a flat dict of diagnostic key→value pairs."""
        ...


class DiagnosticsRegistry:
    """Registry of :class:`DiagnosticsProvider` instances powering ``fp_status``.

    Built-in fixed fields (``schema_version``, ``build_timestamp``) are always
    present. Registered providers contribute additional fields; last-writer-wins
    on key collisions.
    """

    def __init__(self) -> None:
        self._providers: list[DiagnosticsProvider] = []

    def register(self, provider: DiagnosticsProvider) -> None:
        """Add a provider. Future ``collect_all()`` calls will include its output."""
        self._providers.append(provider)

    def collect_all(self) -> dict[str, object]:
        """Merge all provider outputs into a single flat dict.

        Fixed built-in fields come first; provider fields are merged in
        registration order (last-writer-wins on key collisions).
        """
        result: dict[str, object] = {
            "schema_version": SCHEMA_VERSION,
            "build_timestamp": os.environ.get("FRONTPROMPT_BUILD_SESSION", "unknown"),
        }
        for provider in self._providers:
            result.update(provider.collect())
        return result


class _PhaseStatusProvider:
    """Built-in provider reporting Phase-1 capability boundaries."""

    def collect(self) -> dict[str, object]:
        return {
            "phase": "phase-1",
            "capabilities_available": ["fp_status"],
            "capabilities_deferred": ["navigate", "act", "screenshot", "query"],
        }


#: Module-level DiagnosticsRegistry singleton.
#: Register additional providers to extend fp_status output:
#:   from frontprompt.mcp_server import _DIAGNOSTICS
#:   _DIAGNOSTICS.register(my_provider)
_DIAGNOSTICS = DiagnosticsRegistry()
_DIAGNOSTICS.register(_PhaseStatusProvider())


_SERVER_NAME = "frontprompt"
_SERVER_VERSION = "0.0.1"


# ----------------------------------------------------------------------------
# SessionProvider — abstracts when/how the daemon's browser-session is born.
# ----------------------------------------------------------------------------


class SessionProvider(Protocol):
    """Yields the daemon's :class:`SessionMetadata`, lazily if needed."""

    async def get(self) -> SessionMetadata:
        """Return the session metadata; may spawn the browser child on first call."""
        ...

    async def close(self) -> None:
        """Terminate any spawned browser-child. Idempotent."""
        ...


class StaticSessionProvider:
    """Provider backed by a pre-existing :class:`SessionMetadata`. Used in tests.

    No spawn, no teardown — the test fixture owns the underlying socket.
    """

    def __init__(self, session_info: SessionMetadata) -> None:
        self._session_info = session_info

    async def get(self) -> SessionMetadata:
        return self._session_info

    async def close(self) -> None:
        return None


class LazyBrowserSessionProvider:
    """Spawns the show-child on first :meth:`get`, caches it, terminates on :meth:`close`.

    Lifetime model: the daemon process owns at most one browser-session.
    Spawning is deferred until the first MCP-tool-call so that simply registering
    the plugin in Claude Code does not open a chromium window — the browser
    appears only when the user actually invokes a frontprompt tool.

    Thread/concurrency safe via an internal :class:`anyio.Lock`.
    """

    def __init__(self, start_url: str) -> None:
        self._start_url = start_url
        self._lock = anyio.Lock()
        self._session_info: SessionMetadata | None = None
        self._process: anyio.abc.Process | None = None

    async def get(self) -> SessionMetadata:
        async with self._lock:
            if self._session_info is None:
                _LOG.info("mcp.session_provider.spawning_on_first_get", start_url=self._start_url)
                self._process, self._session_info = await spawn_show_child_unmanaged(self._start_url)
            return self._session_info

    async def close(self) -> None:
        async with self._lock:
            if self._process is not None:
                _LOG.info("mcp.session_provider.closing", child_pid=self._process.pid)
                await terminate_show_child(self._process)
                self._process = None
                self._session_info = None


# ----------------------------------------------------------------------------
# Tool definitions + IPC dispatch
# ----------------------------------------------------------------------------


def _build_tool_list() -> list[types.Tool]:
    """31 tools — 1 diagnostic + 7 read-only v0.1+0.2+0.6 + 6 scout v0.3.0 + 14 refinement v0.4.0 + 1 state-summary v0.5.0 + 2 recording v0.7.0.

    5 deprecated v0.3.0 element-readers removed (IPC 0.6.0): get_text, get_html,
    get_attributes, get_state, get_outline. Replacement: frontprompt_inspect_elements.
    """
    empty_input: dict[str, Any] = {
        "type": "object",
        "properties": {},
        "additionalProperties": False,
    }
    return [
        # ── Diagnostic tools (Phase 1) ─────────────────────────────────────────
        types.Tool(
            name="fp_status",
            description=(
                "Phase-1 server healthcheck and diagnostic surface. "
                "Returns a JSON object with: schema_version (matches bridge.messages.SCHEMA_VERSION), "
                "build_timestamp (FRONTPROMPT_BUILD_SESSION env or 'unknown'), "
                "phase (always 'phase-1'), "
                "capabilities_available (tools live in this phase), "
                "capabilities_deferred (business-domain tools reserved for Phase 2: "
                "navigate, act, screenshot, query). "
                "Additional providers can be registered via _DIAGNOSTICS.register(provider) "
                "to extend this output with state-manager, bridge-connection, and session-health data."
            ),
            inputSchema=empty_input,
        ),
        types.Tool(
            name="frontprompt_ping",
            description=(
                "Liveness check on the browser session owned by this MCP server process. "
                "Returns {pong: true} when the IPC socket is alive."
            ),
            inputSchema=empty_input,
        ),
        types.Tool(
            name="frontprompt_get_session_info",
            description=(
                "Return metadata about the browser session owned by this MCP server process: "
                "session_id, pid, url, started_at_iso, socket_path. Note: triggers a lazy "
                "browser spawn on first call (a chromium window will open if it has not yet)."
            ),
            inputSchema=empty_input,
        ),
        types.Tool(
            name="frontprompt_get_state_summary",
            description=(
                "Small, navigable OVERVIEW of the owned browser session's state — counts + "
                "grouping, NOT the full payload. Start here, then drill down. Returns "
                "{schema_version, current_session_id, active_pick_id, active_region_id, "
                "counts:{picks,regions,relations}, by_origin_session:[{session,picks,regions,relations}], "
                "by_hostname:[{hostname,picks}], owned_vs_foreign:{owned,foreign}}. "
                "Hostnames are derived from each Pick's URL (data: URLs collapse to 'data:', "
                "never the blob); owned-vs-foreign compares each pick's origin_session to the "
                "current session. Use frontprompt_get_snapshot / frontprompt_get_picks / "
                "frontprompt_get_pick to drill into a specific slice."
            ),
            inputSchema=empty_input,
        ),
        types.Tool(
            name="frontprompt_get_comments",
            description=(
                "Return all Picks that have a non-empty comment field as a compact list. "
                "Each entry contains {pick_id, comment, selector, url} — the minimal locator "
                "needed to correlate a comment with a page element without loading a full snapshot. "
                "Picks with an empty comment are excluded. Programmatic picks auto-suffix "
                "'[match i/N]' which is non-empty; agents can distinguish human-authored vs "
                "programmatic by checking for that suffix. "
                "Use this instead of frontprompt_get_snapshot when you only want to read "
                "what the human annotated."
            ),
            inputSchema=empty_input,
        ),
        types.Tool(
            name="frontprompt_get_snapshot",
            description=(
                "Full StateSnapshot (panel + inspector + relations + regions) of the owned "
                "browser session. Returns Pydantic-serialized JSON. NOTE: this is the full "
                "firehose — for an overview, prefer frontprompt_get_state_summary and drill "
                "down from there."
            ),
            inputSchema=empty_input,
        ),
        types.Tool(
            name="frontprompt_get_picks",
            description=(
                "List all Picks (DOM-element annotations placed in the overlay) of the owned "
                "browser session. Returns a JSON array of Pick objects."
            ),
            inputSchema=empty_input,
        ),
        types.Tool(
            name="frontprompt_get_pick",
            description=("Return a single Pick by its UUID. Returns an error if pick_id is unknown."),
            inputSchema={
                "type": "object",
                "properties": {
                    "pick_id": {
                        "type": "string",
                        "description": "UUID4 of the pick to retrieve (see Pick.pick_id).",
                    },
                },
                "required": ["pick_id"],
                "additionalProperties": False,
            },
        ),
        types.Tool(
            name="frontprompt_navigate",
            description=(
                "Navigate the owned browser session to a URL. Waits for the page's load "
                "event before returning. Picks and Annotations survive cross-origin "
                "navigation (the overlay is automatically re-hydrated from the "
                "authoritative StateSnapshot). Returns "
                "{navigated_to: str, title: str}."
            ),
            inputSchema={
                "type": "object",
                "properties": {
                    "url": {
                        "type": "string",
                        "description": "Target URL including scheme (e.g. https://example.com).",
                        "minLength": 1,
                    },
                },
                "required": ["url"],
                "additionalProperties": False,
            },
        ),
        # ── Scout tools v0.3.0 — Pick-Creators ────────────────────────────────
        types.Tool(
            name="frontprompt_pick_by_selector",
            description=(
                "Create N single Picks per CSS-selector match (capped to limit, default 10, max 50). "
                "Each Pick is persisted with comment auto-suffixed '[match i/N]'. "
                "Use parent_pick_id to scope the query to a subtree; if the parent is stale, returns error. "
                "Returns {pick_ids: list[str], total_matches: int, captured: int}."
            ),
            inputSchema={
                "type": "object",
                "properties": {
                    "selector": {"type": "string", "minLength": 1, "description": "CSS selector."},
                    "comment": {
                        "type": "string",
                        "minLength": 1,
                        "description": "Base comment (auto-suffixed per match).",
                    },
                    "parent_pick_id": {
                        "type": "string",
                        "description": "Optional: scope query to subtree of this pick.",
                    },
                    "limit": {"type": "integer", "minimum": 1, "maximum": 50, "default": 10},
                },
                "required": ["selector", "comment"],
                "additionalProperties": False,
            },
        ),
        types.Tool(
            name="frontprompt_pick_by_text",
            description=(
                "Create N single Picks by visible text content. Optional role filter is AND-combined "
                "(both text AND role must match). Returns {pick_ids, total_matches, captured}. "
                "Each resulting Pick carries real viewport coordinates in rect, obtained via a "
                "Playwright bounding-box roundtrip using a path-disambiguated CSS selector."
            ),
            inputSchema={
                "type": "object",
                "properties": {
                    "text": {"type": "string", "minLength": 1},
                    "role": {"type": "string", "description": "ARIA role (optional, AND-combined with text)."},
                    "comment": {"type": "string", "minLength": 1},
                    "parent_pick_id": {"type": "string"},
                    "limit": {"type": "integer", "minimum": 1, "maximum": 50, "default": 10},
                },
                "required": ["text", "comment"],
                "additionalProperties": False,
            },
        ),
        types.Tool(
            name="frontprompt_screenshot_element",
            description=(
                "Capture PNG screenshot of each Pick's element (+ optional padding). "
                "Returns list of {pick_id, image_base64, format, width, height} or "
                "{error: stale_pick|screenshot_too_large} per entry. Cap: 2MB per image."
            ),
            inputSchema={
                "type": "object",
                "properties": {
                    "pick_ids": {"type": "array", "items": {"type": "string"}, "minItems": 1, "maxItems": 50},
                    "padding": {"type": "integer", "minimum": 0, "maximum": 100, "default": 8},
                },
                "required": ["pick_ids"],
                "additionalProperties": False,
            },
        ),
        # ── Scout tools v0.3.0 — Page-Level ───────────────────────────────────
        types.Tool(
            name="frontprompt_get_page_info",
            description=(
                "Read page-level metadata: url, title, viewport dimensions, scroll position, ready_state. "
                "Use after navigate to orient."
            ),
            inputSchema=empty_input,
        ),
        types.Tool(
            name="frontprompt_screenshot_page",
            description=(
                "Capture PNG screenshot of the current page. "
                "full_page=true captures the entire scrollable document. Cap: 2MB."
            ),
            inputSchema={
                "type": "object",
                "properties": {
                    "full_page": {"type": "boolean", "default": False},
                },
                "additionalProperties": False,
            },
        ),
        types.Tool(
            name="frontprompt_scroll_to",
            description=(
                "Scroll a single Pick's element into the viewport. "
                "Returns {is_in_viewport: bool, scroll_x: float, scroll_y: float}. "
                "Takes a single pick_id (not a list — viewport has one scroll position)."
            ),
            inputSchema={
                "type": "object",
                "properties": {
                    "pick_id": {"type": "string", "minLength": 1},
                },
                "required": ["pick_id"],
                "additionalProperties": False,
            },
        ),
        # ── Refinement tools v0.4.0 ─────────────────────────────────────────────────
        types.Tool(
            name="frontprompt_get_page_outline",
            description=(
                "Return structural page outline (headings, links, buttons, inputs, forms, landmarks) "
                "as opaque OutlineRefs. Use frontprompt_pick_from_ref to materialise any entry into a Pick. "
                "OutlineRefs are valid until the next snapshot or mutating operation, or for 30 seconds — "
                "afterwards they are invalidated. Call frontprompt_pick_from_ref immediately after this tool, "
                "before any other tool call, to avoid ref_not_found."
            ),
            inputSchema={
                "type": "object",
                "properties": {
                    "include_headings": {"type": "boolean", "default": True},
                    "include_links": {"type": "boolean", "default": True},
                    "include_buttons": {"type": "boolean", "default": True},
                    "include_inputs": {"type": "boolean", "default": True},
                    "include_forms": {"type": "boolean", "default": True},
                    "include_landmarks": {"type": "boolean", "default": True},
                    "max_items_per_kind": {
                        "type": "integer",
                        "default": 50,
                        "minimum": 1,
                        "maximum": 200,
                    },
                },
                "additionalProperties": False,
            },
        ),
        types.Tool(
            name="frontprompt_get_page_html",
            description=(
                "Return semantically-condensed page HTML. Decorative wrapper tags "
                "(div, span, and other non-semantic elements) are unwrapped while "
                "their text and any allowlisted children are kept; allowlisted "
                "elements retain only their semantic attributes. The injected "
                "frontprompt overlay host is always stripped — overlay artefacts "
                "never reach the output. Legacy regex-strip toggles "
                "(scripts, styles, svg, comments, whitespace) remain configurable. "
                "Returns {html, truncated, original_chars, stripped_chars}."
            ),
            inputSchema={
                "type": "object",
                "properties": {
                    "strip_scripts": {"type": "boolean", "default": True},
                    "strip_styles": {"type": "boolean", "default": True},
                    "strip_comments": {"type": "boolean", "default": True},
                    "strip_svg": {"type": "boolean", "default": True},
                    "collapse_whitespace": {"type": "boolean", "default": True},
                    "max_chars": {
                        "type": "integer",
                        "default": 50000,
                        "minimum": 1000,
                        "maximum": 500000,
                    },
                },
                "additionalProperties": False,
            },
        ),
        types.Tool(
            name="frontprompt_pick_from_ref",
            description=(
                "Materialise an OutlineRef (from frontprompt_get_page_outline) as a Pick. "
                "Returns {pick_id} or {error: 'ref_expired'|'ref_not_found'}. "
                "OutlineRefs are invalidated by: (a) a new snapshot via frontprompt_get_page_outline, "
                "frontprompt_get_snapshot, or frontprompt_get_page_html; (b) mutating operations — "
                "frontprompt_dom_patch or frontprompt_eval_js with mutating=true; (c) the 30-second TTL. "
                "Recommended pattern: call this tool immediately after frontprompt_get_page_outline."
            ),
            inputSchema={
                "type": "object",
                "properties": {
                    "ref_id": {"type": "string", "minLength": 1},
                    "snapshot_id": {"type": "string", "minLength": 1},
                    "comment": {"type": "string", "minLength": 1},
                },
                "required": ["ref_id", "snapshot_id", "comment"],
                "additionalProperties": False,
            },
        ),
        types.Tool(
            name="frontprompt_find_one",
            description=(
                "Find exactly one element matching a query. "
                "Returns {pick_id} or {error: 'not_found'|'ambiguous', total_matches?}. "
                "The resulting Pick carries real viewport coordinates in rect, obtained via a "
                "Playwright bounding-box roundtrip using a path-disambiguated CSS selector."
            ),
            inputSchema={
                "type": "object",
                "properties": {
                    "query": {
                        "type": "object",
                        "description": "FindQuery: {kind: 'text'|'css'|'role'|'label'|'placeholder'|'alt', ...}",
                    },
                    "comment": {"type": "string", "minLength": 1},
                    "parent_pick_id": {"type": "string"},
                },
                "required": ["query", "comment"],
                "additionalProperties": False,
            },
        ),
        types.Tool(
            name="frontprompt_find_first",
            description=(
                "Find the first element matching a query; returns pick_id + total match count. "
                "Returns {pick_id, total_matches} or {error: 'not_found'}. "
                "The resulting Pick carries real viewport coordinates in rect, obtained via a "
                "Playwright bounding-box roundtrip using a path-disambiguated CSS selector."
            ),
            inputSchema={
                "type": "object",
                "properties": {
                    "query": {
                        "type": "object",
                        "description": "FindQuery: {kind: 'text'|'css'|'role'|'label'|'placeholder'|'alt', ...}",
                    },
                    "comment": {"type": "string", "minLength": 1},
                    "parent_pick_id": {"type": "string"},
                },
                "required": ["query", "comment"],
                "additionalProperties": False,
            },
        ),
        types.Tool(
            name="frontprompt_find_similar",
            description=(
                "Find elements structurally similar to an anchor pick using the scrapling DOM-fingerprint "
                "relocate engine. Threshold-filtered: matches above the threshold cutoff are returned, "
                "below are dropped — no continuous similarity scores are produced. "
                "Returns {pick_ids, total_matches, captured}. "
                "Each resulting Pick carries real viewport coordinates in rect, obtained via a "
                "Playwright bounding-box roundtrip using a path-disambiguated CSS selector; "
                "max_results=N triggers N Playwright roundtrips."
            ),
            inputSchema={
                "type": "object",
                "properties": {
                    "anchor_pick_id": {"type": "string", "minLength": 1},
                    "comment": {"type": "string", "minLength": 1},
                    "threshold": {"type": "number", "default": 0.7, "minimum": 0.0, "maximum": 1.0},
                    "max_results": {"type": "integer", "default": 50, "minimum": 1, "maximum": 200},
                },
                "required": ["anchor_pick_id", "comment"],
                "additionalProperties": False,
            },
        ),
        types.Tool(
            name="frontprompt_find_by_regex",
            description=(
                "Find elements whose text/attribute matches a regex pattern. "
                "Returns {pick_ids, total_matches, captured}. "
                "Each resulting Pick carries real viewport coordinates in rect, obtained via a "
                "Playwright bounding-box roundtrip using a path-disambiguated CSS selector."
            ),
            inputSchema={
                "type": "object",
                "properties": {
                    "pattern": {"type": "string", "minLength": 1},
                    "comment": {"type": "string", "minLength": 1},
                    "field": {
                        "type": "string",
                        "enum": ["text", "attribute", "any"],
                        "default": "text",
                    },
                    "parent_pick_id": {"type": "string"},
                    "limit": {"type": "integer", "default": 10, "minimum": 1, "maximum": 50},
                },
                "required": ["pattern", "comment"],
                "additionalProperties": False,
            },
        ),
        types.Tool(
            name="frontprompt_get_element_context",
            description=(
                "Return structural neighbourhood of a picked element: ancestors, siblings, landmark context. "
                "Returns {ancestors, prev_sibling, next_sibling, in_form, in_table, semantic_landmark}."
            ),
            inputSchema={
                "type": "object",
                "properties": {
                    "pick_id": {"type": "string", "minLength": 1},
                    "levels_up": {"type": "integer", "default": 2, "minimum": 1, "maximum": 5},
                    "sibling_radius": {"type": "integer", "default": 2, "minimum": 0, "maximum": 5},
                },
                "required": ["pick_id"],
                "additionalProperties": False,
            },
        ),
        types.Tool(
            name="frontprompt_pick_path",
            description=(
                "Return the DOM path from root to the picked element. "
                "Returns {path: [{tag, role?, text_excerpt?, semantic_landmark?}, ...]}."
            ),
            inputSchema={
                "type": "object",
                "properties": {
                    "pick_id": {"type": "string", "minLength": 1},
                },
                "required": ["pick_id"],
                "additionalProperties": False,
            },
        ),
        types.Tool(
            name="frontprompt_relocate_picks",
            description=(
                "Attempt adaptive relocation of picks after DOM changes. "
                "Returns list of {pick_id, status: 'alive'|'recovered'|'stale', new_selector?, similarity?}."
            ),
            inputSchema={
                "type": "object",
                "properties": {
                    "pick_ids": {
                        "type": "array",
                        "items": {"type": "string"},
                        "description": "Picks to relocate. Omit to relocate all current picks.",
                    },
                },
                "additionalProperties": False,
            },
        ),
        types.Tool(
            name="frontprompt_inspect_elements",
            description=(
                "Unified element inspection (replaces deprecated get_text/get_attributes/get_state/get_html/get_outline). "
                "Returns per-pick dict of requested fields. Valid fields: text, role, visible, enabled, "
                "checked, focused, in_viewport, accessible_name, attributes, html, outline."
            ),
            inputSchema={
                "type": "object",
                "properties": {
                    "pick_ids": {
                        "type": "array",
                        "items": {"type": "string"},
                        "minItems": 1,
                        "maxItems": 50,
                    },
                    "fields": {
                        "type": "array",
                        "items": {
                            "type": "string",
                            "enum": [
                                "text",
                                "role",
                                "visible",
                                "enabled",
                                "checked",
                                "focused",
                                "in_viewport",
                                "accessible_name",
                                "attributes",
                                "html",
                                "outline",
                            ],
                        },
                        "default": ["text", "role", "visible", "enabled"],
                    },
                },
                "required": ["pick_ids"],
                "additionalProperties": False,
            },
        ),
        types.Tool(
            name="frontprompt_eval_js",
            description=(
                "Execute arbitrary JavaScript in the page context. Use only when no higher-level tool applies. "
                "Optionally binds a pick's live ElementHandle to `el` in the JS context. "
                "Returns {result: Any, ok: bool, error?: str}."
            ),
            inputSchema={
                "type": "object",
                "properties": {
                    "expression": {"type": "string", "minLength": 1},
                    "pick_id_arg": {
                        "type": "string",
                        "description": "Bind live ElementHandle to `el` in JS context.",
                    },
                    "mutating": {
                        "type": "boolean",
                        "default": False,
                        "description": "True → snapshot is invalidated after execution.",
                    },
                },
                "required": ["expression"],
                "additionalProperties": False,
            },
        ),
        types.Tool(
            name="frontprompt_dom_patch",
            description=(
                "Apply structured DOM mutations to a picked element. Always invalidates snapshot. "
                "Returns {ok, results: [{op, ok, error?}]}."
            ),
            inputSchema={
                "type": "object",
                "properties": {
                    "pick_id": {"type": "string", "minLength": 1},
                    "operations": {
                        "type": "array",
                        "items": {
                            "type": "object",
                            "properties": {
                                "op": {"type": "string"},
                            },
                            "required": ["op"],
                        },
                        "minItems": 1,
                    },
                },
                "required": ["pick_id", "operations"],
                "additionalProperties": False,
            },
        ),
        types.Tool(
            name="frontprompt_pick_by_xpath",
            description=(
                "Low-level XPath picker. Use CSS/text/role finders when possible. "
                "Returns {pick_ids, total_matches, captured}."
            ),
            inputSchema={
                "type": "object",
                "properties": {
                    "xpath": {"type": "string", "minLength": 1},
                    "comment": {"type": "string", "minLength": 1},
                    "parent_pick_id": {"type": "string"},
                    "limit": {"type": "integer", "default": 10, "minimum": 1, "maximum": 50},
                },
                "required": ["xpath", "comment"],
                "additionalProperties": False,
            },
        ),
        # ── Recording read-side v0.7.0 ───────────────────────────────────────────
        types.Tool(
            name="frontprompt_list_recordings",
            description=(
                "List all recordings in this session. Returns array of "
                "RecordingMeta objects: {recording_id, name, description, status, started_at_ms, "
                "ended_at_ms, entry_count}. Use frontprompt_get_recording to fetch the full "
                "timeline of a specific recording."
            ),
            inputSchema=empty_input,
        ),
        types.Tool(
            name="frontprompt_get_recording",
            description=(
                "Return a specific recording with its full timeline. Returns "
                "Recording object: {recording_id, name, status, entries: [{kind, seq, timestamp_ms, ...}]}. "
                "entry kinds: page_event (click/pointerdown/keydown), pick_ref, region_ref, relation_ref, "
                "navigation. Replay-ready: page_event entries carry sufficient data to reconstruct IpcRequest "
                "sequences for future replay agents."
            ),
            inputSchema={
                "type": "object",
                "properties": {
                    "recording_id": {
                        "type": "string",
                        "description": "UUID4 of the recording to retrieve.",
                        "minLength": 1,
                    },
                },
                "required": ["recording_id"],
                "additionalProperties": False,
            },
        ),
    ]


def _build_ipc_request(name: str, arguments: dict[str, Any]) -> IpcRequest:
    if name == "frontprompt_ping":
        return PingRequest()
    if name == "frontprompt_get_state_summary":
        return GetStateSummaryRequest()
    if name == "frontprompt_get_comments":
        return GetCommentsRequest()
    if name == "frontprompt_get_snapshot":
        return GetSnapshotRequest()
    if name == "frontprompt_get_picks":
        return GetPicksRequest()
    if name == "frontprompt_get_pick":
        pick_id = arguments.get("pick_id")
        if not isinstance(pick_id, str) or not pick_id:
            raise ValueError("pick_id is required and must be a non-empty string")
        return GetPickRequest(pick_id=pick_id)
    if name == "frontprompt_navigate":
        url = arguments.get("url")
        if not isinstance(url, str) or not url:
            raise ValueError("url is required and must be a non-empty string")
        return NavigateRequest(url=url)
    if name == "frontprompt_pick_by_selector":
        return PickBySelectorRequest(
            selector=arguments["selector"],
            comment=arguments["comment"],
            parent_pick_id=arguments.get("parent_pick_id"),
            limit=arguments.get("limit", 10),
        )
    if name == "frontprompt_pick_by_text":
        return PickByTextRequest(
            text=arguments["text"],
            role=arguments.get("role"),
            comment=arguments["comment"],
            parent_pick_id=arguments.get("parent_pick_id"),
            limit=arguments.get("limit", 10),
        )
    if name == "frontprompt_screenshot_element":
        return ScreenshotElementRequest(
            pick_ids=arguments["pick_ids"],
            padding=arguments.get("padding", 8),
        )
    if name == "frontprompt_get_page_info":
        return GetPageInfoRequest()
    if name == "frontprompt_screenshot_page":
        return ScreenshotPageRequest(full_page=arguments.get("full_page", False))
    if name == "frontprompt_scroll_to":
        pick_id = arguments.get("pick_id")
        if not isinstance(pick_id, str) or not pick_id:
            raise ValueError("pick_id is required and must be a non-empty string")
        return ScrollToRequest(pick_id=pick_id)
    # ── Refinement tools v0.4.0 ──────────────────────────────────────────────
    if name == "frontprompt_get_page_outline":
        # include_text removed (not in GetPageOutlineRequest schema, extra="forbid")
        return GetPageOutlineRequest(
            include_links=arguments.get("include_links", True),
            include_buttons=arguments.get("include_buttons", True),
            include_inputs=arguments.get("include_inputs", True),
            include_forms=arguments.get("include_forms", True),
            include_landmarks=arguments.get("include_landmarks", True),
            include_headings=arguments.get("include_headings", True),
            max_items_per_kind=arguments.get("max_items_per_kind", 50),
        )
    if name == "frontprompt_get_page_html":
        return GetPageHtmlRequest(
            strip_scripts=arguments.get("strip_scripts", True),
            strip_styles=arguments.get("strip_styles", True),
            strip_comments=arguments.get("strip_comments", True),
            strip_svg=arguments.get("strip_svg", True),
            collapse_whitespace=arguments.get("collapse_whitespace", True),
            max_chars=arguments.get("max_chars", 50000),
        )
    if name == "frontprompt_pick_from_ref":
        return PickFromRefRequest(
            ref_id=arguments["ref_id"],
            snapshot_id=arguments["snapshot_id"],
            comment=arguments["comment"],
        )
    if name == "frontprompt_find_one":
        return FindOneRequest(
            query=arguments["query"],
            comment=arguments["comment"],
            parent_pick_id=arguments.get("parent_pick_id"),
        )
    if name == "frontprompt_find_first":
        return FindFirstRequest(
            query=arguments["query"],
            comment=arguments["comment"],
            parent_pick_id=arguments.get("parent_pick_id"),
        )
    if name == "frontprompt_find_similar":
        return FindSimilarRequest(
            anchor_pick_id=arguments["anchor_pick_id"],
            comment=arguments["comment"],
            threshold=arguments.get("threshold", 0.7),
            max_results=arguments.get("max_results", 50),
        )
    if name == "frontprompt_find_by_regex":
        return FindByRegexRequest(
            pattern=arguments["pattern"],
            comment=arguments["comment"],
            field=arguments.get("field", "text"),
            parent_pick_id=arguments.get("parent_pick_id"),
            limit=arguments.get("limit", 10),
        )
    if name == "frontprompt_get_element_context":
        return GetElementContextRequest(
            pick_id=arguments["pick_id"],
            levels_up=arguments.get("levels_up", 2),
            sibling_radius=arguments.get("sibling_radius", 2),
        )
    if name == "frontprompt_pick_path":
        return PickPathRequest(pick_id=arguments["pick_id"])
    if name == "frontprompt_relocate_picks":
        return RelocatePicksRequest(pick_ids=arguments.get("pick_ids"))
    if name == "frontprompt_inspect_elements":
        return InspectElementsRequest(
            pick_ids=arguments["pick_ids"],
            fields=arguments.get("fields", ["text", "role", "visible", "enabled"]),
        )
    if name == "frontprompt_eval_js":
        return EvalJsRequest(
            expression=arguments["expression"],
            pick_id_arg=arguments.get("pick_id_arg"),
            mutating=arguments.get("mutating", False),
        )
    if name == "frontprompt_dom_patch":
        return DomPatchRequest(
            pick_id=arguments["pick_id"],
            operations=arguments["operations"],
        )
    if name == "frontprompt_pick_by_xpath":
        return PickByXpathRequest(
            xpath=arguments["xpath"],
            comment=arguments["comment"],
            parent_pick_id=arguments.get("parent_pick_id"),
            limit=arguments.get("limit", 10),
        )
    # ── Recording read-side v0.7.0 ──────────────────────────────────────────
    if name == "frontprompt_list_recordings":
        return GetRecordingsRequest()
    if name == "frontprompt_get_recording":
        recording_id = arguments.get("recording_id")
        if not isinstance(recording_id, str) or not recording_id:
            raise ValueError("recording_id is required and must be a non-empty string")
        return GetRecordingRequest(recording_id=recording_id)
    raise ValueError(f"unknown tool: {name!r}")


def _as_text_content(payload: Any) -> list[types.TextContent]:
    text = json.dumps(payload, indent=2, ensure_ascii=False, default=str)
    return [types.TextContent(type="text", text=text)]


# ----------------------------------------------------------------------------
# Server loop
# ----------------------------------------------------------------------------


async def serve_mcp_stdio(
    session_provider: SessionProvider,
    read_stream: MemoryObjectReceiveStream[SessionMessage | Exception] | None = None,
    write_stream: MemoryObjectSendStream[SessionMessage] | None = None,
) -> None:
    """Boot the MCP stdio server, spawning the browser-child lazily.

    ``session_provider`` decides when the browser-session comes into being:

    - :class:`LazyBrowserSessionProvider` (production): spawns on first tool-call.
    - :class:`StaticSessionProvider` (tests): backed by a pre-existing
      :class:`SessionMetadata` so tests don't spawn real subprocesses.

    On server exit (clean stdio EOF or task-cancellation), ``provider.close()`` is
    called so any spawned chromium terminates with the daemon.
    """
    server: Server[object, object] = Server(_SERVER_NAME, version=_SERVER_VERSION)
    tools = _build_tool_list()

    @server.list_tools()  # type: ignore[no-untyped-call]
    async def _list_tools() -> list[types.Tool]:
        return tools

    @server.call_tool()
    async def _call_tool(name: str, arguments: dict[str, Any]) -> list[types.TextContent]:
        # fp_status is a diagnostic tool — does not require a browser session spawn.
        if name == "fp_status":
            return _as_text_content(_DIAGNOSTICS.collect_all())

        try:
            session_info = await session_provider.get()
        except ShowSpawnError as exc:
            _LOG.warning("mcp.tool.spawn_failed", tool=name, error=str(exc))
            # Surface spawn failures as MCP-tool errors so Claude sees the diagnosis.
            raise RuntimeError(f"frontprompt mcp failed to spawn browser session: {exc}") from exc

        if name == "frontprompt_get_session_info":
            return _as_text_content(session_info.model_dump(mode="json"))

        request = _build_ipc_request(name, arguments)
        socket_path = Path(session_info.socket_path)

        # Entry/exit tracing of the daemon→socket round-trip: a hang in the
        # show-child's IPC/page-op leaves ``mcp.tool.ipc.start`` as the last
        # daemon-side line with no matching ``mcp.tool.ipc.done`` — that pins the
        # hang to the show-side, not the daemon dispatch itself.
        _LOG.info("mcp.tool.ipc.start", tool=name, socket=str(socket_path))
        try:
            response = await query(socket_path, request)
        except IpcConnectError as exc:
            _LOG.warning(
                "mcp.tool.browser_session_ended",
                tool=name,
                socket=str(socket_path),
                error=str(exc),
            )
            raise RuntimeError(f"browser session ended: {exc}") from exc
        _LOG.info("mcp.tool.ipc.done", tool=name, ok=response.ok)

        if not response.ok:
            raise RuntimeError(response.error or f"{name} failed")

        return _as_text_content(response.data)

    init_options = InitializationOptions(
        server_name=_SERVER_NAME,
        server_version=_SERVER_VERSION,
        capabilities=server.get_capabilities(
            notification_options=NotificationOptions(),
            experimental_capabilities={},
        ),
    )

    try:
        if read_stream is not None and write_stream is not None:
            _LOG.info("mcp.server.ready", mode="in-process-test")
            await server.run(read_stream, write_stream, init_options)
        else:
            async with stdio_server() as (rs, ws):
                _LOG.info("mcp.server.ready", mode="stdio")
                await server.run(rs, ws, init_options)
    finally:
        await session_provider.close()


__all__ = [
    "DiagnosticsProvider",
    "DiagnosticsRegistry",
    "LazyBrowserSessionProvider",
    "SessionProvider",
    "StaticSessionProvider",
    "serve_mcp_stdio",
]
