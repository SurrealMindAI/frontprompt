# MCP Scout-Refinement v0.4.0 — PageAnalyzer + Token-Optimized Tools

**Status:** Spec für Implementation
**Date:** 2026-05-26
**IPC Schema-Bump:** 0.3.0 → 0.4.0 (additive)
**Pick-Schema:** unverändert (0.6.0)
**Predecessor:** [2026-05-24-mcp-scout-tools-design.md](2026-05-24-mcp-scout-tools-design.md) (Phase 1)

## Motivation

Phase-1 Scout (v0.3.0) lieferte 11 neue MCP-Tools, alle pick-driven, alle live-DOM-basiert. Live-Smoke-Test 2026-05-26 enthüllte vier strukturelle Schwächen:

1. **`screenshot_*` 2MB-cap zu generös** — Claude-response-token-limit liegt bei ~50KB; ein 1200×1279 viewport-PNG (150KB base64) sprengt Claude's response-budget komplett.
2. **`pick_by_text("More information")` → 0 matches** auf example.com obwohl der Link existiert. Pseudo-selector-routing in der eigenen impl matched zu strikt.
3. **`pick_by_text` produziert manchmal sofort stale picks** — DOM-Elemente ohne stabile re-resolution (z.B. text-node-parent ohne id/class) werden gepickt, gehen direkt stale beim ersten read.
4. **Token-Economy unzureichend** — outline-Erkundung erfordert N pick_by_selector-roundtrips. inspect_elements verteilt auf 3 separate Tools (get_text + get_attributes + get_state) statt 1 unified call. get_html returnt raw HTML mit scripts/styles ohne stripping.

Phase 1.5 adressiert diese vier Findings UND legt die Foundation für Phase-2 (Reproducer) + Phase-3 (Questionnaire) durch eine neue Service-Layer **`PageAnalyzer`** — sie nutzt Scrapling als implementation-detail, exponiert aber pick-domain-API.

## Design-Direktive (user-approved 2026-05-26)

1. **Pick-driven default** — Agent denkt in Picks, nicht Selektoren. Tool-Responses sind picks oder opaque refs.
2. **Low-level escape-hatch erlaubt im Ausnahmezustand** — `eval_js`, `dom_patch`, `pick_by_xpath` als 3 explizite Tools mit selbsterklärenden Namen. Naming signalisiert Gefahr ohne `unsafe_`-prefix.
3. **Scrapling als implementation-detail** — der Service heißt `PageAnalyzer` (intent-revealing), Scrapling wird hinter `analysis/_impl/scrapling_bridge.py` versteckt. Eine Datei, leicht austauschbar wenn Scrapling stirbt (bus-factor=1).
4. **Outline returnt opaque refs, NICHT auto-picks** — `pick_from_ref(ref, comment)` materialisiert on-demand. StateManager bleibt clean.
5. **Default inspect-fields** `[text, role, visible, enabled]` — der häufigste case ist abgedeckt; mehr fields auf Anfrage.

## Architektur

Zwei-Tier-Modell (NEW):

```
┌──────────────────────────────────────────────────────────────┐
│ TIER 1 — Live Browser (Playwright Page)                      │
│   • click, type, scroll_to, screenshot, navigate (Phase-1)   │
│   • dynamic state: is_visible/_enabled/_focused/_checked     │
│   • DOM-mutation: eval_js, dom_patch (low-level, NEW)        │
│   • Pure live-DOM access                                     │
└──────────────────────────────────────────────────────────────┘
                          │
                          │ page.content() snapshot
                          ▼
┌──────────────────────────────────────────────────────────────┐
│ TIER 2 — Parsed Page Snapshot (PageAnalyzer)                 │
│   • outline, condensed_html, context, path                   │
│   • find_one/_first/_similar, find_by_text/_regex            │
│   • adaptive relocation                                      │
│   • Pure-Python lxml queries — NO JS-eval round-trips        │
│   • Implementation: Scrapling (invisible behind bridge)      │
└──────────────────────────────────────────────────────────────┘
                          │
                          │ resolve via fingerprint → live ElementHandle
                          ▼
                  ┌──────────────────┐
                  │  Pick (persisted │
                  │  in StateManager)│
                  └──────────────────┘
```

