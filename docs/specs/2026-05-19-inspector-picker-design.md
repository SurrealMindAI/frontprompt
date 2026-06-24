# 2026-05-19 — Inspector / Element-Picker Design

> Status: draft, awaiting implementation
> Domain language anchor: the PointingSession / Pick / Annotation aggregate (see ARCHITECTURE.md).

## Context

Phase-1 Durchstich (panel-state mirror, expose_function bridge, customElement HUD) is live since 2026-05-19 03:17. Next priority is the **first real Pick-Flow**: connect a UI-driven action that mutates backend-state and survives a snapshot broadcast round-trip. This spec covers the design of that flow.

The user has long-running need for an in-page element inspector — a toggle that lets a human point at any DOM element in the open page, label it with a comment, and have the resulting Pick survive in a session-scoped list. This is the canonical Interactive-Surface use case.

## Goal

Build the **Inspector** feature: a toggle in the left panel that enters a pick-mode where the user can target any element in the page-content area, capturing its identity (selector + structural fingerprint) and an optional comment. Picks live in a list in the left panel; the selected pick's details + comment editor live in the right panel.

## Naming

- **Inspector** — feature name. The mode. The user-visible verb is "inspect".
- **`inspectorActive: bool`** — the toggle state in `backendState.inspector`.
- **`<InspectorLayer />`** — the transient capture surface mounted only while active.
- **`<HighlightBorder />`** — the animated rect that tracks the hovered element.
- **Pick** — the entity persisted on click (matches the domain vocabulary).
- **Element-Locator service** — the standalone TS service that produces selector + fingerprint at pick-time.

`Overlay` remains reserved for the customElement HUD itself. Inspector is a feature *inside* the overlay.

## Scope

### Phase 1 (this spec)

