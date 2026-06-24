/**
 * findScrollableAncestor — walk up DOM bis zum ersten echten scroller.
 *
 * "Scrollable" bedeutet:
 *   - ``overflow-y: auto | scroll`` AND ``scrollHeight > clientHeight``, ODER
 *   - ``overflow-x: auto | scroll`` AND ``scrollWidth > clientWidth``
 *
 * Beide overflow + scroll-overflow-checks sind nötig: ein ``<div overflow:auto>``
 * mit content < container scrollt NICHT (sieht "scrollbar" aus, ist's aber nicht).
 *
 * Fallback wenn keiner gefunden: ``document.scrollingElement`` (= meist ``<html>``
 * in standards-mode, ``<body>`` in quirks). Das ist der "window-scroll" target.
 *
 * Warum nicht einfach window.scrollBy:
 *   Moderne SPAs (Gmail, Google, Discord, Slack, ...) routen scroll oft auf
 *   custom containers für virtualization / sticky headers / etc. Body kann
 *   `overflow:hidden` haben (z.B. wegen consent-modal). Dann ist
 *   window-scroll ein no-op aber DAS PAGE SCROLLT TROTZDEM — auf einem
 *   anderen container. Wir müssen den finden.
 */
export function findScrollableAncestor(start: Element): Element {
  let node: Element | null = start;
  while (node) {
    if (isScrollable(node)) return node;
    if (node === document.documentElement) break;
    node = node.parentElement;
  }
  return document.scrollingElement ?? document.documentElement;
}

/**
 * Check ob ein element scrollable ist: overflow erlaubt scroll UND content
 * tatsächlich overflowt (sonst gibt's nichts zu scrollen).
 *
 * Note: ``getComputedStyle`` ist günstig auf modernen browsers (cached) aber
 * trotzdem nicht gratis — caller sollten das ergebnis nicht in hot-loops
 * neu berechnen wenn vermeidbar.
 */
export function isScrollable(el: Element): boolean {
  const style = window.getComputedStyle(el);
  const canScrollY =
    (style.overflowY === 'auto' || style.overflowY === 'scroll') &&
    el.scrollHeight > el.clientHeight;
  const canScrollX =
    (style.overflowX === 'auto' || style.overflowX === 'scroll') && el.scrollWidth > el.clientWidth;
  return canScrollY || canScrollX;
}
