# services/regions

Schema 0.4.0+: Regions sind first-class räumliche Container über Picks. User zieht eine box auf der page → alle visible DOM-elements im rect werden zu Picks (mit fingerprint-dedup gegen existing) + eine Region wird angelegt, die diese als `member_pick_ids` referenziert.

| Service                | Responsibility                                                                                                                                                                                                                                            | Datei                    |
| ---------------------- | --------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------- | ------------------------ |
| `region-scanner`       | DOM-walk → Liste von `{pick, element}` für alle visible+contained+meaningful elements im viewport-rect. Drei-Stufen-Algo: ≥80% bbox-containment → deepest-match-filter → min-area (50px²).                                                                | `region-scanner.ts`      |
| `regionDraft`          | localState state-machine fürs drag-rect-Drawing. `start/setOrigin/updateCurrent/commit/cancel`, derived `rect` ($state-normalisiert für negative drags). Commit: scanRegion → submitPick je member → submitRegion → analyzeDomRelations → submitRelation. | `region-draft.svelte.ts` |
| `buildPickFromElement` | DOM-Element → `Pick`-objekt (fresh uuid4, fingerprint, selector, rect, text-snippet, url, timestamp). Shared between InspectorLayer (single click-pick) und region-scanner (bulk-scan).                                                                   | `region-scanner.ts`      |

## Containment-Algorithmus (region-scanner)

```
ASCII der drei filter-stufen für eine drawn region:

Step 1 — visible + contained (≥80% bbox-area-overlap):
  ┌────── region ──────┐
  │ <html> bbox=viewport → 5% overlap → SKIP (<80%)
  │  <body> bbox=most-of-viewport → 30% → SKIP
  │   <div> bbox=column-width → 60% → SKIP
  │     <p> bbox=fully-inside → 95% → KEEP
  │     <a> bbox=fully-inside → 90% → KEEP
  └────────────────────┘

Step 2 — drop ancestors of other candidates (deepest-match):
  Candidates: [<p>, <a>]
  <p> has descendant in candidates? no  → KEEP
  <a> has descendant in candidates? no  → KEEP

Step 3 — min-area-filter (skip <50px² spacers):
  <p> bbox = 600×30 = 18000px² → KEEP
  <a> bbox = 80×20 = 1600px² → KEEP

Final picks: [<p>, <a>]
```

Algorithm-konstanten in `region-scanner.ts`:

- `CONTAINMENT_THRESHOLD = 0.8` — slack für sub-pixel und nicht-pixel-genauen drags
- `MIN_BBOX_AREA = 50` — filtert decorative spans / spacer-divs

## Commit-flow

```
regionDraft.commit():
  ├─ scanRegion(rect) → Array<{pick, element}>
  │
  ├─ für jedes scanned-pick:
  │   id = backendState.inspector.submitPick(pick)   ← fingerprint-dedup gegen existing
  │   collect pickElementRef = {pickId: id, element}
  │
  ├─ submitRegion({
  │    region_id, rect (page-absolute, scrollX+clientX),
  │    member_pick_ids, viewport_snapshot, color_index
  │   })  ← wire: region_created_requested
  │
  └─ analyzeDomRelations(pickElementRefs, existingRelations)
       │
       ├─ pair-wise: containment? → part_of (child→parent)
       │             sonst LCA + tree-distance ≤ 4? → relates_to (symmetric)
       │
       └─ für jede derived relation: submitRelation
```

## Schema 0.6.0+ region.rect = page-absolute

Drawn-rect wird zur commit-zeit von viewport-coords (drag-rect) zu page-absoluten coords (`scrollX + clientX`) konvertiert. Begründung: scroll-invariante storage, direkt usable für screenshot-API (Playwright `page.screenshot({clip: rect})`). Plus `viewport_snapshot` field: scroll/viewport/document-dimensionen zum draw-zeitpunkt → screenshot-canvas-context + future layout-drift-detection.

Render via `positionService.liveRectForRegion`: bounding-box der live member-pick-rects (anchored, folgt reflow). Wenn keine members resolvable → null → kein render (ground-truth-principle).

## Cross-refs

- `services/relations-analyzer/` — DOM-post-processing-step nach scan
- `services/element-locator/` — `buildFingerprint` + `generateCssSelector` (shared mit InspectorLayer)
- `services/color-palette/` — color_index assignment für visual identity