- Toolbar-style button in a new left-panel-tools strip toggles inspector.
- All panels retract to tabs while inspector active (derived, no snapshot/restore).
- `InspectorLayer` captures pointer, draws animated border, captures click → Pick.
- Picks land in `backendState.inspector.picks` (in-memory in Python's StateManager).
- Left panel bottom area is a tabbed container with one tab: "Picks" (list).
- Right panel shows the active pick: details + comment editor with explicit Save + dirty-state.
- ESC cancels active inspector mode.
- Cross-origin navigation is non-destructive — Python keeps the pick-list authoritative.

### Phase 2 (deferred — out of scope)

- Adaptive re-location: Python uses Scrapling's `.relocate(fingerprint, percentage)` against the current `page.content()` to re-locate picks after DOM drift or cross-origin nav and back.
- Visual marker overlay for re-located picks ("you were here").
- Disk persistence (SQLite under `~/.local/state/frontprompt/`).
- Mode selector (text-range pick, css-selector-only pick, screenshot pick, …).
- Multi-tab Inspector panel (history, search, filter).

The data model captured in Phase 1 is **forward-compatible** with all Phase-2 use cases: no refactor needed, only additions.

## Architecture

```text
┌─────────────────────────────────────────────────────────────────────┐
│  Python CLI Process                                                 │
│                                                                     │
│   StateManager (single-writer, anyio.Lock)                          │
│     ├─ PanelStateView                       (existing)              │
│     └─ InspectorState                       (NEW)                   │
│          ├─ active: bool                                            │
│          ├─ picks: list[Pick]                                       │
│          └─ active_pick_id: str | None                              │
│                                                                     │
│   BridgeManager  (handles new *Requested intents — see § Wire)      │
└──────────────────────────┬──────────────────────────────────────────┘
                           │ expose_function (Playwright)
                           ▼
┌─────────────────────────────────────────────────────────────────────┐
│  Page — <fp-overlay> Svelte customElement (shadow DOM)              │
│                                                                     │
│   App.svelte grid:                                                  │
│     top    — Toolbar (unchanged)                                    │
│     left   — <LeftPanel>                                            │
│                ├─ <LeftPanelTools>  (Inspector toggle)              │
│                └─ <TabbedPanel> → "Picks" → <PicksTab>              │
│     right  — <RightPanel>                                           │
│                └─ <PickDetails> + <CommentEditor>                   │
│     bottom — DebugPanel (unchanged)                                 │
│     center — pointer-events: none  (page click-through)             │
│                                                                     │
│   When inspectorActive:                                             │
│     <InspectorLayer />          (position:fixed; inset:0)           │
│       captures pointermove + click on page elements                 │
│       elementsFromPoint filter: skip closest('fp-overlay')          │
│       <HighlightBorder />        (rAF + scroll-listener tracking)   │
└─────────────────────────────────────────────────────────────────────┘
```

### Lifecycle

```text
1. User clicks Inspector toggle in LeftPanelTools
     ├─ optimistic UI: backendState.inspector.active = true (panels retract via derived)
     ├─ wire OUT: inspector_activate_requested
     └─ python: StateManager.set_inspector_active(True) → snapshot broadcast

2. InspectorLayer mounts (its existence is reactive to inspector.active)
     ├─ listens window pointermove + click + scroll
     ├─ subscribes to global keyboard service for ESC
     └─ rAF loop tracks hovered element's getBoundingClientRect → HighlightBorder

3a. User clicks an element →
     ├─ build fingerprint + selector via element-locator service
     ├─ generate uuid4 pick_id (client-side)
     ├─ optimistic UI: append pick to picks list, set activePickId, inspector.active = false
     ├─ wire OUT: inspector_pick_made_requested { pick_id, element, url, timestamp_ms }
     └─ python: StateManager.add_pick(...) → snapshot broadcast

3b. User presses ESC →
     ├─ optimistic UI: inspector.active = false (no pick)
     ├─ wire OUT: inspector_canceled_requested
     └─ python: StateManager.set_inspector_active(False) → snapshot broadcast

4. Right panel rendert <PickDetails> + <CommentEditor> für activePickId
   User editiert Kommentar, click Save:
     ├─ optimistic UI: pick.comment ← editor value, dirty = false
     ├─ wire OUT: pick_comment_updated_requested { pick_id, comment }
     └─ python: StateManager.update_pick_comment(...) → snapshot broadcast

5. User clickt anderen Pick in der Liste:
     ├─ optimistic UI: activePickId ← clicked.pick_id
     ├─ wire OUT: pick_selected_requested { pick_id }
     └─ python: StateManager.select_pick(...) → snapshot broadcast
```

### Panel-retract via derived (no snapshot/restore)

The user's intent (which panels they want open) lives untouched in `panelState.panels[id].open`. The **displayed** state derives Inspector-awareness:

```ts
// in panel-state.svelte.ts
private inspectorActive = $derived(backendState.inspector.active);

effectiveOpenFor(id: PanelId): boolean {
  return this.inspectorActive ? false : this.panels[id].open;
}

effectiveSize(id: PanelId): number {
  return this.effectiveOpenFor(id) ? this.panels[id].size : PANEL_CONFIGS[id].tabThickness;
}
```

When `inspector.active` flips false, derived returns to original panel-state. No state copy, no restore logic, no Python-side tracking of "previous panel state". Existing grid-template-transition (220ms cubic-bezier) animates retract + restore for free.

## State Shape

### Pydantic (Python SSoT — `frontprompt.state.state`)

```python
class ElementRect(BaseModel):
    x: float; y: float; width: float; height: float

class ElementFingerprint(BaseModel):
    """Scrapling-equivalent multi-factor element identity.

    Captured client-side at pick-time. Used Phase-1 for storage only.
    Phase-2: passed to Scrapling's Selector.relocate() against page.content()
    for adaptive re-location after DOM drift / cross-origin nav.
    """
    tag: str                              # "DIV"
    attributes: dict[str, str]            # all attribs (id, class, data-*, aria-*, role, ...)
    text: str                             # textContent, truncated 500 chars
    path: list[str]                       # tag-sequence root→element (e.g. ["html","body","main","div"])
    parent_tag: str | None
    parent_attributes: dict[str, str]
    parent_text: str                      # truncated 500 chars
    siblings: list[str]                   # tag-sequence of direct siblings (in order)
    children: list[str]                   # tag-sequence of direct children (in order)

class PickElement(BaseModel):
    selector: str                         # human-readable CSS selector (id-first → :nth-of-type chain)
    fingerprint: ElementFingerprint
    text_snippet: str                     # truncated 120-char preview for list display
    rect: ElementRect                     # boundingClientRect at pick-time

class Pick(BaseModel):
    pick_id: str                          # uuid4, client-generated
    url: str                              # window.location.href at pick-time
    timestamp_ms: int                     # epoch ms (client-generated)
    element: PickElement
    comment: str = ""

class InspectorState(BaseModel):
    active: bool = False
    picks: list[Pick] = []
    active_pick_id: str | None = None

class StateSnapshot(BaseModel):
    schema_version: str = "0.2.0"         # bumped from 0.1.0
    panel_state: PanelStateView
    inspector_state: InspectorState
```

`__codegen_roots__` extends:
```python
__codegen_roots__ = [
    "PanelView", "PanelStateView",
    "ElementRect", "ElementFingerprint", "PickElement", "Pick",
    "InspectorState", "StateSnapshot",
]
```

### StateManager methods (async, lock-guarded)

```python
async def set_inspector_active(self, active: bool) -> StateSnapshot: ...
async def add_pick(self, pick: Pick) -> StateSnapshot: ...        # appends, sets active_pick_id, sets inspector.active=False
async def select_pick(self, pick_id: str) -> StateSnapshot: ...   # sets active_pick_id; no-op if pick_id unknown
async def update_pick_comment(self, pick_id: str, comment: str) -> StateSnapshot: ...
async def delete_pick(self, pick_id: str) -> StateSnapshot: ...   # convenience, may be used by UI delete-button
```

`add_pick` is **atomic**: append + activePickId + inspector.active=False mutate inside a single `anyio.Lock` block. One snapshot broadcast lands the combined state on the overlay side.

### TS-side (`frontend/src/backend-state/inspector-state.svelte.ts`)

```ts
import { bridge } from '../bridge/bridge.svelte';
import type { Pick, InspectorState as InspectorView } from '../_generated/state';

const SCHEMA_VERSION = '0.2.0';

export class InspectorState {
  active = $state(false);
  picks = $state<Pick[]>([]);
  activePickId = $state<string | null>(null);

  activePick = $derived(
    this.picks.find(p => p.pick_id === this.activePickId) ?? null
  );

  hydrate(view: InspectorView): void {
    this.active = view.active ?? this.active;
    this.picks = view.picks ?? this.picks;
    this.activePickId = view.active_pick_id ?? this.activePickId;
  }

  // Intents (optimistic UI + wire-send)
  activate(): void {
    this.active = true;
    void bridge.send({ kind: 'inspector_activate_requested', schema_version: SCHEMA_VERSION });
  }
  cancel(): void {
    this.active = false;
    void bridge.send({ kind: 'inspector_canceled_requested', schema_version: SCHEMA_VERSION });
  }
  submitPick(pick: Pick): void {
    this.picks = [...this.picks, pick];
    this.activePickId = pick.pick_id;
    this.active = false;
    void bridge.send({
      kind: 'inspector_pick_made_requested',
      schema_version: SCHEMA_VERSION,
      pick_id: pick.pick_id,
      element: pick.element,
      url: pick.url,
      timestamp_ms: pick.timestamp_ms,
    });
  }
  selectPick(pickId: string): void {
    this.activePickId = pickId;
    void bridge.send({ kind: 'pick_selected_requested', schema_version: SCHEMA_VERSION, pick_id: pickId });
  }
  updateComment(pickId: string, comment: string): void {
    const i = this.picks.findIndex(p => p.pick_id === pickId);
    if (i >= 0) this.picks[i] = { ...this.picks[i], comment };
    void bridge.send({ kind: 'pick_comment_updated_requested', schema_version: SCHEMA_VERSION, pick_id: pickId, comment });
  }
  deletePick(pickId: string): void {
    this.picks = this.picks.filter(p => p.pick_id !== pickId);
    if (this.activePickId === pickId) this.activePickId = null;
    void bridge.send({ kind: 'pick_deleted_requested', schema_version: SCHEMA_VERSION, pick_id: pickId });
  }
}
```

`backendState` umbrella adds:
```ts
class BackendState {
  panel = new PanelState();
  inspector = new InspectorState();
  hydrate(snap: StateSnapshot): void {
    if (snap.panel_state) this.panel.hydrate(snap.panel_state);
    if (snap.inspector_state) this.inspector.hydrate(snap.inspector_state);
  }
}
```

## Wire Messages

New outbound (TS → Python) in `frontprompt.bridge.messages`:

| Message | Payload |
|---------|---------|
| `InspectorActivateRequested` | — |
| `InspectorCanceledRequested` | — |
| `InspectorPickMadeRequested` | `pick_id`, `element: PickElement`, `url`, `timestamp_ms` |
| `PickSelectedRequested` | `pick_id` |
| `PickCommentUpdatedRequested` | `pick_id`, `comment` |
| `PickDeletedRequested` | `pick_id` |

All carry `schema_version` field per existing convention. All extend the `OutboundMessage` discriminated union by `kind` literal.

No new inbound messages — Python signals state changes via the existing `StateSnapshotMessage` broadcast.

## Component Decomposition

```text
frontend/src/
├── App.svelte                          [UPDATE: <LeftPanel /> + <RightPanel /> + conditional <InspectorLayer />]
├── components/
│   ├── Panel.svelte                    (unchanged)
│   ├── PanelTab.svelte                 (unchanged)
│   ├── PanelResizer.svelte             (unchanged)
│   ├── Toolbar.svelte                  (unchanged)
│   ├── DebugPanel.svelte               (unchanged)
│   ├── left-panel/
│   │   ├── LeftPanel.svelte            [NEW: 2-row internal grid — Tools + TabbedPanel]
│   │   ├── LeftPanelTools.svelte       [NEW: Inspector-toggle button, ~40px row]
│   │   └── tabs/
│   │       ├── PicksTab.svelte         [NEW: scroll-y list of picks]
│   │       └── PickItem.svelte         [NEW: tag + selector + comment preview, click → selectPick]
│   ├── right-panel/
│   │   ├── RightPanel.svelte           [NEW: empty-state vs activePick render]
│   │   ├── PickDetails.svelte          [NEW: tag, classes, id, selector, url, timestamp, text-snippet]
│   │   └── CommentEditor.svelte        [NEW: textarea + Save + dirty-state + Discard]
│   ├── inspector/
│   │   ├── InspectorLayer.svelte       [NEW: position:fixed capture surface]
│   │   └── HighlightBorder.svelte      [NEW: animated rect tracking hovered element]
│   └── primitives/
│       └── TabbedPanel.svelte          [NEW: reusable snippet-based tab container]
├── services/
│   ├── element-locator/
│   │   ├── index.ts
│   │   ├── selector-path.ts            [NEW: Firefox-style CSS-selector generator]
│   │   ├── element-fingerprint.ts      [NEW: Scrapling-equivalent fingerprint builder]
│   │   ├── stable-id.ts                [NEW: isStableId predicate]
│   │   ├── types.ts                    [NEW: re-exports of generated types]
│   │   └── element-locator.test.ts     [NEW: unit tests against DOM snippets]
│   └── keyboard/
│       ├── keyboard.svelte.ts          [NEW: global subscribable keyboard service]
│       └── keyboard.test.ts            [NEW: unit tests]
├── backend-state/
│   ├── backend-state.svelte.ts         [UPDATE: + inspector]
│   ├── panel-state.svelte.ts           [UPDATE: cross-derive on inspector.active]
│   └── inspector-state.svelte.ts       [NEW]
└── _generated/
    ├── state.ts                        [REGEN]
    └── schemas.ts                      [REGEN]
```

## Element-Locator Service

Standalone TS module under `frontend/src/services/element-locator/`. Pure functions, no Svelte runes, no state — easy to unit-test. Produces `(selector: string, fingerprint: ElementFingerprint)` from a DOM Element.

### `selector-path.ts` — `generateCssSelector(el): string`

Firefox-DevTools-style algorithm, modeled on Scrapling's `SelectorsGeneration._general_selection` (see `/scrapling/core/mixins.py`):

```ts
function generateCssSelector(el: Element, opts: { fullPath?: boolean } = {}): string {
  if (el.id && isStableId(el.id)) return `#${CSS.escape(el.id)}`;

  const parts: string[] = [];
  let node: Element | null = el;
  while (node && node !== document.documentElement) {
    const tag = node.tagName.toLowerCase();
    const idx = nthOfType(node);    // 1-based among same-tag siblings under same parent
    parts.unshift(`${tag}:nth-of-type(${idx})`);
    if (!opts.fullPath && parts.length >= 4) break;
    node = node.parentElement;
  }
  return parts.join(' > ');
}

