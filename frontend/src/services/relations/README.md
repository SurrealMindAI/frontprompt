# services/relations — responsibility table

SRP-services für das Relations-Feature. SVG-only renderer (design decision: Canvas is a footgun here). Schema 0.4.0+: heterogeneous endpoints (Pick ↔ Pick, Pick ↔ Region, Region ↔ Region).

| Service            | Single Responsibility                                                                                                                                                                                                                                                          | Datei                          |
| ------------------ | ------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------ | ------------------------------ |
| `PositionService`  | `pick.element.rect` / region member-bbox → viewport rect via **live DOM-lookup**. Ground-truth: `liveRectForPick/Region` returnen `null` wenn selector nicht resolvable auf der aktuellen page. Caller filtert null statt fallback-zu-snapshot.                                | `position-service.svelte.ts`   |
| `PositionTracker`  | reactive `tick` $state, gebumpt bei window-resize + scroll (capture). $derived-consumer lesen `tick` als reactive dep für live-rect re-eval. Setup einmal in `App.svelte` via `setupPositionTracker()`.                                                                        | `position-tracker.svelte.ts`   |
| `PathPlanner`      | Pure `(relations, picks, regions, positions) → DrawCommand[]`. Quadratic-Bezier mit sag-offset zwischen heterogeneous endpoints (pick/region) via `centerForNode` dispatcher. Filtert relations wo source ODER target null returnt. Kind → isDirected mapping.                 | `path-planner.ts`              |
| `LookupService`    | `relationsFor(nodeId, nodeKind, relations) → {outgoing, incoming}`, `pickById`, `regionById`, `countFor`. Stateless, queries gegen zentrale relations-list. Schema-0.4.0-aware (kind-discriminator).                                                                           | `lookup-service.svelte.ts`     |
| `relationDraft`    | localState state-machine für Relation-im-Entstehen: `source/target/kind/note` mit endpoint-refs (`{id, kind}`). `start/setSource/setTarget/setKind/setNote/commit/cancel`. Phase-1 RelationsTab nutzt nur Pick-endpoints; Region-endpoints kommen in zukünftiger UI.           | `relation-draft.svelte.ts`     |
| `Renderer (svg)`   | Rendert pro DrawCommand: glow-layer, dashed bezier mit kind-color, endpoint-pulses, midpoint kind+note-label, arrowhead-marker (directed kinds). Zusätzlich pick-rect-borders (color-coded via palette) + region-rect-borders. Ground-truth: skipped wenn `liveRect === null`. | `renderer/svg-renderer.svelte` |
| `animation-tokens` | CSS-vars `--rel-dash-period`, `--rel-pulse-period`, `--rel-glow-*`, `--rel-color-{kind}` + helper `applyTokenDefaults(el)`. Single source für theming.                                                                                                                         | `animation-tokens.ts`          |

## Architecture sketch

```
RelationsLayer.svelte  (mounted by App.svelte)
   │  liest: backendState.inspector.{relations, picks, regions, active*Id}
   │         uiPrefs.{relationsVisible, regionsVisible, picksVisible, hoveredRelationId}
   │         positionTracker.tick  ← reactive dep für live-rect re-eval
   ▼
planPaths(relations, picks, regions, positionService)
   │  → DrawCommand[]  (Bezier between live centers; filters null endpoints)
   ▼
svg-renderer.svelte
   ├─ <defs>: arrow-marker per directed kind
   ├─ pick rect-borders (color = palette[color_index]; selected → solid pulsing)
   ├─ region rect-borders (color = palette[color_index]; active → dicker + fill)
   ├─ pro relation: glow + main-stroke + endpoints + midpoint-label
   └─ ground-truth: liveRect === null → skip render

relationDraft (localState)
   └─ commit → backendState.inspector.submitRelation
```

## Ground-truth rendering principle

Pick/region rects sind **immer live** geresolvet via `document.querySelector(selector).getBoundingClientRect()`. Wenn das fehlschlägt (cross-origin nav, element gelöscht, selector invalid) → null. Renderer skippt nullable items. **Kein fallback** auf `pick.element.rect` snapshot — das produzierte ghost-boxes nach navigation. Picks/regions/relations bleiben in der state-list (LeftPanel-tabs); nur die visuelle overlay-darstellung verschwindet.

Edge-case: selector-collision auf anderer page → wrong-position-render statt no-render. Phase-2-fix via fingerprint-verify in `liveRectForPick`.

## Tests

Vitest-suites unter `__tests__/`:

- `path-planner.test.ts` — bezier control-point arithmetic, kind→isDirected mapping, degenerate same-position
- `lookup-service.test.ts` — outgoing/incoming/countFor, heterogeneous kind-discriminator
- `relation-draft.test.ts` (renamed from creation-service) — state-machine, commit→bridge-shape, ESC cancel
- `svg-renderer.smoke.test.ts` — mount-test: directed relation → `<path>` + `<marker>` + glow im shadow DOM

## Cross-refs

- `services/regions/` — region-scanner + region-draft state-machine (sibling-service)
- `services/relations-analyzer/` — DOM-post-processing nach region-scan (LCA + tree-distance)
- `services/color-palette/` — index → CSS color (32 palette)
- local vs backend state split: see ARCHITECTURE.md
- single-writer state-manager: see ARCHITECTURE.md
