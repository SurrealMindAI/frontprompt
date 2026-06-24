/**
 * PositionService — node_id (pick oder region) → viewport rect.
 *
 * **Ground-truth principle**: Picks/regions werden
 * im overlay NUR gerendert wenn ihre underlying DOM-elements tatsächlich auf
 * der aktuellen page sichtbar sind. Sonst kriegen wir nach cross-origin nav
 * (example.com → google.com) "Ghost-Boxes" an Stellen wo gar nichts mehr ist.
 *
 * Konsequenz: alle live-rect-methods returnen ``ElementRect | null``. Caller
 * (svg-renderer, path-planner) müssen null filtern. Picks/Regions BLEIBEN in
 * der state-list (Picks-Tab usw.) — nur die visuelle overlay-darstellung
 * verschwindet wenn das Element nicht resolvable ist.
 *
 * **KISS, kein Fingerprint-Verify**: aktuell prüfen wir nur selector-presence.
 * Edge-case "neue page hat zufällig dasselbe selector-path" → wrong-position-
 * render statt no-render. Akzeptiert für jetzt; Phase 2 kann fingerprint-
 * verify nachziehen (vergleich gespeicherter fingerprint mit live-element).
 *
 * **Live-rect lookup**: ``document.querySelector(selector).getBoundingClientRect()``
 * — overlay wandert so mit beim resize, scroll, layout-shift. Reactivity über
 * ``positionTracker.tick`` als $derived-dependency.
 *
 * **Region-live-rect**: Regions haben kein eigenes DOM-element. Berechnung
 * als bounding-box der live-rects ihrer member-picks. Wenn keine members oder
 * alle lookups null returnen → return null (kein page-absolute fallback,
 * sonst ghost-boxes nach nav).
 */
import type {
  ElementRect,
  Pick,
  Region,
  RelationEndpointKind,
  Viewport,
} from '../../_generated/state';

export interface RectCenter {
  cx: number;
  cy: number;
}

export class PositionService {
  /**
   * Cache: pick_id → resolved Element | null.
   * Key is pick.pick_id (unique per pick by construction). A null value means
   * "selector was queried but element not found" — avoids repeated failed lookups.
   * Cleared entirely by the MutationObserver on any DOM structural change.
   */
  private _selectorCache = new Map<string, Element | null>();

  /**
   * MutationObserver that clears _selectorCache on any DOM childList change.
   * Registered on document.documentElement to catch subtree mutations.
   * Disconnect via dispose() for cleanup (e.g. test teardown, HMR).
   * Note: cross-origin navigation causes page reload which replaces the overlay
   * entirely — a fresh PositionService singleton is constructed per injected
   * context and re-attaches via _startObserving() (deferred to DOMContentLoaded
   * when the document root is not yet present).
   */
  private _observer: MutationObserver;

  constructor() {
    this._observer = new MutationObserver(() => {
      this._selectorCache.clear();
    });
    this._startObserving();
  }

  /**
   * Attach the cache-invalidation observer to the document root.
   *
   * The overlay bundle is injected via `add_init_script` at document_start,
   * at which point `document.documentElement` does not exist yet. The module-load
   * singleton (`export const positionService = new PositionService()`) therefore
   * runs this constructor before any DOM exists — calling `observe(null)` throws
   * "parameter 1 is not of type 'Node'" and aborts the entire bundle bootstrap
   * (no overlay host ever mounts). Guard for the root and otherwise defer to
   * DOMContentLoaded, mirroring the deferred mount in main.ts.
   */
  private _startObserving(): void {
    const root = document.documentElement;
    if (root) {
      this._observer.observe(root, { childList: true, subtree: true });
    } else {
      document.addEventListener('DOMContentLoaded', () => this._startObserving(), { once: true });
    }
  }

  /** Disconnect MutationObserver. Call from App.svelte $effect cleanup. */
  dispose(): void {
    this._observer.disconnect();
  }

  /**
   * Live rect für einen Pick via querySelector(selector) → bbox.
   * Returns ``null`` wenn das element NICHT auf der current page resolvable
   * ist (cross-origin nav, element gelöscht, selector invalid).
   *
   * querySelector result cached per pick_id, invalidated on DOM mutations.
   */
  /**
   * Resolve a Pick's live DOM element via querySelector(selector), cached per
   * pick_id (invalidated on DOM mutation). Returns ``null`` when the
   * element is not resolvable on the current page. Exposed so consumers that
   * need the element itself — e.g. background-colour sampling for dynamic
   * marker contrast — reuse the same cache as the rect lookups.
   */
  liveElementForPick(pick: Pick): Element | null {
    let el: Element | null | undefined = this._selectorCache.get(pick.pick_id);
    if (el === undefined) {
      // Cache miss — resolve and store
      try {
        el = document.querySelector(pick.element.selector);
      } catch {
        // selector invalid (z.B. CSS.escape gap) → not present
        el = null;
      }
      this._selectorCache.set(pick.pick_id, el);
    }
    return el ?? null;
  }

  liveRectForPick(pick: Pick): ElementRect | null {
    const el = this.liveElementForPick(pick);
    if (el) {
      const r = el.getBoundingClientRect();
      if (r.width > 0 && r.height > 0) {
        return { x: r.x, y: r.y, width: r.width, height: r.height };
      }
    }
    return null;
  }