function nthOfType(el: Element): number {
  if (!el.parentElement) return 1;
  let n = 0;
  for (const child of el.parentElement.children) {
    if (child.tagName === el.tagName) {
      n++;
      if (child === el) return n;
    }
  }
  return 1;
}
```

### `stable-id.ts` — `isStableId(id): boolean`

Filter out framework-generated volatile IDs that would make selectors brittle:

```ts
export function isStableId(id: string): boolean {
  if (!id || id.length > 40) return false;
  return !/^(react-|v-|__|svelte-|ember\d+|aria-|tippy-|popper-|\d+$)/.test(id);
}
```

This is the only departure from Scrapling's default — page-author IDs win, framework-generated IDs lose. Adjust pattern set in unit tests as we encounter new frameworks.

### `element-fingerprint.ts` — `buildFingerprint(el): ElementFingerprint`

Mirrors Scrapling's `_StorageTools.element_to_dict` output (see `/scrapling/core/utils/_utils.py`):

```ts
export function buildFingerprint(el: Element): ElementFingerprint {
  return {
    tag: el.tagName.toLowerCase(),
    attributes: getAttributes(el),
    text: truncate(el.textContent ?? '', 500),
    path: getPath(el),                                       // ["html","body","main","div"]
    parent_tag: el.parentElement?.tagName.toLowerCase() ?? null,
    parent_attributes: el.parentElement ? getAttributes(el.parentElement) : {},
    parent_text: truncate(el.parentElement?.textContent ?? '', 500),
    siblings: [...(el.parentElement?.children ?? [])].map(c => c.tagName.toLowerCase()),
    children: [...el.children].map(c => c.tagName.toLowerCase()),
  };
}
```

Helpers (`getAttributes`, `getPath`, `truncate`) are simple, unit-tested.

### Unit-test coverage

- selector for element with stable id → returns `#id`
- selector for element with framework id (`react-XXX`, etc.) → ignores id, falls through to nth-of-type chain
- selector for deeply nested element → caps at 4 levels by default
- fingerprint round-trips via JSON.stringify/parse (no Pydantic ConfigDict surprises)
- fingerprint for orphan element (no parent) → parent_tag is null, parent_attributes is {}
- fingerprint text truncation at 500 chars

