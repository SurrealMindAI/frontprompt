# ADR-019 — Ground-Truth Overlay Rendering (no snapshot fallback)

> Part of the frontprompt [Architecture Decision Records](./index.md).

**Status**: accepted
**Date**: 2026-05-20
**Cross-References**: [ADR-018 State Classification](./ADR-018-state-classification-local-vs-backend.md), [ADR-016 Bridge via expose_function](./ADR-016-expose-function-bridge.md)

---

## Context

Das Inspector-Feature (picks + regions + relations) zeichnet rect-borders + bezier-edges in einem SVG-Overlay über die page. Stored daten (Schema 0.4.0+):

| Item | Stored fields |
|---|---|
| `Pick.element.rect` | bbox-snapshot zum pick-zeitpunkt (viewport-relativ) |
| `Pick.element.selector` | CSS-selector path zum element |
| `Pick.element.fingerprint` | Scrapling-equivalent struct |
| `Region.rect` | drawn-rect (Schema 0.6.0+: page-absolute) |
| `Region.member_pick_ids` | references zu picks |

Per ADR-018 sind diese items **backend-state** — überleben cross-origin navigation. Frage: was rendert das overlay nach navigation?

`example.com → google.com`:
- Picks + regions bleiben im Python-StateManager
- Overlay-mirror hydratet die items beim post-nav-OverlayReady
- Stored `pick.element.rect` zeigt auf die EHEMALIGE viewport-position auf example.com
- Auf google.com ist diese position willkürlich (anderer content)

Naive fallback "wenn live-lookup fehlt, render stored snapshot" → **ghost-boxes**: rechteckige hülsen schweben im google-suchergebnis an stellen wo example.com's `<p>` mal war. Visuell verwirrend + suggeriert dem User dass das overlay konfus ist.

## Decision

**Live-DOM ist die einzige source of truth für rendering. Kein fallback auf stored rect-snapshots.**

Concrete:

1. `positionService.liveRectForPick(pick)` returnt `ElementRect | null`:
   - Try `document.querySelector(pick.element.selector).getBoundingClientRect()`
   - Wenn element nicht da / selector invalid / bbox 0×0 → **return null**
   - Kein fallback auf `pick.element.rect`

2. `positionService.liveRectForRegion(region, picks)` returnt `ElementRect | null`:
   - Bounding-box der live-rects der member-picks
   - Wenn keine member-picks resolvable → **return null**
   - Kein fallback auf `region.rect` translated-by-scroll

3. SVG-renderer skipt render-pfade wenn null:
   ```svelte
   {@const liveRect = livePickRects.get(pick.pick_id)}
   {#if liveRect}
     <rect ... />
   {/if}
   ```

4. `centerForNode` (path-planner) propagiert null → relation-DrawCommand wird verworfen wenn endpoint nicht resolvable.

## Boundary: list-display ≠ overlay-render

Crucial distinction (User-Mandate 2026-05-20):

- **State-list im LeftPanel** (Picks-Tab, Regions-Tab, Relations-Tab) zeigt items **immer** — auch wenn DOM sie nicht resolvable hat. Begründung: User soll wissen was er in der session captured hat. Pick auf example.com bleibt visible in der liste auch nach nav zu google.
- **Overlay (SVG-rects, bezier-edges)** zeigt items **nur wenn live**. Begründung: ghost-boxes irritieren mehr als sie helfen.

## Edge case bewusst akzeptiert

Selector-collision: page A hat selector `body > div:nth-of-type(1) > p:nth-of-type(2)` für ein bestimmtes element. Page B hat ZUFÄLLIG selber selector-path aber semantisch anderes element. Live-lookup succeeded → rect renderert an position auf page B die nichts mit dem ursprünglichen element zu tun hat.

**Frequency**: niedrig. Selector-paths sind strukturell, identische DOM-shapes zwischen disjunkten sites sind selten.

**Worst case**: wrong-position-render. Nicht no-render. Akzeptiert für KISS.

**Phase-2-Upgrade-path**: fingerprint-verify in `liveRectForPick` — vergleich gespeicherter `Pick.element.fingerprint` mit live-element-fingerprint, return null wenn divergent. Reuses Scrapling's `element_to_dict`-equivalent (already stored).

## Reactivity-Requirement

Live-lookups sind impure — gleicher input (pick) kann verschiedene rects returnen über die zeit (resize, scroll, layout-shift, dom-add/remove). Svelte $derived tracked nur svelte-managed state; DOM-änderungen sind unsichtbar.

**Lösung**: `positionTracker.tick` — ein $state counter gebumpt bei `window.resize` + `scroll` (capture, für nested). Consumer ($derived in svg-renderer, RelationsLayer) lesen `tick` als reactive dep:

```ts
const livePickRects = $derived.by(() => {
  void positionTracker.tick;  // reactive dep
  return new Map(picks.map((p) => [p.pick_id, positionService.liveRectForPick(p)]));
});
```

Setup einmal in App.svelte mount-pfad:
```ts
$effect(() => setupPositionTracker());
```

## Consequences

### Positive
- Keine ghost-boxes nach cross-origin nav, page-content-change, DOM-mutations
- Live overlay folgt reflow, scroll, resize automatisch
- Mental model klar: "wenn ich es nicht sehe, ist es nicht im DOM (oder selector-collision)"
- Picks/regions in der state-list bleiben — kein info-verlust

### Negative
- Live-lookup pro pick/region pro render-frame: O(n) querySelector-calls. Bei großen n + häufigem tick-bump merkbar. Mitigation: aktuell <100 items typisch, ~100 queries pro frame ist <1ms.
- Selector-collision-edge-case (siehe oben) — fingerprint-verify aufgeschoben.
- positionTracker als zusätzliche service-API.

## Alternativen erwogen

### Alt 1 — Stored snapshot als fallback (rejected)
Produziert ghost-boxes. Verworfen empirisch nach 2026-05-20 smoke-test (User-Bericht).

### Alt 2 — Page-absolute coords mit current-scroll-translation (rejected for picks)
Vorgeschlagen für regions in Schema 0.6.0 (drawn-rect-storage) UND als pick-fallback. Verworfen für picks: die liveDom-lookup ist primary, fallback würde dieselben ghost-boxes nach nav erzeugen. **Behalten für regions** (drawn-rect → page-absolute) aber NUR für screenshot-API-storage, nicht als render-fallback.

### Alt 3 — Show-with-warning (rejected)
Render ghost-box mit "stale" badge. Visuelle complexity, der User würde mental nicht klar "stale vs live" unterscheiden. KISS-Verstoß.

## Related

- [ADR-018 State Classification](./ADR-018-state-classification-local-vs-backend.md) — listet picks/regions als backend-state
- [ADR-002 Single-Writer](./ADR-002-single-writer-helland.md) — StateManager-discipline
- frontprompt CLAUDE.md "Cross-origin survival" section
- `frontend/src/services/relations/position-service.svelte.ts` — implementation
- `frontend/src/services/relations/position-tracker.svelte.ts` — reactivity