**Lifecycle:** `PageAnalyzer` cached den parsed snapshot bis er invalidiert wird:
- automatisch bei `navigate()` (kompletter DOM-replace)
- automatisch bei `eval_js(mutating=True)` oder `dom_patch(...)`
- TTL-default 30s (gegen stale snapshots bei async-loading)
- manuell via `analyzer.invalidate_snapshot()`

20 Outline-queries auf gleichem snapshot kosten effektiv 1 IPC-call (1× snapshot, 20× lxml-queries).

### Datei-Struktur (was sich ändert)

```
src/frontprompt/
├── analysis/                                    NEW package
│   ├── __init__.py                              exports PageAnalyzer + result types
│   ├── analyzer.py                              PageAnalyzer class (the service)
│   ├── snapshot.py                              PageSnapshot (parsed handle, TTL, invalidation)
│   ├── outline.py                               OutlineBuilder + OutlineRef + PageOutline types
│   ├── finders.py                               find_one/_first/_similar/_by_text/_by_regex
│   ├── context.py                               element-context (parent/siblings/path)
│   ├── relocator.py                             adaptive pick-relocation
│   ├── types.py                                 FindQuery, InspectField, OutlineOptions, etc.
│   └── _impl/
│       ├── __init__.py
│       └── scrapling_bridge.py                  ONLY file that imports scrapling
│
├── ipc/
│   ├── page_controller.py                       Protocol +3 low-level methods
│   ├── playwright_controller/
│   │   ├── controller.py                        orchestrator gains eval_js + dom_patch + xpath
│   │   ├── element_resolver.py                  delegates hard cases to analyzer.relocator
│   │   ├── browser_actions.py                   + eval_js, + dom_patch
│   │   ├── screenshots.py                       + return_mode="path"|"inline"
│   │   ├── (dom_readers + page_meta unchanged)
│   │   └── xpath_query.py                       NEW: pick_by_xpath low-level helper
│   └── protocol.py                              +14 new request classes, schema 0.4.0
│
├── state/
│   └── programmatic_picks.py                    delegate pick_by_text to PageAnalyzer
│
└── mcp_server.py                                +14 tool defs, deprecation-warnings on 5 existing
```

Test-Mirror:
```
tests/
├── analysis/
│   ├── test_analyzer.py                         high-level integration
│   ├── test_snapshot.py                         lifecycle + TTL
│   ├── test_outline.py                          outline + ref materialization
│   ├── test_finders.py                          find_one/_first/_similar/_by_text/_by_regex
│   ├── test_context.py                          parent/siblings/path
│   ├── test_relocator.py                        adaptive relocation
│   └── _impl/test_scrapling_bridge.py           bridge unit tests
├── ipc/playwright_controller/
│   ├── test_xpath_query.py                      NEW
│   ├── test_browser_actions.py                  + eval_js + dom_patch tests
│   └── test_screenshots.py                      + return_mode test
└── browser/test_mcp_scout_refinement.py         e2e real-chromium für alle 14 neuen tools
```

### PageAnalyzer Interface

```python
class PageAnalyzer:
    """High-level page-analysis service.

    Snapshots the live DOM, runs rich queries, returns Picks.
    Underlying technology (Scrapling/lxml) is implementation-detail.
    """

    def __init__(
        self,
        page: Page,
        resolver: ElementResolver,
        state_manager: StateManager,
        snapshot_ttl_seconds: float = 30.0,
    ) -> None: ...

    # ── Snapshot lifecycle ──
    async def snapshot(self, fresh: bool = False) -> PageSnapshot: ...
    def invalidate_snapshot(self) -> None: ...

    # ── Outline + condensed read ──
    async def outline(self, options: OutlineOptions = ...) -> PageOutline: ...
    async def condensed_html(self, options: CondensedHtmlOptions = ...) -> CondensedHtml: ...

    # ── Finders (return Picks or refs, no raw selectors leaked) ──
    async def find_one(self, query: FindQuery, comment: str) -> Pick | None: ...
    async def find_first(self, query: FindQuery, comment: str) -> tuple[Pick, int] | None: ...
    async def find_by_text(self, text: str, role: str | None, parent_pick: Pick | None,
                            comment: str, limit: int) -> FindResult: ...
    async def find_by_regex(self, pattern: str, field: Literal["text", "attribute", "any"],
                             parent_pick: Pick | None, comment: str, limit: int) -> FindResult: ...
    async def find_similar(self, anchor_pick: Pick, threshold: float, max_results: int,
                            comment: str) -> FindResult: ...

    # ── Context + path ──
    async def context(self, pick: Pick, levels_up: int, sibling_radius: int) -> ElementContext: ...
    async def path(self, pick: Pick) -> list[PathSegment]: ...

    # ── Ref materialization ──
    async def pick_from_ref(self, ref: OutlineRef, comment: str) -> Pick | None: ...

    # ── Adaptive relocation ──
    async def relocate(self, picks: list[Pick]) -> list[RelocationResult]: ...

    # ── Inspect (hybrid: static via snapshot + dynamic via live page) ──
    async def inspect(self, picks: list[Pick], fields: list[InspectField]) -> list[InspectResult]: ...
```

