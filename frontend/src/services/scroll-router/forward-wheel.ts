/**
 * forwardWheel — leite einen wheel-event an den scrollable container unter dem
 * cursor weiter (skip overlay-elemente).
 *
 * Wird vom InspectorLayer aufgerufen: die layer fängt wheel events (weil
 * pointer-events:auto + fixed + topmost), und delegiert dann manuell:
 *
 *   1. ``elementsFromPoint(x, y)`` → stack der elements unter cursor
 *   2. filter: erstes nicht-overlay-element (via ``skipPredicate``)
 *   3. walk up via ``findScrollableAncestor``
 *   4. ``scrollBy(...)`` auf dem gefundenen scroller
 *
 * Falls keine page-elements unter cursor → no-op (return).
 *
 * ``skipPredicate`` ist injectable — default skipped ``fp-overlay``-descendants.
 */
import { findScrollableAncestor } from './find-scrollable-ancestor';

export interface ForwardWheelOptions {
  /** Predicate für "skip dieses element beim suchen". Default: skip fp-overlay. */
  skipPredicate?: (el: Element) => boolean;
}

const defaultSkipPredicate = (el: Element): boolean => !!el.closest?.('fp-overlay');

export function forwardWheel(e: WheelEvent, options: ForwardWheelOptions = {}): void {
  const skipPredicate = options.skipPredicate ?? defaultSkipPredicate;

  const stack = document.elementsFromPoint(e.clientX, e.clientY);
  const underCursor = stack.find((el) => !skipPredicate(el));
  if (!underCursor) return;

  const scroller = findScrollableAncestor(underCursor);

  // window.scrollBy() vs Element.scrollBy() — APIs sind compatible (beide nehmen
  // {left, top, behavior}), aber semantik leicht different: window.scrollBy
  // scrollt das viewport (= document.scrollingElement), Element.scrollBy
  // scrollt den container. Konsolidiert: wir checken ob scroller === scrollingElement
  // und nutzen window.scrollBy (canonical für viewport-scroll).
  if (scroller === document.documentElement || scroller === document.scrollingElement) {
    window.scrollBy({ left: e.deltaX, top: e.deltaY, behavior: 'auto' });
  } else {
    scroller.scrollBy({ left: e.deltaX, top: e.deltaY, behavior: 'auto' });
  }
}