## InspectorLayer Details

```svelte
<!-- InspectorLayer.svelte -->
<script lang="ts">
  import { backendState } from '../../backend-state/backend-state.svelte';
  import { keyboard } from '../../services/keyboard/keyboard.svelte';
  import { buildFingerprint, generateCssSelector } from '../../services/element-locator';
  import HighlightBorder from './HighlightBorder.svelte';

  let hoveredEl = $state<Element | null>(null);
  let rect = $state<DOMRect | null>(null);

  // rAF loop while hovered — keeps border synced with scroll, animation, layout drift
  let rafHandle: number | null = null;
  function startTracking() {
    function loop() {
      if (hoveredEl) rect = hoveredEl.getBoundingClientRect();
      rafHandle = requestAnimationFrame(loop);
    }
    rafHandle = requestAnimationFrame(loop);
  }
  function stopTracking() {
    if (rafHandle !== null) cancelAnimationFrame(rafHandle);
    rafHandle = null;
  }

  function onPointerMove(e: PointerEvent) {
    const els = document.elementsFromPoint(e.clientX, e.clientY);
    const target = els.find(el => !el.closest('fp-overlay')) ?? null;
    if (target !== hoveredEl) {
      hoveredEl = target;
      if (target) startTracking(); else stopTracking();
    }
  }

  function onClick(e: PointerEvent) {
    if (!hoveredEl) return;
    e.preventDefault();
    e.stopPropagation();
    const fingerprint = buildFingerprint(hoveredEl);
    const selector = generateCssSelector(hoveredEl);
    const rect = hoveredEl.getBoundingClientRect();
    backendState.inspector.submitPick({
      pick_id: crypto.randomUUID(),
      url: window.location.href,
      timestamp_ms: Date.now(),
      element: {
        selector,
        fingerprint,
        text_snippet: (hoveredEl.textContent ?? '').slice(0, 120),
        rect: { x: rect.x, y: rect.y, width: rect.width, height: rect.height },
      },
      comment: '',
    });
  }

  $effect(() => {
    const unsubEsc = keyboard.subscribe('Escape', () => backendState.inspector.cancel());
    return () => { stopTracking(); unsubEsc(); };
  });
</script>

<div
  class="inspector-layer"
  onpointermove={onPointerMove}
  onclick={onClick}
>
  {#if rect}
    <HighlightBorder {rect} />
  {/if}
</div>

<style>
  .inspector-layer {
    position: fixed;
    inset: 0;
    z-index: 99999;
    pointer-events: auto;
    cursor: crosshair;
    /* No background — must not visually obscure the page */
  }
</style>
```

