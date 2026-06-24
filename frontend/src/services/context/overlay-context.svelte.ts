/**
 * overlay-context.svelte.ts — the reactive OverlayContext singleton.
 *
 * Holds the current {@link OverlayContext} in a Svelte `$state` so that
 * overlay consumers (`svg-renderer` gate, LeftPanel visibility grouping, any
 * future "should this box look different?" decision) read a single reactive
 * source of truth and re-render when it refreshes.
 *
 * `refresh()` re-derives the context from the live main-world via
 * {@link createOverlayContext} — `window.__fp.getState()` for the session id
 * and `window.location` for the URL. This is the fix for the stale-mount bug:
 * the context is NEVER a one-shot mount snapshot, it can be re-derived on
 * demand (e.g. after every state snapshot, or after navigation).
 *
 * This module is the reactive *wrapper*; the pure value object + factory live
 * in `overlay-context.ts` (no Svelte runes there, so they stay unit-testable
 * without a Svelte environment).
 *
 * backendState category (session identity is backend-authoritative,
 * survives cross-origin nav because it lives in module scope, not page JS).
 * Single `window.__fp` namespace respected — read-only consumer of getState.
 */

import {
  createOverlayContext,
  isAboutBlankFor,
  overlayContextFrom,
  type OriginBearing,
  type OverlayContext,
} from './overlay-context';

class OverlayContextStore {
  /** Current context. Defaults to a fully-degraded context (null session). */
  current = $state<OverlayContext>(overlayContextFrom({ url: null, currentSessionId: null }));

  /**
   * Re-derive the context from the live main-world. Safe to call repeatedly —
   * each call reflects the *current* `getState()` session id + `location` URL.
   */
  async refresh(): Promise<void> {
    this.current = await createOverlayContext();
  }

  /** Convenience: ownership decision against the current context. */
  isOwned(entity: OriginBearing): boolean {
    return this.current.isOwned(entity);
  }

  /** Convenience: current page hostname (lowercased), or null. */
  hostname(): string | null {
    return this.current.hostname();
  }

  /** Convenience: current backend session id, or null. */
  get currentSessionId(): string | null {
    return this.current.currentSessionId;
  }

  /**
   * True when the current page URL is `about:blank`.
   *
   * Derives reactively from `this.current` (which is `$state`): any consumer
   * reading this inside a `$derived` or Svelte template re-evaluates when
   * `refresh()` reassigns `current`. A `null` URL (degraded / pre-refresh)
   * returns `false` — detection is never implicit.
   */
  get isAboutBlank(): boolean {
    return isAboutBlankFor(this.current.url);
  }

  /** Inject an explicit context (tests / reconstruction). */
  setForTests(state: { url: URL | null; currentSessionId: string | null }): void {
    this.current = overlayContextFrom(state);
  }

  /** Reset to the fully-degraded default between test suites. */
  resetForTests(): void {
    this.current = overlayContextFrom({ url: null, currentSessionId: null });
  }
}

export const overlayContext = new OverlayContextStore();
