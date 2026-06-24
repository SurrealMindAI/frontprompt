/**
 * PositionTracker — reactive tick für live-rect re-eval.
 *
 * Die live-rect-lookups in PositionService (querySelector + bbox) sind impure
 * — ihr Output kann sich ändern obwohl der ``Pick``/``Region``-state unverändert
 * bleibt (window resize, scroll, layout-shift). Svelte $derived tracked
 * lediglich svelte-managed state; DOM-änderungen sind unsichtbar.
 *
 * Lösung: ein dünner $state ``tick``. Consumers lesen ``tracker.tick`` im
 * derived expression als reactive dep, und wir incrementen ``tick`` per
 * resize/scroll-listener (registriert via ``setupPositionTracker()`` aus
 * App.svelte). So flickt das overlay nach resize sauber durch.
 *
 * Pure localState (UI-concern). Cross-origin nav resettet den
 * counter — acceptable.
 */

class PositionTracker {
  /**
   * Monotonic counter. Caller machen ``positionTracker.tick`` als reactive
   * dep in ihren ``$derived`` — wenn wir hier bumpen, re-evaluieren alle
   * abhängigen derived.
   */
  tick = $state(0);

  bump(): void {
    this.tick += 1;
  }
}

export const positionTracker = new PositionTracker();

/**
 * Module-level RAF-pending flag. Plain boolean — NOT $state. A $state pending
 * flag creates a dual-reactive-source problem: the Svelte
 * runtime and the RAF callback would race to update the same logical value.
 * Reset to false in cleanup callback for HMR safety.
 */
let _rafPending = false;

/**
 * One-shot setup vom App.svelte mount-pfad. Registriert resize + scroll
 * listeners die ``positionTracker.bump()`` via RAF-batching callen.
 * Returns cleanup-callback für $effect.
 *
 * RAF batching: all scroll/resize events within one animation frame collapse
 * into a single tick increment — matches the visual update rate of the browser.
 * At 60fps this reduces $derived re-evaluations from O(events) to O(frames).
 *
 * Scroll wird mit ``capture: true`` registriert damit nested-scrolls (z.B.
 * inner-div scrollt) auch unsere bump triggern.
 */
export function setupPositionTracker(): () => void {
  const onChange = (): void => {
    if (_rafPending) return;
    _rafPending = true;
    requestAnimationFrame(() => {
      _rafPending = false;
      positionTracker.bump();
    });
  };
  window.addEventListener('resize', onChange);
  window.addEventListener('scroll', onChange, true);
  return () => {
    window.removeEventListener('resize', onChange);
    window.removeEventListener('scroll', onChange, true);
    // Reset pending flag for HMR safety (rapid unmount/remount cycles).
    _rafPending = false;
  };
}
