/**
 * generateCssSelector — Firefox-DevTools-style CSS selector path.
 *
 * Algorithm (modeled after Scrapling's ``SelectorsGeneration._general_selection``,
 * /scrapling/core/mixins.py):
 *
 *   1. Falls das Element eine stabile ID hat → ``#id`` direkt zurückgeben (kürzer).
 *   2. Sonst: ancestor-chain bauen mit ``tag:nth-of-type(n)``.
 *      - n = 1-based Position unter same-tag-siblings am selben parent.
 *      - Standard-Cap: 4 Levels (genug zur Identifikation in 99% der Fälle).
 *      - opts.fullPath=true → bis hoch zu ``html`` (für Phase-2 scrapling-relocate fallback).
 *
 * @example
 *   <div id="hero-cta">…</div>  →  '#hero-cta'
 *   <body><main><p>x</p><p>y</p></main></body>  → 'p:nth-of-type(2)' für y
 *
 * Output ist immer ein valider CSS-selector der mit document.querySelector
 * konsumiert werden kann.
 */
import { isStableId } from './stable-id';

export interface GenerateOptions {
  /** Wenn true: gesamte ancestor-chain bis html. Default: gecappt bei 4 Levels. */
  fullPath?: boolean;
}

const DEPTH_CAP = 4;

export function generateCssSelector(el: Element, opts: GenerateOptions = {}): string {
  // Fast-path: stabile id → eindeutig genug
  const id = el.getAttribute('id');
  if (isStableId(id)) {
    return `#${cssEscape(id!)}`;
  }

  const parts: string[] = [];
  let node: Element | null = el;
  const cap = opts.fullPath ? Infinity : DEPTH_CAP;

  while (node && node !== document.documentElement) {
    const tag = node.tagName.toLowerCase();
    const idx = nthOfType(node);
    parts.unshift(`${tag}:nth-of-type(${idx})`);
    if (parts.length >= cap) break;
    node = node.parentElement;
  }

  return parts.join(' > ');
}

/** 1-based position des Elements unter same-tag-siblings am selben parent. */
function nthOfType(el: Element): number {
  const parent = el.parentElement;
  if (!parent) return 1;
  let n = 0;
  for (const child of parent.children) {
    if (child.tagName === el.tagName) {
      n++;
      if (child === el) return n;
    }
  }
  return 1;
}

/**
 * CSS.escape polyfill — auch ohne window verfügbar (jsdom in tests).
 * Implementiert die Subset-Regeln aus CSSOM Living Standard.
 */
function cssEscape(value: string): string {
  if (typeof CSS !== 'undefined' && typeof CSS.escape === 'function') {
    return CSS.escape(value);
  }
  // Minimal fallback — escapes chars die in CSS-Idents NICHT erlaubt sind
  return value.replace(/([^\w-])/g, '\\$1');
}
