# MCP Scout-Tools Design — Phase-1

**Status:** Spec für Implementation
**Date:** 2026-05-24
**Schema-Bump:** IPC 0.2.0 → 0.3.0 (additive)
**Pick-Schema:** unverändert (0.6.0)

## Motivation

Heute hat frontprompt 6 MCP-Tools (`ping`, `get_session_info`, `get_snapshot`, `get_picks`, `get_pick`, `frontprompt_navigate`). Davon sind 4 read-side auf der bestehenden Inspector-State + 1 write-side Browser-Action (navigate). Der MCP-Server kann aktuell weder Daten von Elementen extrahieren noch eigene Picks anlegen — der Agent ist nur passiver Konsument der heutigen User-Inspector-Picks.

Phase-1 Scout führt den Agent in eine **scout-fähige** Rolle: er kann eigene Picks via Selector/Text-Query anlegen, deren DOM-Inhalt strukturiert lesen, Screenshots ziehen, scrollen, und die Page orientieren. Foundation für spätere Phase-2 (Reproducer: `point_at`, `walk_through`) und Phase-3 (Questionnaire: `ask`, `wait_for_user`).

## Design-Direktive (vom User)

1. **pick_id-driven** — jede Element-Operation referenziert ein Pick (kein raw selector in den read-tools). Agent muss explizit picken+commenten bevor er agiert (Audit-Trail-Property).
2. **Semantisch-höherwertig statt 1:1-Playwright-wraps** — frontprompt's Stärke (Inspector + Overlay-Surface) nutzen, kein generischer Playwright-MCP-Klon.
3. **Array-by-design im Reader-Layer** — der Agent kann via Selector mehrere Matches erzeugen, alle Reader nehmen `list[pick_id]` und returnen `list[result]`.
4. **KISS** — Pick-Entity bleibt single-element (Schema 0.6.0). Group-Pick-Vision ist ein separates backlog-item (Schema-Evolution v0.7.0, deferred).

## Architektur

Mit den neuen Tools öffnen sich zwei NEUE Mutation-Targets:

| Target | Aggregat | Wer mutiert |
|--------|----------|-------------|
| Browser-Page (besteht: `navigate`) | Playwright Page | PageController |
| **StateManager.picks** (NEU) | `InspectorState.picks` | `ProgrammaticPickService` (via StateManager.add_pick) |
| (read-only) DOM-Inspection | Live-DOM | PageController, kein State-touch |

Single-Writer-Discipline bleibt gewahrt: picks-creation durchläuft denselben `anyio.Lock` wie der User-Inspector.

### Datei-Struktur (was sich ändert)

```
src/frontprompt/
├── ipc/
│   ├── protocol.py                     # 11 neue Request-Klassen + typed Result-Models
│   ├── page_controller.py              # Protocol wächst um 9 read-methods + 1 action
│   └── playwright_controller/          # NEU: package, concrete Playwright-Impl
│       ├── __init__.py
│       ├── controller.py               # PlaywrightPageController class (orchestrator)
│       ├── element_resolver.py         # pick → ElementHandle (fingerprint-rehydrate, stale-detect)
│       ├── dom_readers.py              # read_text/_html/_outline/_attributes/_state (flat funcs)
│       ├── browser_actions.py          # navigate, scroll_to (flat funcs)
│       ├── screenshots.py              # shoot_element, shoot_page (2MB-cap)
│       └── page_meta.py                # page_info (flat func)
├── state/
│   └── programmatic_picks.py           # NEU: ProgrammaticPickService (StateMgr + PageController orchestrator)
├── mcp_server.py                       # 11 neue tool-handlers
└── cli.py                              # inline _PlaywrightPageController WEG, wird Import
```