  /**
   * Live rect für eine Region — bounding-box der live-rects ihrer member-picks,
   * expanded by the original drawn padding delta.
   *
   * **Padding preservation (sub-plan 01)**: ``region.rect`` is page-absolute and
   * stores the original drawn bounding box. The drawn padding delta is
   * ``region.rect`` minus the member bbox at draw time. We re-apply the same
   * per-edge delta at render time so the visual bounding box matches the user's
   * spatial intent, not just the naked member-pick bbox.
   *
   * Guard: negative padding values (member exceeds drawn rect due to DOM reflow)
   * are clamped to zero — we never shrink below the live member bbox.
   *
   * Returns ``null`` wenn die region keine member-picks hat ODER keiner der
   * member-picks auf der aktuellen page resolvable ist. Bewusst KEIN
   * page-absolute fallback: das würde nach cross-origin nav "Ghost-Regions"
   * an alten coordinates rendern.
   */
  liveRectForRegion(region: Region, picks: readonly Pick[]): ElementRect | null {
    // O(n×m) complexity — n = member_pick_ids.length, m = picks.length.
    // Array.find runs m comparisons per member. Negligible at typical session sizes
    // (n < 50, m < 100). Flag for sessions with N > 500 picks OR m > 500 region-members.
    // Phase-2 fix: caller pre-builds Map<pickId, Pick> and passes it in, reducing to O(n).
    const memberPicks = (region.member_pick_ids ?? [])
      .map((id) => picks.find((p) => p.pick_id === id))
      .filter((p): p is Pick => p !== undefined);
    if (memberPicks.length === 0) return null;
    const rects = memberPicks
      .map((p) => this.liveRectForPick(p))
      .filter((r): r is ElementRect => r !== null);
    if (rects.length === 0) return null;

    // Raw member bounding box (viewport-relative)
    const x1 = Math.min(...rects.map((r) => r.x));
    const y1 = Math.min(...rects.map((r) => r.y));
    const x2 = Math.max(...rects.map((r) => r.x + r.width));
    const y2 = Math.max(...rects.map((r) => r.y + r.height));

    // Padding preservation: expand by original drawn padding delta.
    // region.rect is page-absolute; convert to current viewport coords.
    const drawnX = region.rect.x - window.scrollX;
    const drawnY = region.rect.y - window.scrollY;
    const drawnX2 = drawnX + region.rect.width;
    const drawnY2 = drawnY + region.rect.height;

    // Per-edge deltas: how far the member bbox edges are inside the drawn rect.
    // Clamp to 0 to never shrink below the live member bbox.
    const padLeft = Math.max(0, x1 - drawnX);
    const padTop = Math.max(0, y1 - drawnY);
    const padRight = Math.max(0, drawnX2 - x2);
    const padBottom = Math.max(0, drawnY2 - y2);

    const result = {
      x: x1 - padLeft,
      y: y1 - padTop,
      width: x2 - x1 + padLeft + padRight,
      height: y2 - y1 + padTop + padBottom,
    };

    // Layout-drift detection (sub-plan 02): warn when document dimensions differ
    // significantly from when the region was drawn.
    if (region.viewport_snapshot) {
      const currentW = document.documentElement.scrollWidth;
      const currentH = document.documentElement.scrollHeight;
      if (detectLayoutDrift(region.viewport_snapshot, currentW, currentH)) {
        const snap = region.viewport_snapshot;
        console.warn(
          `[frontprompt] region ${region.region_id.slice(0, 6)} drawn at ${snap.document_w}×${snap.document_h}, current page is ${currentW}×${currentH} — rect may be stale`
        );
      }
    }

    return result;
  }

  /**
   * Center-koordinaten in viewport-pixels für den pick. Returns null wenn
   * pick unbekannt ODER element nicht resolvable auf current page.
   */
  centerForPick(pickId: string, picks: readonly Pick[]): RectCenter | null {
    const pick = picks.find((p) => p.pick_id === pickId);
    if (!pick) return null;
    const r = this.liveRectForPick(pick);
    if (!r) return null;
    return { cx: r.x + r.width / 2, cy: r.y + r.height / 2 };
  }

  /** Center für eine Region. Returns null bei nicht-resolvable members. */
  centerForRegion(
    regionId: string,
    regions: readonly Region[],
    picks: readonly Pick[]
  ): RectCenter | null {
    const region = regions.find((r) => r.region_id === regionId);
    if (!region) return null;
    const r = this.liveRectForRegion(region, picks);
    if (!r) return null;
    return { cx: r.x + r.width / 2, cy: r.y + r.height / 2 };
  }

  /** Dispatcher — Schema-0.4.0-heterogeneous-Relation-endpoint to center. */
  centerForNode(
    nodeId: string,
    nodeKind: RelationEndpointKind,
    picks: readonly Pick[],
    regions: readonly Region[]
  ): RectCenter | null {
    if (nodeKind === 'pick') return this.centerForPick(nodeId, picks);
    return this.centerForRegion(nodeId, regions, picks);
  }
}

/** Singleton — Service selber ist stateless (state lebt in positionTracker). */
export const positionService = new PositionService();

/**
 * Detects layout drift between a stored viewport snapshot and current page dimensions.
 *
 * Returns true when either document width or document height deviates by more than
 * ``thresholdPx`` (default 50px — a deliberate responsive-breakpoint-sized delta;
 * single-pixel reflow noise should not trigger).
 *
 * Pure function — no side effects. Exported for direct testing and for use in
 * RegionItem.svelte's drift indicator.
 */
export function detectLayoutDrift(
  stored: Viewport,
  currentW: number,
  currentH: number,
  thresholdPx = 50
): boolean {
  return (
    Math.abs(currentW - stored.document_w) > thresholdPx ||
    Math.abs(currentH - stored.document_h) > thresholdPx
  );
}
