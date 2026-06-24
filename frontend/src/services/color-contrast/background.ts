/**
 * DOM-side background sampling for dynamic marker contrast.
 *
 * `effectiveBackgroundColor` walks an element's ancestor chain and returns the
 * first sufficiently-opaque `background-color` (browser canvas default = white
 * when none is found — matches what the user actually sees on a bare page).
 * `contrastingColor` ties this to the pure math: given a palette HSL colour and
 * the element a marker sits over, return an HSL string that is guaranteed to
 * stand out (hue preserved, lightness flipped).
 */

import {
  type Hsl,
  type Rgb,
  adaptHslForContrast,
  formatHsl,
  parseCssColorToRgb,
  parseHsl,
  relativeLuminance,
} from './contrast';

const WHITE: Rgb = { r: 255, g: 255, b: 255 };

/**
 * Per-element background cache. getComputedStyle + ancestor-walk is too costly
 * to run for every marker on every scroll/resize tick; a WeakMap keyed by the
 * element reuses the result and lets GC reclaim entries when elements vanish.
 * Staleness on a JS-driven background change (rare) self-corrects on the next
 * full nav (fresh elements ⇒ fresh cache entries). Call `clearBackgroundCache`
 * to force re-sampling (e.g. a page-wide theme toggle), if ever wired.
 */
let _bgCache = new WeakMap<Element, Rgb>();

export function clearBackgroundCache(): void {
  _bgCache = new WeakMap<Element, Rgb>();
}

/**
 * The effective background colour behind ``el`` — first opaque-enough ancestor
 * background, else white. Treats alpha ≥ 0.5 as "the background"; more
 * transparent layers are skipped (the layer below dominates the perceived bg).
 */
export function effectiveBackgroundColor(el: Element | null): Rgb {
  if (!el) return WHITE;
  const cached = _bgCache.get(el);
  if (cached) return cached;

  let node: Element | null = el;
  let result: Rgb = WHITE;
  while (node) {
    const parsed = parseCssColorToRgb(getComputedStyle(node).backgroundColor);
    if (parsed && parsed.alpha >= 0.5) {
      result = parsed.rgb;
      break;
    }
    node = node.parentElement;
  }
  _bgCache.set(el, result);
  return result;
}

/**
 * Adapt a palette HSL colour so it contrasts against the background behind
 * ``el``. Hue + saturation are preserved; only lightness shifts. Returns the
 * input unchanged if it does not parse as HSL (defensive — non-HSL inputs are
 * left to the caller's own styling).
 */
export function contrastingColor(hslString: string, el: Element | null, target?: number): string {
  const hsl: Hsl | null = parseHsl(hslString);
  if (!hsl) return hslString;
  const bgLum = relativeLuminance(effectiveBackgroundColor(el));
  return formatHsl(adaptHslForContrast(hsl, bgLum, target));
}