Test-Mirror:
```
tests/
├── ipc/
│   ├── fakes.py                                  # NEU: FakePageController (in-memory)
│   ├── test_protocol_v0_3_0.py                   # NEU: Pydantic-validation für 11 neue Requests
│   └── playwright_controller/
│       ├── test_element_resolver.py
│       ├── test_dom_readers.py
│       ├── test_browser_actions.py
│       ├── test_screenshots.py
│       └── test_page_meta.py
├── state/
│   └── test_programmatic_picks.py
├── mcp/
│   └── test_tool_surface_v0_3_0.py               # MCP-handler-tests mit FakePageController
└── browser/
    └── test_mcp_tool_surface.py                  # real-chromium end-to-end, alle 11 tools
```

## Tool-Catalog (11 neue Tools)

### Gruppe A — Pick-Creators (write StateManager, 2 tools)

| Tool | Args | Returns |
|------|------|---------|
| `frontprompt_pick_by_selector` | `selector: str, comment: str, parent_pick_id?: str, limit?: int=10` | `{pick_ids: list[str], total_matches: int, captured: int}` |
| `frontprompt_pick_by_text` | `text: str, role?: str, comment: str, parent_pick_id?: str, limit?: int=10` | `{pick_ids: list[str], total_matches: int, captured: int}` |

- `limit` default 10, hard-max 50 (durch Pydantic-Range geprüft)
- N matches → N separate Picks im StateManager, comment auto-suffixed `"<comment> [match 1/3]"`
- `parent_pick_id` scoped die Query auf den Subtree
- `total_matches > limit` → Agent sieht Diskrepanz, kann refinen

### Gruppe B — Element-Readers (read DOM, 6 tools, array-by-design)

Alle nehmen `pick_ids: list[str]` (min 1, max 50), returnen `list[result]` parallel über Picks.

| Tool | Args | Returns (per pick) |
|------|------|--------------------|
| `frontprompt_get_text` | `pick_ids` | `{text, accessible_name, role, is_visible, is_enabled, is_focused}` |
| `frontprompt_get_html` | `pick_ids, max_chars?=4000` | `{html, truncated: bool}` |
| `frontprompt_get_attributes` | `pick_ids` | `{attributes: dict[str,str]}` |
| `frontprompt_get_state` | `pick_ids` | `{visible, enabled, checked?, focused, in_viewport}` |
| `frontprompt_get_outline` | `pick_ids, max_depth?=3, max_nodes?=100` | nested tree als JSON (rekursiv, capped) |
| `frontprompt_screenshot_element` | `pick_ids, padding?=8` | `{image_base64, format: 'png', width, height}` |

- Single-pick: Agent wraps mit `[id]`
- Stale-pick: result-element wird zu `{error: 'stale_pick', pick_id}` — partial-success möglich
- `get_text` rich, `get_state` atomic — komplementär nicht redundant
- Screenshot-Bild >2MB → `{error: 'screenshot_too_large', pick_id, ...}` in der Liste

### Gruppe C — Page-Level + Scroll (3 tools)

| Tool | Args | Returns | Notes |
|------|------|---------|-------|
| `frontprompt_get_page_info` | (keine) | `{url, title, viewport: {w,h}, scroll: {x,y}, ready_state}` | nach navigate orientieren |
| `frontprompt_screenshot_page` | `full_page?: bool=false` | `{image_base64, format, width, height}` | full vs viewport, 2MB-cap |
| `frontprompt_scroll_to` | `pick_id: str` (single!) | `{is_in_viewport, scroll_position: {x,y}}` | viewport hat nur 1 position; bei list muss Agent wählen |

## IPC-Schema 0.2.0 → 0.3.0 (additive)

11 neue Pydantic-Request-Klassen in `ipc/protocol.py`, discriminated by `kind`. Alle erben `model_config = ConfigDict(extra='forbid')` + `schema_version`-field.

Beispiel:
```python
class PickBySelectorRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")
    kind: Literal["pick_by_selector"] = "pick_by_selector"
    schema_version: str = IPC_SCHEMA_VERSION
    selector: str = Field(min_length=1)
    comment: str = Field(min_length=1)
    parent_pick_id: str | None = None
    limit: int = Field(default=10, ge=1, le=50)
```