### `<HighlightBorder />`

```svelte
<script lang="ts">
  let { rect }: { rect: DOMRect } = $props();
</script>

<div
  class="highlight-border"
  style:left="{rect.x}px"
  style:top="{rect.y}px"
  style:width="{rect.width}px"
  style:height="{rect.height}px"
></div>

<style>
  .highlight-border {
    position: fixed;
    pointer-events: none;
    outline: 2px solid rgba(120, 220, 255, 0.95);
    outline-offset: -1px;
    box-shadow: 0 0 0 4px rgba(120, 220, 255, 0.18), 0 0 16px rgba(120, 220, 255, 0.4);
    border-radius: 2px;
    transition: left 100ms cubic-bezier(0.2, 0.8, 0.2, 1),
                top  100ms cubic-bezier(0.2, 0.8, 0.2, 1),
                width  100ms cubic-bezier(0.2, 0.8, 0.2, 1),
                height 100ms cubic-bezier(0.2, 0.8, 0.2, 1);
  }
</style>
```

Scroll handling falls out of the rAF loop — every frame recomputes `getBoundingClientRect()` which reflects current scroll position. No explicit scroll listener needed when rAF is running. If the user scrolls without moving the pointer, the rAF loop is already running because `hoveredEl` is set; the border tracks the element through scroll naturally.

