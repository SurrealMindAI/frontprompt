# Architecture

frontprompt is a single Python process that drives a headful Chromium browser
via Playwright and injects an in-page Svelte overlay (a shadow-DOM HUD) for
visually annotating any web page. The same process exposes its state and
browser controls to AI agents over an MCP stdio server.

This document is the design reference. For setup and contribution workflow see
[DEVELOPMENT.md](DEVELOPMENT.md) and [CONTRIBUTING.md](CONTRIBUTING.md).

## The headline property: cross-origin survival

Navigating `example.com → google.com` destroys the page's JavaScript context
entirely. Every origin-scoped browser storage mechanism — localStorage,
IndexedDB, cookies, ServiceWorker — is unavailable to the injected overlay
after such a navigation. The only durable place to keep state is the Python
process itself.

Therefore: **every state-item that must survive cross-origin navigation MUST be
authoritative in the Python `StateManager`.** The overlay holds a *read-mirror*
only, hydrated via `window.__fp.getState()` before its first mount (which
eliminates a flash-of-defaults). User actions in the overlay emit `*Requested`
envelopes; the StateManager mutates; a fresh snapshot is broadcast; the mirror
reconciles.

This single decision drives most of the rest of the architecture.

## Two-context model

frontprompt's domain has two conceptually distinct surfaces:

- **Programmatic surface** — the agent-facing MCP tools: navigate, query the
  page, pick elements, screenshot, read state.
- **Interactive surface** — the human-facing annotation UI: pointing,
  picking, drawing regions, typing relations.

