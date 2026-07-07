# InteractionMachine refactor — overlay mode-state consolidation

**Status:** STEP 0–2 landed (bug fix); STEP 3–7 planned.
**Origin:** state-machine analysis of the scattered overlay interaction/mode state,
triggered by the "pick/region dead during recording" bug.

## Verdict

There is **no single interaction-mode authority**. "What the user is doing" is
spread across **6 flags in 5 files**, and mutual exclusion between modes is
*emergent* (UI button-disable + hand-rolled cross-cancels), never an invariant:

- `inspector.active` (`backend-state/inspector-state.svelte.ts`) — backend mirror
  *and* shadow of `pickClaim.current`
- `pickClaim.current` (`local-state/pick-claim.svelte.ts`) — presence duplicates
  `inspector.active`; only the `{id,onPick,onCancel}` payload is non-derivable
- `regionDraft.drafting` (`services/regions/region-draft.svelte.ts`)
- `quickCommentMode.active` (`local-state/quick-comment-mode.svelte.ts`) — parallel
  `.grid--quick` CSS path, in no mutex
- `recordings.activeRecordingId` (`backend-state/recording-state.svelte.ts`) —
  re-derived 4× (`recorder.isActive`, `LeftPanelTools:37`, `interceptor:292`)
- `panelCollapse.active` (`local-state/panel-collapse.svelte.ts`) — aggregate

### The deepest stench (root cause of the reported bug)

`panelCollapse.active = pageTool.active || recorder.isActive` fused three
category-distinct concerns into one boolean:

- **capture** (recording in progress)
- **viewport** (a full-viewport tool owns the screen)
- gating an **affordance** (are the tool buttons clickable) via
  `Panel.svelte .content--collapsed { pointer-events: none }`

So enabling recording collapsed the LEFT panel that hosts the pick/region tools →
`togglePick`/`toggleRegion` never fired. Second desync: `InspectorLayer`'s Escape
called `backendState.inspector.cancel()` directly, bypassing `pickClaim`, leaving
`pickClaim.current` set with no picker mounted ("tool stays on, click does nothing").

## Target machine (derived-first)

One `InteractionMachine` singleton owning the **minimal real inputs**:

- `mode: 'idle' | 'inspecting' | 'drawingRegion' | 'quickComment'` — one enum,
  replaces `inspector.active`, `pickClaim.current` presence, `regionDraft.drafting`,
  `quickCommentMode.active`
- `activeClaim: { id, onPick, onCancel } | null` — the only non-derivable part of pickClaim
- `selectedTarget: { kind: 'pick' | 'region', id } | null` — replaces the
  hand-maintained `(activePickId, activeRegionId)` mutex with one discriminated union
- `regionGeometry: { origin, current } | null` — genuine pointer input (rect stays derived)
- `quickPending: pickId | null` — which pick the quick-comment box edits
- `recording: { id, voiceOver } | null` — **orthogonal axis**, authoritative from the
  Python snapshot; composes with any `mode` as a legal product state
- `floatingToolbarPosition` / `activeDragHandle` — genuine UI drag inputs
- domain collections (`picks`/`regions`/`relations`/`recordings`) — backend-owned data

Everything else becomes `$derived`:

| Current flag | Becomes |
|---|---|
| `inspector.active` | `mode === 'inspecting'` |
| `pickClaim.current` presence | `mode ∈ {inspecting, quickComment}` (keep payload only) |
| `regionDraft.drafting` | `mode === 'drawingRegion'` |
| `quickCommentMode.active` | `mode === 'quickComment'` |
| `pageTool.active` | `mode ∈ {inspecting, drawingRegion}` |
| `panelCollapse.active` | `pageTool.active` (mode-only — **never** recording) |
| `recorder.isActive` | `recording !== null` (canonical `recordings.isRecording`, not a 4th re-derivation) |

`submit`/`cancel` are single **atomic** transitions that clear `mode` + `activeClaim`
together → the Escape desync becomes unrepresentable. `enterPick`/`enterRegion` are
dispatched identically by `LeftPanelTools` and any floating affordance → the two
claim ids (`pick:global` vs `pick:recorder-toolbar`) collapse into one.

## Migration steps

- **STEP 0 — DONE** — failing tests pinning the bug (`panel-collapse.svelte.test.ts`
  recording-does-not-collapse; `InspectorLayer.test.ts` Escape-routing).
- **STEP 1 — DONE** — `panel-collapse.svelte.ts`: dropped the `recorder.isActive`
  OR-term → `active = pageTool.active`. Recording is orthogonal; the tool strip stays
  reachable during recording.
- **STEP 2 — DONE** — `InspectorLayer.svelte`: Escape routes through `handleCancel()`
  (the `onCancel` prop = `pickClaim.routeCancel`), never `inspector.cancel()` directly.
- **STEP 3** — consolidate the recording predicate: point `recorder.isActive`,
  `LeftPanelTools:37`, `interceptor:292` at the canonical `recordings.isRecording`;
  delete the dead/duplicate derivations.
- **STEP 4** — collapse the selection mutex into a `selectedTarget` discriminated
  union behind the existing `activePickId`/`activeRegionId` getters (derived shims);
  fix `submitPick` to clear the partner by construction.
- **STEP 5** — introduce the `InteractionMachine` singleton (mode enum + one reducer
  per transition); wire `inspector.active`, `regionDraft.drafting`,
  `quickCommentMode.active`, `pickClaim.current`-presence as `$derived` shims. No
  call-site edits yet.
- **STEP 6** — atomic transitions: move mode-exit out of `submitPick` into a `submit`
  transition; route `App.onQuickPick`, `LeftPanelTools`, `FloatingRecorderToolbar`
  through the same `enterPick`/`submit`/`cancel` dispatch; collapse the two claim ids.
- **STEP 7** — derive `panelCollapse` + interceptor + recorder lifecycle from the
  machine; delete the now-unused real-state flags and the parallel `.grid--quick` CSS
  path. Full vitest + python arch tests green.

## Open questions (decide before STEP 5)

1. **Recording = orthogonal axis** (recommended, evidence-backed: backend
   `add_pick`/`add_region` COL-6 auto-links during recording; `App.branches.test`
   proves co-existence) — confirm it is never a member of the `mode` enum.
2. Quick-comment: first-class peer `mode` vs a `mode==='inspecting' + quickPending`
   sub-state? It was deliberately decoupled from `inspector.active` to dodge an earlier
   "picker lingers" bug (`App.svelte` tombstone) — folding it back must not reintroduce that.
3. Tool strip: always-on chrome (render `LeftPanelTools` outside the collapsible Panel)
   vs collapse-but-keep-interactive?
4. `FloatingRecorderToolbar`: separate mode-entry surface, or an alternate skin
   dispatching the same transitions (→ drop the `pick:recorder-toolbar` claim id)?
5. `selectedTarget`: is single-selection the invariant (RightPanel/svg-renderer
   currently disagree on whether a pick and a region can be selected at once)?
6. Does the backend snapshot ever legitimately carry `inspector.active=false` mid-pick,
   or is the local machine authoritative over the hydrated mirror during an in-flight
   interaction?