`IpcResponse` bleibt generic (`ok`, `data`, `error`). Per-tool data-shapes als separate Pydantic-Models in `protocol.py` definiert (für MCP-server-side typing), wire-format bleibt generic dict.

Schema-Version:
```python
IPC_SCHEMA_VERSION: str = "0.3.0"
# 0.1.0 — read-only
# 0.2.0 — + NavigateRequest (first write-side)
# 0.3.0 — + 11 tools (2 pick-creators, 6 element-readers, 3 page-level)
```

## PageController-Protocol-Erweiterung

`PageController` wächst von 1 method auf 10:

```python
class PageController(Protocol):
    # existing
    async def navigate(self, url: str) -> dict[str, Any]: ...

    # new browser-side reads (nehmen Pick-objekte, nicht pick_id-strings)
    async def get_text(self, picks: list[Pick]) -> list[dict]: ...
    async def get_html(self, picks: list[Pick], max_chars: int) -> list[dict]: ...
    async def get_attributes(self, picks: list[Pick]) -> list[dict]: ...
    async def get_state(self, picks: list[Pick]) -> list[dict]: ...
    async def get_outline(self, picks: list[Pick], max_depth: int, max_nodes: int) -> list[dict]: ...
    async def screenshot_element(self, picks: list[Pick], padding: int) -> list[dict]: ...
    async def screenshot_page(self, full_page: bool) -> dict: ...
    async def get_page_info(self) -> dict: ...

    # new browser-side action
    async def scroll_to(self, pick: Pick) -> dict: ...
```

Pick-Resolution (pick_id-string → Pick from StateMgr) passiert **vor** PageController-call, im mcp_server.py oder ProgrammaticPickService. Saubere Schichtung.

`NullPageController` raises `NotImplementedError` für jede neue method. `FakePageController` (test-only) implementiert sie mit predictable returns.

## ProgrammaticPickService (NEU)

Service in `state/programmatic_picks.py` der **beide** Seiten kennt (StateMgr + PageController):

```python
class ProgrammaticPickService:
    def __init__(self, state_manager: StateManager, page_controller: PageController):
        ...

    async def pick_by_selector(self, selector: str, comment: str,
                                parent_pick_id: str | None, limit: int) -> dict:
        """Erzeugt N single-picks pro selector-match, capped to limit."""
        # 1. parent_pick_id → ElementHandle scope (or document)
        # 2. page.query_selector_all(selector) within scope
        # 3. for handle in elements[:limit]:
        #      pick = build_pick_from_handle(handle, f"{comment} [match {i+1}/{N}]")
        #      await state_manager.add_pick(pick)
        # 4. return {pick_ids, total_matches, captured}

    async def pick_by_text(self, ...): ...   # analog mit Playwright accessibility-locator
```

`add_pick` ist neue Methode auf StateManager — wrappt das bestehende `submit_pick`-event-pattern, aber für non-overlay-Quellen (`source='mcp_agent'` optional als Audit-Flag).

## Failure-Modes

| Szenario | Behavior |
|----------|----------|
| Pick verschwunden aus DOM (fingerprint mismatch nach nav) | Reader returnt `{error: 'stale_pick', pick_id}` an der Stelle in der Liste — partial-success |
| `parent_pick_id` stale beim Pick-Creator | Hard fail mit `{error: 'parent_stale', parent_pick_id}`, keine Picks erzeugt |
| `pick_by_text` mit `role` — text matched, role mismatched | Beide constraints sind AND — gilt als 0 matches |
| Selector matched 0 | `{pick_ids: [], total_matches: 0, captured: 0}` — kein error, Agent sieht's |
| Selector matched > limit | `{captured: limit, total_matches: N}` |
| Screenshot > 2MB | `{error: 'screenshot_too_large', pick_id, ...}` an der Stelle in der Liste |
| `len(pick_ids) > 50` in Reader | hard fail (`{error: 'too_many_picks', max: 50}`) |
| MCP-handler bekommt unbekannten `kind` | bestehende IPC-dispatcher-Fehlerbehandlung; sollte vor schema-bump-roll-out nicht passieren |