Both surfaces mutate the same authoritative state. In the current alpha they
live in one process and share one `StateManager`; the code boundary between
them is not yet hard-separated. What *is* enforced today is **single-writer
discipline**: all state mutation funnels through the `StateManager`, guarded by
an `anyio.Lock`, so the two surfaces can never race each other. A harder
code-level separation is deferred until a second concurrent consumer (e.g.
multi-client coordination) actually exists — see
[Scope](#scope-alpha) below.

## State classification: local vs. backend

A strict boundary governs where each piece of overlay state lives:

| Class | Lives in | Survives cross-origin nav? | Examples |
|---|---|---|---|
| **backendState** | Python `StateManager`, mirrored read-only in the page | yes | picks, regions, relations, panel state |
| **localState** | the page only, dies with it | no | bridge log, drag-in-progress, hover selector, UI prefs |

Anything that a user authored and expects to keep — a pick, a region, a typed
relation — is backend state. Anything ephemeral to the current page render — a
half-finished drag, which tab is open, a transient hover — is local state and
is allowed to die with the page. Hand-writing a piece of would-be-durable state
as local state is the classic regression this boundary prevents.

## ASCII architecture

```
   ┌─────────────────────────────────────────────────────────────────┐
   │  Python CLI Process  (frontprompt show <url>)                   │
   │                                                                 │
   │   BrowserSessionMgr ──► OverlayInjector ──► add_init_script     │
   │   BridgeManager ──► expose_function dispatch (in/out)           │
   │                                                                 │
   │   StateManager (anyio.Lock single-writer)                       │
   │     ├─ PanelStateView                                           │
   │     ├─ InspectorState                                           │
   │     │    ├─ picks: list[Pick]            (color_index, fp, rect)│
   │     │    ├─ regions: list[Region]        (page-abs rect, members│
   │     │    │                                viewport_snapshot,    │
   │     │    │                                color_index)          │
   │     │    ├─ relations: list[Relation]    (hetero: pick|region)  │
   │     │    ├─ active_pick_id / active_region_id (mutually excl.)  │
   │     │    └─ active flag (inspector mode)                        │
   │     └─ SQLite persistence (WAL + JSON-blob)                     │
   └──────────────────────────┬──────────────────────────────────────┘
                              │  expose_function (Playwright)
                              ▼
   ┌─────────────────────────────────────────────────────────────────┐
   │  Page (any origin) — <fp-overlay> Svelte customElement          │
   │                                                                 │
   │   window.__fp (single namespace, callable + dispatch + version) │
   │                                                                 │
   │   ╭─ backendState (mirror, $state-based) ───────────────────╮   │
   │   │  panel + inspector (hydrated on OverlayReady)           │   │
   │   ╰─────────────────────────────────────────────────────────╯   │
   │                                                                 │
   │   ╭─ localState (dies-with-page) ──────────────────────────╮    │
   │   │  bridgeLog · uiPrefs (tab+visibilities+hover)          │    │
   │   │  pageTool (inspector OR region-draft active?)          │    │
   │   │  pickClaim (single-claim-at-a-time coordinator)        │    │
   │   ╰────────────────────────────────────────────────────────╯    │
   │                                                                 │
   │   ╭─ Inspector-Layers ─────────────────────────────────────╮    │
   │   │  InspectorLayer    — click-pick (one element)          │    │
   │   │  DrawRegionLayer   — drag-rect (region+auto-picks)     │    │
   │   │  RelationsLayer    — SVG overlay (picks, regions, edges│    │
   │   │                       — ground-truth live-DOM render)  │    │
   │   ╰────────────────────────────────────────────────────────╯    │
   │                                                                 │
   │   ╭─ HUD (4 panels: top/bottom/left/right) ────────────────╮    │
   │   │  Toolbar (4 stat-pills: events/picks/regions/relations)│    │
   │   │  LeftPanel: Picks · Regions · Relations · Events tabs  │    │
   │   │  RightPanel: PickDetails | RegionDetails (mutex)       │    │
   │   ╰────────────────────────────────────────────────────────╯    │
   └─────────────────────────────────────────────────────────────────┘
```

## The bridge: `expose_function`, no HTTP

The Python process and the in-page overlay communicate exclusively through
Playwright's `expose_function` API. There is no HTTP server and no WebSocket.
This keeps the alpha to one process and one transport with zero network
surface: the bridge function is installed into the page, the overlay calls it
to read state and emit intents, and the Python side dispatches typed Pydantic
message-models in response.

A single page-global namespace, `window.__fp`, carries everything: the callable
bridge, the dispatch surface, and a version marker. The overlay's TypeScript
`Bridge` class is the only thing that touches it. Namespace pollution
(`window.__fp_anything`) is **structurally forbidden** and enforced by two
architecture tests, one on the TypeScript side and one on the Python side.

## Single-writer state

`StateManager` is the sole writer of authoritative state, serialized through an
`anyio.Lock`. Concurrency is anyio-based throughout (not asyncio-locked), so the
same code runs unmodified under either backend. State is persisted to a
SQLite database (WAL mode, JSON-blob schema, with an `origin_session` provenance
column) so annotations outlive the process. The Pydantic types — `Pick`,
`Region`, `Relation`, `Viewport`, `InspectorState`, `StateSnapshot` — are the
single source of truth; the overlay's TypeScript types are generated from them.

## Ground-truth overlay rendering

The overlay never renders a pick/region/relation from a stored snapshot rect.
It always re-derives the geometry from the *live DOM* at render time. If an
element no longer exists on the current page — for instance after a cross-origin
navigation — the live lookup returns null and the renderer simply skips it.
There is no snapshot fallback, so there are no "ghost boxes" floating where an
element used to be. Live DOM is the only source of geometric truth.

## Shadow-DOM isolation

The overlay is a Svelte component compiled in customElement mode and mounted in
a shadow root. This isolates it from the host page's CSS: page rules such as
`example.com div { opacity: 0.8 }` cannot bleed into the HUD, and the HUD's
styles cannot leak out into the page. This was an empirical regression that the
shadow boundary resolves cleanly.

## Layer boundaries

### Python (`src/frontprompt/`)

- `browser/` — Playwright session lifecycle.
- `overlay/` — `page.add_init_script` injection plus a `verify_mounted` poll.
  The loader resolves the bundle from the **embedded package data first**
  (`frontprompt/_overlay/`, what ships in the wheel), then falls back to
  `frontend/dist/` for development.
- `_overlay/` — gitignored, build-time-embedded overlay bundle and manifest.
  This is what makes the wheel self-contained.
- `bridge/` — `BridgeManager` (the `expose_function` lifecycle and dispatch),
  the Pydantic message-models, and the codegen wrapper.
- `state/` — `StateManager` (single-writer, `anyio.Lock`) and the Pydantic
  domain types. SQLite persistence lives under `state/persistence/`.
- `build/` — the canonical build entry point (`python -m frontprompt.build`):
  codegen → vite → embed into `_overlay/`; `--wheel` then packages a
  self-contained wheel.
- `cli.py` — entry-point wiring for the `frontprompt` command.

### Frontend (`frontend/src/`)

- `bridge/` — the TypeScript `Bridge` class and interceptor pattern (single
  `window.__fp`).
- `backend-state/` — the `backendState` umbrella: `PanelState` and
  `InspectorState` mirrors, hydration/sync, and intent emission.
- `local-state/` — the `localState` umbrella: `BridgeLog`, `uiPrefs` (tab
  state, overlay visibilities, hover), `pageTool` (derived: inspector OR
  region-draft active), `pickClaim` (single-claim coordinator).
- `components/` — Panel, PanelTab, PanelResizer, Toolbar, LeftPanel (4 tabs),
  RightPanel (Pick | Region details), InspectorLayer (click-pick),
  DrawRegionLayer (drag-rect), RelationsLayer (SVG overlay), DebugPanel, and
  primitives.
- `managers/` — `ResizeManager` (pointer-event drag).
- `services/relations/` — position-service (live-DOM ground truth),
  position-tracker (resize/scroll tick), path-planner (heterogeneous endpoints,
  bezier + sag), lookup-service, relation-draft (creation state machine),
  animation-tokens, svg-renderer.
- `services/regions/` — region-scanner (containment + deepest + min-area),
  region-draft (drag state machine), and a `buildPickFromElement` shared with
  InspectorLayer.
- `services/relations-analyzer/` — DOM post-processing after a region scan
  (lowest-common-ancestor + tree-distance threshold → derived relations).
- `services/color-palette/` — a 32-color rainbow palette (bit-reversed hue +
  4 lightness groups).
- `services/element-locator/` — `buildFingerprint`, `generateCssSelector`,
  `fingerprintHash`.
- `services/scroll-router/` — wheel-event forwarding to the scrollable ancestor
  under the cursor.
- `services/event-interceptor/` — page-event capture for the Events tab.
- `services/keyboard/` — global keyboard-shortcut coordinator.
- `_generated/` — schema-driven TypeScript types generated from the Pydantic
  source of truth (gitignored).

## Inspector flows

| Flow | Components | Resulting state |
|---|---|---|
| **Click-pick** | "pick" tool → InspectorLayer → click element → `submitPick` | a `Pick` with fingerprint-dedup, color index, comment field |
| **Region-draw** | "region" tool → DrawRegionLayer → drag rect → region-scanner picks ≥80%-contained members → `submitPick` per member → `submitRegion` → analyze DOM relations → `submitRelation` per derived edge | a `Region` (page-absolute rect, viewport snapshot, members) + auto-picks + auto-relations |
| **Relation-create** | Relations tab "+ create" → pick × 2 → kind + note → `submitRelation` | a `Relation` (pick↔pick, manual) |
| **Selection** | click pick/region in LeftPanel → `selectPick` / `selectRegion` (mutex) → RightPanel opens details | `active_pick_id` ⊕ `active_region_id` |
| **Visibility** | toolbar pills toggle picks/regions/relations | `uiPrefs.{picks,regions,relations}Visible` |

Relations are heterogeneous: an edge may connect any pair of pick or region
endpoints, with a typed kind (`relates_to` / `triggers` / `part_of`). Edges can
be drawn manually or derived automatically after a region scan via
lowest-common-ancestor plus a tree-distance threshold.

## MCP server

`frontprompt mcp` is the MCP stdio server entry point. Each invocation spawns an
independent, ephemeral server process that owns exactly one private browser
session. There is no singleton and no lockfile — multiple client sessions each
get their own process and their own Chromium, and the process dies on stdio-EOF
(client disconnect). A crashed browser session therefore cannot corrupt another
agent's pick state.

**Lazy browser spawn.** A lazy session provider defers the `frontprompt show`
child-spawn until the first actual tool call. Daemon startup is instant; the
Chromium window appears only when a tool needs it. Teardown happens on
SIGINT/SIGTERM: the daemon terminates the child's process group
(`os.killpg(SIGTERM)`), cascading to Chromium and its children without leaving
zombies (the child is spawned with `start_new_session=True`).

**`fp_status` diagnostic tool.** This is the health-check entry point. It
returns `schema_version`, `phase`, `capabilities_available`, and
`capabilities_deferred` *without* requiring a browser session, and is the
extension point for additional diagnostics providers.

**`get_state_summary` — overview first.** A full `get_snapshot` is a firehose
for an AI agent (hundreds of thousands of characters at a few hundred picks).
`get_state_summary` is the small, navigable counterpart: a typed `StateSummary`
(read-only, lock-consistent) with `counts`, a per-origin-session breakdown, a
per-hostname breakdown (host derived per pick URL; `data:` URLs collapse to
`"data:"`, never the blob), and an owned-vs-foreign split. Agents start here,
then drill down via `get_snapshot` / `get_picks` / `get_pick`.

## State schema history

| Version | Date | Change |
|---|---|---|
| 0.1.0 | 2026-05-18 | initial — `panel_state` only |
| 0.2.0 | 2026-05-19 | + `inspector_state` (picks flow) |
| 0.3.0 | 2026-05-20 | + `inspector_state.relations` (pick↔pick edges, typed kinds) |
| 0.4.0 | 2026-05-20 | heterogeneous relations (`source_id`+`source_kind`+`target_id`+`target_kind`). + `inspector_state.regions` + `active_region_id`. **Breaking** relation shape. |
| 0.5.0 | 2026-05-20 | + `Pick.color_index` + `Region.color_index` (additive — 32-color palette identity) |
| 0.6.0 | 2026-05-20 | `Region.rect` migrated to page-absolute (was viewport-relative). + `Region.viewport_snapshot`. Screenshot-extraction-ready. |
| 0.7.0 | 2026-05-31 | + `origin_session` on Pick/Region/Relation (additive — persistence provenance) |
| 0.8.0 | 2026-06-26 | + `recordings_state: RecordingsState` on StateSnapshot (additive). Introduces Recording aggregate with TimelineEntry union (PageEventEntry/PickRefEntry/RegionRefEntry/RelationRefEntry/NavigationEntry), RecordingMeta (lightweight list), RecordingsState (active_recording_id + detail selection). SQLite tables: `recordings` + `timeline_entries` (WAL, UNIQUE(recording_id, seq)). Python-owned monotonic seq counter. Non-broadcasting `append_timeline_entry` path (COL-5). Auto-link on pick/region/relation add (COL-6). |

## IPC (tool) schema history

| Version | Date | Change |
|---|---|---|
| 0.1.0 | 2026-05-18 | initial read-only — ping, get_snapshot, get_picks, get_pick |
| 0.2.0 | 2026-05-20 | + navigate (first write-side, browser action) |
| 0.3.0 | 2026-05-24 | + 11 tools: pick_by_selector, pick_by_text (pick-creators) + 6 element-readers + get_page_info, screenshot_page, scroll_to (page-level) |
| 0.4.0 | 2026-05-26 | + PageAnalyzer service layer: get_page_outline, get_page_html, pick_from_ref, find_one, find_first, find_similar, find_by_regex, get_element_context, pick_path, relocate_picks, inspect_elements, eval_js, dom_patch, pick_by_xpath. screenshot return modes "path"\|"inline". |
| 0.5.0 | 2026-06-02 | + get_state_summary — small navigable overview; mitigates the get_snapshot firehose for AI agents |

## Anti-patterns, structurally prevented

| Anti-pattern | How it is prevented |
|---|---|
| Cross-origin state loss | Python is authoritative; the overlay pre-mount-hydrates a read-mirror |
| Multi-writer state races | `anyio.Lock` single-writer in `StateManager` |
| Page CSS bleeding into the overlay | Shadow DOM via Svelte customElement mode |
| `window.__fp_*` namespace pollution | Two architecture tests (TypeScript + Python) fail the build |
| Ghost boxes after cross-origin nav | Live DOM is ground truth; a null live-rect lookup skips the render — no snapshot fallback |

## Scope (alpha)

Phase 1 (current) is intentionally minimal: one process, one in-page overlay,
`expose_function` only. The following are explicitly deferred to Phase 2 with
clear re-trigger criteria, rather than built speculatively:

- **Daemon singleton / multi-instance coordination** — reactivate only on a
  documented multi-client need. Today each daemon owns its own session.
- **HTTP / WebSocket transport** — the bridge is `expose_function`-only.
- **Hard two-context code separation** — single-writer discipline is enforced
  now; the code boundary hardens when a second concurrent consumer lands.

In scope from Phase 1, without re-opening the design: diagnostic/health-check
MCP tools (`fp_status` and future diagnostics providers reporting state-manager
health, bridge state, browser-session health, queue depths). Navigation,
screenshots, and the element-reader/PageAnalyzer tools are already live.