## Comment Editor — Save + Dirty-State

`<CommentEditor />` accepts the activePick's `pick_id` + current `comment`. Holds a local editor-value, tracks dirty-state, exposes Save + Discard buttons.

```svelte
<script lang="ts">
  import { backendState } from '../../backend-state/backend-state.svelte';

  let { pickId, initialComment }: { pickId: string; initialComment: string } = $props();
  let editorValue = $state(initialComment);
  const dirty = $derived(editorValue !== initialComment);

  // If activePickId changes (user clicks different pick), refresh editor
  $effect(() => { editorValue = initialComment; });

  function save() {
    if (!dirty) return;
    backendState.inspector.updateComment(pickId, editorValue);
  }
  function discard() {
    editorValue = initialComment;
  }
</script>

<div class="comment-editor">
  <textarea
    bind:value={editorValue}
    placeholder="Notiz zu diesem Pick..."
    rows="6"
  ></textarea>
  <div class="actions">
    <button onclick={save} disabled={!dirty} class:dirty>
      {dirty ? 'Speichern *' : 'Gespeichert'}
    </button>
    <button onclick={discard} disabled={!dirty} class="ghost">Verwerfen</button>
  </div>
</div>
```

The dirty-marker `*` in the button label is the visible signal. The button is disabled when not dirty.

## Global Keyboard Service

`services/keyboard/keyboard.svelte.ts` — small subscribable global keyboard event service. Decouples ESC handling from any single component, lets the InspectorLayer (and any future feature) subscribe declaratively.

```ts
type Handler = (e: KeyboardEvent) => void;

class KeyboardService {
  private handlers = new Map<string, Set<Handler>>();
  private installed = false;

  private install(): void {
    if (this.installed) return;
    window.addEventListener('keydown', this.onKeydown, { capture: true });
    this.installed = true;
  }

  private onKeydown = (e: KeyboardEvent): void => {
    const set = this.handlers.get(e.key);
    if (!set) return;
    for (const h of set) h(e);
  };

  subscribe(key: string, handler: Handler): () => void {
    this.install();
    if (!this.handlers.has(key)) this.handlers.set(key, new Set());
    this.handlers.get(key)!.add(handler);
    return () => this.handlers.get(key)?.delete(handler);
  }
}

export const keyboard = new KeyboardService();
```