## Test-Strategie

| Layer | Test-Type | File |
|-------|-----------|------|
| IPC Pydantic | Unit | `tests/ipc/test_protocol_v0_3_0.py` |
| ElementResolver | Unit + integration | `tests/ipc/playwright_controller/test_element_resolver.py` |
| dom_readers | Unit (mock-handle) + real-chromium | `tests/ipc/playwright_controller/test_dom_readers.py` |
| browser_actions | Real-chromium | `tests/ipc/playwright_controller/test_browser_actions.py` |
| screenshots | Real-chromium | `tests/ipc/playwright_controller/test_screenshots.py` |
| ProgrammaticPickService | Integration (FakePageController + echter StateMgr) | `tests/state/test_programmatic_picks.py` |
| MCP-Server-Handler | Unit (FakePageController) | `tests/mcp/test_tool_surface_v0_3_0.py` |
| End-to-end real-browser | Real-chromium | `tests/browser/test_mcp_tool_surface.py` |

TDD-Reihenfolge bottom-up: 17 Schritte, abwechselnd RED→GREEN von IPC-Requests über ElementResolver → readers → actions → screenshots → controller → service → mcp_server → e2e → cli.py-refactor → drift-gate.

`FakePageController` (`tests/ipc/fakes.py`):
- in-memory pick_id → result-dict map
- konfigurierbare `stale_picks: set[str]` für stale-tests
- predictable returns, kein Playwright-Boot in Unit-Tests

## Migration

Reiner additiver Change:

- ✅ Existing 6 tools bleiben funktional (kein Signatur-change)
- ✅ Schema-bump 0.2.0 → 0.3.0 additive (existing clients ignorieren neue request-kinds)
- ✅ Pick-Entity bleibt unverändert (Schema 0.6.0 bleibt 0.6.0)
- ✅ Frontend touchet keine neuen Types (regen nur)
- ❌ NICHT-additive: `cli.py` Inline-Class wird Import (interner Refactor, kein externe API)

### Post-PR

1. `frontprompt/CLAUDE.md` — Schema-history-row 0.3.0 + MCP-tools-section ersetzt das aktuelle "returns `[]`"
2. `pydantic-zod-codegen` regen → `frontend/src/_generated/` aktualisiert
3. CI drift-gate-job verifiziert codegen-actuality
4. Tier-1 Cleanup audit-items (gestrige session, dead-code `spawn_show_child`) separate run

## Out-of-Scope (explizit, separate Specs)

- **Pick-Schema-Evolution v0.7.0** (group-pick) — backlog [low], deferred. Workaround: N single-picks pro selector-match.
- **Phase-2 Reproducer-Tools** (`point_at`, `walk_through`) — bauen auf Phase-1, eigenes Spec
- **Phase-3 Questionnaire-Tools** (`ask`, `wait_for_user`) — bauen auf Phase-2
- **Persistence-stub → SQLite** — orthogonal, existiert als backlog-item
- **Schema-Evolution-Entscheidung** für eventuelle Schema-Evolution (falls die später kommt)
- **Group-pick UI** (LeftPanel expand/collapse für N-element-pick) — entfällt mit KISS-Pfad

## Cross-Refs

- Ground-truth overlay rendering — Live-DOM-Resolution-Pattern (gleiches Prinzip in `element_resolver.py`); see ARCHITECTURE.md
- Per-MCP-daemon browser isolation — Daemon-Model (Voraussetzung); see ARCHITECTURE.md
- backlog-item: Pick-Schema-Evolution v0.7.0 (parallel deferred)