### FindQuery (Pydantic discriminated union)

```python
class FindByText(BaseModel):
    kind: Literal["text"] = "text"
    text: str
    role: str | None = None
    exact: bool = False  # default: substring case-insensitive

class FindByRegex(BaseModel):
    kind: Literal["regex"] = "regex"
    pattern: str
    field: Literal["text", "attribute", "any"] = "text"

class FindByLabel(BaseModel):
    kind: Literal["label"] = "label"
    label_text: str  # accessible-name-based finder

class FindByRole(BaseModel):
    kind: Literal["role"] = "role"
    role: str
    name: str | None = None

class FindByCss(BaseModel):
    """Low-level — prefer FindByText/Role/Label when possible."""
    kind: Literal["css"] = "css"
    selector: str

FindQuery = Annotated[
    FindByText | FindByRegex | FindByLabel | FindByRole | FindByCss,
    Field(discriminator="kind"),
]
```

### OutlineRef contract

```python
class OutlineRef(BaseModel):
    """Opaque reference to an outline-entry. Short-lived (per snapshot)."""
    ref_id: str  # "out:link:3" or similar — internal mapping to selector + fingerprint
    snapshot_id: str  # the snapshot that produced this ref
    expires_at_ms: int  # client may check before pick_from_ref

class PageOutline(BaseModel):
    snapshot_id: str
    title: str
    url: str
    headings: list[OutlineHeading]
    links: list[OutlineLink]
    buttons: list[OutlineButton]
    inputs: list[OutlineInput]
    forms: list[OutlineForm]
    landmarks: list[OutlineLandmark]

class OutlineLink(BaseModel):
    ref: OutlineRef
    text: str
    href: str | None
    in_viewport: bool  # computed via live page state, not parser

# ... analog für headings/buttons/inputs/forms/landmarks
```

Refs sind invalidated wenn der zugehörige snapshot invalidated wird. `pick_from_ref` returnt `None` wenn ref expired.

## Tool-Catalog

### Pick-driven default (high-level, 11 NEW + 1 modified)

| Tool | Args | Returns |
|------|------|---------|
| `frontprompt_get_page_outline` | `options?` (include_text/links/buttons/inputs/forms/landmarks/headings, max_items_per_kind) | PageOutline |
| `frontprompt_get_page_html` | `strip_scripts?=true, strip_styles?=true, strip_comments?=true, strip_svg?=true, collapse_whitespace?=true, max_chars?=50000` | `{html, truncated, original_chars, stripped_chars}` |
| `frontprompt_pick_from_ref` | `ref_id: str, snapshot_id: str, comment: str` | `{pick_id} \| {error: "ref_expired" \| "ref_not_found"}` |
| `frontprompt_find_one` | `query: FindQuery, comment: str, parent_pick_id?: str` | `{pick_id} \| {error: "not_found" \| "ambiguous", total_matches}` |
| `frontprompt_find_first` | `query: FindQuery, comment: str, parent_pick_id?: str` | `{pick_id, total_matches} \| {error: "not_found"}` |
| `frontprompt_find_similar` | `anchor_pick_id: str, threshold?=0.7, max_results?=50, comment: str` | `{pick_ids: list[str], scores: list[float]}` |
| `frontprompt_find_by_regex` | `pattern: str, field?="text", parent_pick_id?: str, comment: str, limit?=10` | `{pick_ids, total_matches, captured}` |
| `frontprompt_get_element_context` | `pick_id: str, levels_up?=2, sibling_radius?=2` | `{ancestors, prev_sibling, next_sibling, in_form, in_table, semantic_landmark}` |
| `frontprompt_pick_path` | `pick_id: str` | `{path: [{tag, role, text_excerpt, semantic_landmark}, ...]}` |
| `frontprompt_relocate_picks` | `pick_ids?: list[str]` (default = all) | `[{pick_id, status: "alive" \| "recovered" \| "stale", new_selector?, similarity?}]` |
| `frontprompt_inspect_elements` | `pick_ids: list[str], fields?=["text","role","visible","enabled"]` | `[{pick_id, ...requested_fields}]` |

