/**
 * overlay-context.ts — the OverlayContext SSoT for "where we are".
 *
 * A single, focused, reconstructable value object that answers the two
 * questions the overlay's visibility logic needs:
 *
 *   1. *Where* are we?      → `url` / `hostname()`           (window.location)
 *   2. *Who* are we?        → `currentSessionId`              (backend session)
 *
 * plus the derived helpers the overlay render gate and the LeftPanel
 * visibility grouping consult: `isOwned(entity)` and `sameOrigin(other)`.
 *
 * ## Why this exists (fix/overlay-context-gating)
 *
 * The previous `sessionInfo` mirror was set ONCE at mount from the
 * `getState()` seed envelope and, per its own doc, "never updated after". When
 * that single seed read was null/stale at mount, the render gate degraded to
 * render-all *forever* — foreign-session picks drew overlay boxes on the page
 * (measured 96 SVG rects for a single owned pick). A later `getState()`
 * envelope DOES carry the correct `current_session_id`, but nothing re-read it.
 *
 * The fix is structural: ownership/origin decisions flow through a context that
 * is **derived from the live main-world** rather than a frozen mount snapshot.
 *
 *   - pure `overlayContextFrom({ url, currentSessionId })` — reconstructable +
 *     trivially testable, no globals touched.
 *   - live `createOverlayContext()` — derives `currentSessionId` on demand from
 *     `window.__fp.getState()` (the only envelope that carries it; the ongoing
 *     state_snapshot broadcasts do NOT) and the URL from `window.location`.
 *
 * Single `window.__fp` namespace is respected — we only ever *read* the
 * existing `window.__fp.getState`, never introduce a second window global.
 *
 * Spec: docs/specs/2026-06-01-domain-scoped-owner-aware-visibility-design.md
 * §Ownership & domain model — "Overlay render gate"; null degrade applies to
 * BOTH the overlay gate and the list view.
 */

/** Minimal ownership-bearing shape — Pick / Region / Relation all carry this. */
export interface OriginBearing {
  origin_session?: string | null;
}

/**
 * Immutable, reconstructable context value. Holds the page URL + current
 * backend session id; exposes the ownership/origin helpers.
 */
export interface OverlayContext {
  /** Page URL, or null when not derivable. */
  readonly url: URL | null;
  /** Backend-authoritative session id, or null (degrade → treat all as owned). */
  readonly currentSessionId: string | null;
  /** Lowercased hostname of `url`, or null when no URL. */
  hostname(): string | null;
  /**
   * True when the entity belongs to the current session, OR when there is no
   * current session (degrade mode → render/show all).
   *   - currentSessionId === null            → true (degrade)
   *   - origin_session === currentSessionId   → true (owned)
   *   - otherwise                             → false (foreign)
   */
  isOwned(entity: OriginBearing): boolean;
  /** True when `other`'s hostname equals this context's hostname. */
  sameOrigin(other: string | null | undefined): boolean;
}

function lowerHostnameOf(url: string | null | undefined): string | null {
  if (!url) return null;
  try {
    const h = new URL(url).hostname;
    return h ? h.toLowerCase() : null;
  } catch {
    return null;
  }
}

/**
 * Pure constructor — build an OverlayContext from explicit state. No globals,
 * no async, no side effects. This is the reconstructable + testable core; the
 * live factory below is a thin async wrapper that feeds it main-world values.
 */
export function overlayContextFrom(state: {
  url: URL | null;
  currentSessionId: string | null;
}): OverlayContext {
  const { url, currentSessionId } = state;
  return {
    url,
    currentSessionId,
    hostname(): string | null {
      return url ? (url.hostname ? url.hostname.toLowerCase() : null) : null;
    },
    isOwned(entity: OriginBearing): boolean {
      return currentSessionId === null || entity.origin_session === currentSessionId;
    },
    sameOrigin(other: string | null | undefined): boolean {
      const self = this.hostname();
      if (self === null) return false;
      return lowerHostnameOf(other) === self;
    },
  };
}

/**
 * Returns `true` iff `url` is non-null and its href is exactly `'about:blank'`.
 *
 * A `null` URL (degraded / pre-`refresh()` / underivable) is NOT about:blank —
 * detection must be explicit so the dashboard never appears over a real page
 * whose URL derivation merely failed.
 *
 * Note: `deriveUrl()` does `new URL(window.location.href)` and
 * `new URL('about:blank').href === 'about:blank'`, so the canonical about:blank
 * page produces a non-null URL with that exact href.
 */
export function isAboutBlankFor(url: URL | null): boolean {
  return url !== null && url.href === 'about:blank';
}

/**
 * Reads `current_session_id` from the live `window.__fp.getState()` envelope.
 *
 * `current_session_id` lives at the TOP LEVEL of the wire envelope (next to
 * `integrity_token`), NOT inside the StateSnapshot domain model — so we read it
 * off the raw record. Returns null on any failure (no __fp, no getState, null
 * seed, thrown error) → the context degrades to render-all, never throws.
 */
async function deriveSessionId(): Promise<string | null> {
  const fp = typeof window !== 'undefined' ? window.__fp : undefined;
  if (!fp?.getState) return null;
  try {
    const seed = await fp.getState();
    if (!seed) return null;
    const v = (seed as unknown as Record<string, unknown>)['current_session_id'];
    return typeof v === 'string' ? v : null;
  } catch {
    return null;
  }
}

function deriveUrl(): URL | null {
  if (typeof window === 'undefined' || !window.location) return null;
  try {
    return new URL(window.location.href);
  } catch {
    return null;
  }
}

/**
 * Live factory — derives a fresh OverlayContext from the current main-world:
 * `currentSessionId` from `window.__fp.getState()`, URL from `window.location`.
 *
 * Reconstructable by design: call it again at any time (e.g. after a state
 * snapshot arrives, or after navigation) to re-derive the *current* values —
 * it is never a frozen mount snapshot.
 */
export async function createOverlayContext(): Promise<OverlayContext> {
  const [currentSessionId, url] = [await deriveSessionId(), deriveUrl()];
  return overlayContextFrom({ url, currentSessionId });
}