Capture-phase listener fires before page elements can swallow the key. ESC is the only key bound in Phase 1, but the design supports any number of handlers per key.

## Schema Migration

`schema_version` bumps from `0.1.0` to `0.2.0`.

- Frontend `hydrate` paths are field-tolerant (`if (snap.X)`) per existing convention — overlay receiving an old `0.1.0` snapshot would simply not hydrate `inspector_state` (defaults preserved). Old overlay receiving new `0.2.0` snapshot would ignore the unknown field.
- pydantic-zod-codegen drift gate runs on `python -m frontprompt.build` and CI — failing the build if `_generated/` is stale.
- No persisted state to migrate (Phase 1 is in-memory only). Phase 2 SQLite will land its own migration story.

## Testing Strategy

| Layer | Tests |
|-------|-------|
| `services/element-locator/` | unit (vitest + happy-dom): stable-id, nth-of-type chain, depth cap, fingerprint shape, text truncation, orphan elements |
| `services/keyboard/` | unit (vitest): subscribe/unsubscribe, key dispatch, multiple handlers |
| `backend-state/inspector-state.svelte.ts` | unit (vitest): hydrate, optimistic mutations, derived `activePick`, intent → bridge.send calls (bridge mocked) |
| `state.py` Pydantic | unit (pytest): roundtrip, schema-version, codegen-roots-coverage |
| `state/manager.py` | unit (pytest): each mutation method, listener-broadcast, atomicity of `add_pick` |
| `bridge/messages.py` | unit (pytest): each new envelope shape, discriminated-union routing |
| End-to-end | Playwright real-chromium integration (`tests/browser/`): activate → click element → assert snapshot broadcast contains the new pick |

The end-to-end test is the canonical Durchstich-test: spawn `frontprompt show <fixture-page>`, programmatically click the inspector toggle, click a known fixture element, assert Python state contains the pick with correct selector + fingerprint. Reuses the existing real-chromium-integration test harness.

## Risks

1. **`document.elementsFromPoint` cross-shadow-DOM behavior.** In Chromium with `mode: 'open'` shadow DOMs, `elementsFromPoint` returns elements only from the topmost open shadow tree at each point. We filter for `!el.closest('fp-overlay')` which works because `fp-overlay` is itself a custom element on the host document. Risk: if a page has its own nested custom elements with closed shadow DOMs, we may pick the host element rather than the intended inner element. Mitigation: document the limitation, accept Phase-1.

2. **Performance with rAF loop.** Each frame computes `getBoundingClientRect()` (cheap, ~µs) and updates `style:`. On a 120Hz display this is ~8ms budget — well within range. If we observe jank, batch into a single `style.cssText` write.

3. **iframes.** Cross-origin iframes are inaccessible (same-origin policy). Same-origin iframes report their internal element via `elementsFromPoint`. Phase 1 picks the iframe-host element only (we don't recurse into iframes). Phase 2 may add iframe-recursion.

4. **DOM mutation during inspector active.** SPA mutations (React/Svelte re-renders) may replace the `hoveredEl` reference with a stale node. The rAF loop reads from the cached reference, not a live query — if the node is detached, `getBoundingClientRect()` returns all zeros. Acceptable for Phase 1 (user moves cursor → new element → recovers). Phase 2 can add MutationObserver to re-evaluate the hovered element if the cached reference detaches.

5. **Scout-mode followups.** During implementation, the canonical build (`python -m frontprompt.build`) may surface drift in `_generated/`. Land the regenerated files in the same commit as the Pydantic edits.

## References

- Pick/Annotation aggregate and the localState-vs-backendState classification — see ARCHITECTURE.md.
- Scrapling element-fingerprint implementation: `scrapling/core/mixins.py`, `scrapling/core/utils/_utils.py`, `scrapling/parser.py` (`Selector.relocate`)