### Modified existing tools (3)

| Tool | Change |
|------|--------|
| `frontprompt_screenshot_element` | + `return_mode: "path" \| "inline" = "path"`. Path-mode writes to `/tmp/frontprompt/<session>/<ts>-elem-<pid8>.png`, returns `{path, width, height, bytes, directive: "Read this PNG via the Read tool for pixel content."}` |
| `frontprompt_screenshot_page` | analog `return_mode` parameter |
| `frontprompt_pick_by_text` | intern delegiert zu `PageAnalyzer.find_by_text(...)` — **fixes smoke-test bug**: bessere substring-matching + stable-pick-post-condition |

### Low-level escape-hatch (3 NEW)

| Tool | Args | Returns |
|------|------|---------|
| `frontprompt_pick_by_xpath` | `xpath: str, comment: str, parent_pick_id?: str, limit?=10` | `{pick_ids, total_matches, captured}` |
| `frontprompt_eval_js` | `expression: str, pick_id_arg?: str, mutating?=false` | `{result: Any, ok: bool, error?: str}`. If `pick_id_arg` given, the live ElementHandle is bound to `el` in JS context. `mutating=true` invalidates snapshot. |
| `frontprompt_dom_patch` | `pick_id: str, operations: list[DomPatchOp]` | `{ok, results: list[{op, ok, error?}]}`. Operations: `set_attribute`, `remove_attribute`, `set_text`, `add_class`, `remove_class`, `remove_element`. Always invalidates snapshot. |

`DomPatchOp` ist Pydantic discriminated union per `op`-discriminator.

### Deprecated (still wired, removed in v0.5.0)

| Tool | Replacement | Deprecation-message in tool description |
|------|------------|------------------------------------------|
| `frontprompt_get_text` | `inspect_elements(pick_ids, fields=["text","role","visible","enabled","focused","accessible_name"])` | "Deprecated: use inspect_elements with fields parameter" |
| `frontprompt_get_attributes` | `inspect_elements(pick_ids, fields=["attributes"])` | analog |
| `frontprompt_get_state` | `inspect_elements(pick_ids, fields=["visible","enabled","checked","focused","in_viewport"])` | analog |
| `frontprompt_get_html` | `inspect_elements(pick_ids, fields=["html"], max_chars=...)` for per-pick, oder `get_page_html` für gesamte page | analog |
| `frontprompt_get_outline` | `inspect_elements(pick_ids, fields=["outline"], max_depth=..., max_nodes=...)` | analog |

Deprecated tools bleiben funktional, geben nur deprecation-warning in description-text.

## IPC Schema 0.3.0 → 0.4.0 (additive)

14 neue Pydantic Request-Klassen + ~10 Result-Models in `protocol.py`. Bestehende 0.3.0-Requests bleiben unverändert. IpcRequest-union erweitert.

Beispiel:
```python
class FindOneRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")
    kind: Literal["find_one"] = "find_one"
    schema_version: str = IPC_SCHEMA_VERSION
    query: FindQuery
    comment: str = Field(min_length=1)
    parent_pick_id: str | None = None

class GetPageOutlineRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")
    kind: Literal["get_page_outline"] = "get_page_outline"
    schema_version: str = IPC_SCHEMA_VERSION
    include_text: bool = True
    include_links: bool = True
    include_buttons: bool = True
    include_inputs: bool = True
    include_forms: bool = True
    include_landmarks: bool = True
    include_headings: bool = True
    max_items_per_kind: int = Field(default=50, ge=1, le=200)
```

