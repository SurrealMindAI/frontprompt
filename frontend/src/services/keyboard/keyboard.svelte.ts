/**
 * Global subscribable keyboard service.
 *
 * Capture-phase ``keydown`` listener auf ``window`` — fires bevor Page-Elements
 * den Key swallowen können. Subscribers können sich pro Key-Name anhängen
 * (z.B. ``'Escape'``, ``'ArrowDown'``).
 *
 * Lazy-Install: der window-listener wird beim ersten subscribe() installiert,
 * nicht beim Modul-Load. Behält den Boot minimal.
 *
 * Mehrere Subscribers pro Key sind unterstützt — alle bekommen den event.
 * Reihenfolge: insertion-order (Set-Iteration).
 *
 * Unsubscribe via returned function. Listener wird NICHT entfernt wenn keine
 * Subscribers mehr da sind — Idle-Cost ist ein einziger no-op handler.
 *
 * @example
 *   const unsubscribe = keyboard.subscribe('Escape', () => closeModal());
 *   // later: unsubscribe();
 */

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
    for (const h of set) {
      try {
        h(e);
      } catch (err) {
        // eslint-disable-next-line no-console
        console.error('[keyboard] handler threw:', err);
      }
    }
  };

  /**
   * Register a handler for a specific KeyboardEvent.key value.
   * Returns an unsubscribe function. Idempotent — same handler subscribed
   * twice for the same key fires once (Set-semantics).
   */
  subscribe(key: string, handler: Handler): () => void {
    this.install();
    let set = this.handlers.get(key);
    if (!set) {
      set = new Set();
      this.handlers.set(key, set);
    }
    set.add(handler);
    return () => {
      const s = this.handlers.get(key);
      if (s) {
        s.delete(handler);
        if (s.size === 0) this.handlers.delete(key);
      }
    };
  }

  /** For test purposes only — clears all subscriptions + removes the listener. */
  _reset(): void {
    if (this.installed) {
      window.removeEventListener('keydown', this.onKeydown, { capture: true });
    }
    this.handlers.clear();
    this.installed = false;
  }
}

export const keyboard = new KeyboardService();