Schema-Version:
```python
IPC_SCHEMA_VERSION: str = "0.4.0"
# 0.1.0 — read-only
# 0.2.0 — + NavigateRequest (write-side)
# 0.3.0 — + 11 scout tools v0.3.0
# 0.4.0 — + PageAnalyzer (11 high-level + 3 low-level) + screenshot return_mode + pick_by_text rewire
```

## PageController-Protocol-Erweiterung

Protocol wächst um 3 Methoden für low-level escape:

```python
class PageController(Protocol):
    # ... existing 10 from v0.3.0 ...

    async def eval_js(self, expression: str, pick_id_arg: Pick | None,
                       mutating: bool) -> dict[str, Any]: ...
    async def dom_patch(self, pick: Pick, operations: list[dict]) -> dict[str, Any]: ...
    async def pick_by_xpath_raw(self, xpath: str, parent_pick: Pick | None,
                                  limit: int) -> dict[str, Any]: ...  # returns element-data
                                                                       # (analog query_selector_all)
```

`NullPageController` raises NotImplementedError für alle drei. `FakePageController` (tests) gibt deterministic returns.

## Scrapling-Bridge Isolation

**Vertrag:** Nur `src/frontprompt/analysis/_impl/scrapling_bridge.py` darf `import scrapling.*`. Architecture-Test enforced:

```python
# tests/arch/test_scrapling_isolation.py
def test_only_bridge_imports_scrapling():
    """Scrapling must remain swappable. Only the bridge file is allowed to import it."""
    import ast
    for py_file in glob.glob("src/frontprompt/**/*.py", recursive=True):
        if py_file.endswith("_impl/scrapling_bridge.py"):
            continue
        tree = ast.parse(open(py_file).read())
        for node in ast.walk(tree):
            if isinstance(node, ast.ImportFrom) and node.module:
                assert not node.module.startswith("scrapling"), \
                    f"{py_file}: only scrapling_bridge.py may import scrapling.*"
            if isinstance(node, ast.Import):
                for alias in node.names:
                    assert not alias.name.startswith("scrapling"), \
                        f"{py_file}: only scrapling_bridge.py may import scrapling.*"
```

Bridge-API ist tech-agnostisch:
```python
# scrapling_bridge.py exposes ONLY domain-typed helpers, NEVER scrapling-types
def parse_html(html: str) -> ParsedDocument: ...
def find_elements(doc: ParsedDocument, query: dict) -> list[ElementMatch]: ...
def find_similar_elements(doc: ParsedDocument, anchor_fingerprint: dict,
                          threshold: float, max_results: int) -> list[ElementMatch]: ...
def find_by_text(doc: ParsedDocument, text: str, role: str | None,
                  exact: bool, scope: ElementMatch | None) -> list[ElementMatch]: ...
def find_by_regex(doc: ParsedDocument, pattern: str, field: str,
                   scope: ElementMatch | None) -> list[ElementMatch]: ...
def relocate_element(doc: ParsedDocument, fingerprint: dict) -> ElementMatch | None: ...
def condensed_html(doc: ParsedDocument, options: dict) -> str: ...
# ... etc
```

`ParsedDocument` und `ElementMatch` sind unsere eigenen Pydantic types, NICHT Scrapling-types. Bridge konvertiert intern.

## Failure Modes

| Szenario | Behavior |
|----------|----------|
| `find_one` mit > 1 match | `{error: "ambiguous", total_matches: N}` — Agent muss query refinen |
| `find_one` mit 0 matches | `{error: "not_found"}` |
| `pick_from_ref` mit expired ref | `{error: "ref_expired"}` — Agent muss outline neu callen |
| `pick_from_ref` mit unknown ref_id | `{error: "ref_not_found"}` |
| `relocate_picks` für unrecoverable picks | per-pick `{status: "stale", ...}` |
| `relocate_picks` für recovered picks | per-pick `{status: "recovered", new_selector: ..., similarity: 0.85}` |
| `eval_js` mit JS-exception | `{ok: false, error: "JavaScript error: ..."}` |
| `eval_js` mit `mutating=true` aber kein DOM-change | invalidates snapshot trotzdem (sicher) |
| `dom_patch` mit invalid op | `{ok: false, results: [{op: ..., ok: false, error: "unknown operation kind"}]}` |
| `dom_patch` stale pick | hard fail `{ok: false, error: "stale_pick"}` |
| `pick_by_xpath` invalid XPath | Pydantic-validation-error vor IPC-call |
| `find_similar` mit anchor_pick stale | hard fail `{error: "stale_pick"}` |
| `get_page_outline` snapshot age > TTL | auto-refresh snapshot |
| `inspect_elements(fields=["html","outline"])` for >50 picks | hard fail per existing cap |

## Test Strategy

| Layer | Test type | File |
|-------|-----------|------|
| Scrapling-bridge | Unit (parsed lxml fixtures) | `tests/analysis/_impl/test_scrapling_bridge.py` |
| PageSnapshot | Unit + TTL/invalidation | `tests/analysis/test_snapshot.py` |
| PageAnalyzer | Integration (real Chromium + FakeStateManager) | `tests/analysis/test_analyzer.py` |
| Outline + refs | Integration | `tests/analysis/test_outline.py` |
| Finders | Integration | `tests/analysis/test_finders.py` |
| Context + path | Integration | `tests/analysis/test_context.py` |
| Relocator | Integration (DOM-mutation szenarios) | `tests/analysis/test_relocator.py` |
| xpath_query | Real-chromium | `tests/ipc/playwright_controller/test_xpath_query.py` |
| eval_js + dom_patch | Real-chromium | extends `test_browser_actions.py` |
| screenshot return_mode | Real-chromium | extends `test_screenshots.py` |
| Scrapling isolation arch-test | Static AST | `tests/arch/test_scrapling_isolation.py` |
| IPC Pydantic 0.4.0 | Unit | `tests/ipc/test_protocol_v0_4_0.py` |
| socket-server +14 dispatch | Integration | `tests/ipc/test_socket_server_v0_4_0.py` |
| mcp_server tool-surface | Unit | `tests/mcp/test_tool_surface_v0_4_0.py` |
| End-to-end real-chromium | Real-chromium | `tests/browser/test_mcp_scout_refinement.py` |

## Migration

Reiner additiver Change:

- ✅ Existing 17 tools bleiben funktional (5 davon deprecated mit warning, nicht broken)
- ✅ Schema-bump 0.3.0 → 0.4.0 additive
- ✅ Pick-Entity bleibt Schema 0.6.0
- ✅ Frontend ungeschnitten (kein _generated/ codegen-bump erforderlich da neue IPC-types nicht im wire-codegen-root sind, analog v0.3.0)
- ❌ NICHT-additive: pick_by_text impl wird umgestellt (intern), aber API-contract bleibt

### Post-PR

1. IPC schema-history row 0.4.0
2. Foundation libs row: scrapling Phase-1.5 status active (war pre-staged)
3. New architecture decision: "PageAnalyzer service layer + Scrapling isolation"
4. Drift-gate verify (kein codegen-change erwartet)

## Out-of-Scope (separate tracks)

- **Pick-Schema-Evolution v0.7.0** — group-pick deferred bleibt
- **Phase-2 Reproducer-Tools** (`point_at`, `walk_through`)
- **Phase-3 Questionnaire-Tools** (`ask`, `wait_for_user`)
- **Phase-2 Act-Side** (`click`, `type`, `select`, `wait_for`) — needs a dedicated architecture decision
- **SQLite persistence migration**
- **PageAnalyzer multi-snapshot caching** (e.g. parallel-tab support) — Phase 2

## Cross-Refs

- [Phase-1 spec — 2026-05-24-mcp-scout-tools-design.md](2026-05-24-mcp-scout-tools-design.md)
- [Phase-1 collision-analysis](../plans/mcp-scout-tools-v0-3-0/collision-analysis.md)
- Ground-truth overlay rendering and per-MCP-daemon browser isolation — see ARCHITECTURE.md
- backlog-entry: MCP-Tool-Erweiterung Phase-1.5 v0.4.0
