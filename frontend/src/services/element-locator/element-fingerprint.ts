/**
 * buildFingerprint — multi-faktorieller Element-Fingerprint, Scrapling-Format.
 *
 * Mirror von Scrapling's ``_StorageTools.element_to_dict``
 * (/scrapling/core/utils/_utils.py). **Field-names sind 1:1 mit Scrapling**
 * damit Python's ``Selector.relocate(fingerprint_dict)`` in Phase 2 direkt
 * funktioniert — verifiziert durch tests/scrapling/test_fingerprint_compatibility.py.
 *
 * Phase 1: nur Storage.
 * Phase 2: Scrapling's ``Selector.relocate(fingerprint, percentage=0.7)``
 * scored gegen page.content() für adaptive Re-Location nach DOM-Drift.
 *
 * Truncation: text + parent_text auf 500 chars gecappt. Vorbeugung gegen
 * extrem große textContent (z.B. wenn der user den Body picked). Scoring in
 * Scrapling nutzt SequenceMatcher — 500 chars sind statistisch genug für
 * stabiles Matching.
 *
 * Naming notes (matched to Scrapling):
 *   - parent_name (NICHT parent_tag)
 *   - parent_attribs (NICHT parent_attributes)
 *   - siblings EXKLUDIERT das Element selbst (Scrapling-Konvention)
 */
import type { ElementFingerprint } from '../../_generated/state';

const TEXT_TRUNCATE = 500;

export function buildFingerprint(el: Element): ElementFingerprint {
  return {
    tag: el.tagName.toLowerCase(),
    attributes: getAttributes(el),
    text: truncate((el.textContent ?? '').trim(), TEXT_TRUNCATE),
    path: getPath(el),
    parent_name: el.parentElement?.tagName.toLowerCase() ?? null,
    parent_attribs: el.parentElement ? getAttributes(el.parentElement) : {},
    parent_text: truncate((el.parentElement?.textContent ?? '').trim(), TEXT_TRUNCATE),
    siblings: el.parentElement
      ? [...el.parentElement.children].filter((c) => c !== el).map((c) => c.tagName.toLowerCase())
      : [],
    children: [...el.children].map((c) => c.tagName.toLowerCase()),
  };
}

/** Alle attributes als plain dict {name: value}. Lossless für nicht-namespaced attrs. */
function getAttributes(el: Element): Record<string, string> {
  const out: Record<string, string> = {};
  for (const attr of el.attributes) {
    out[attr.name] = attr.value;
  }
  return out;
}

/** Tag-sequence von root bis (inclusive) zum element. */
function getPath(el: Element): string[] {
  const path: string[] = [];
  let node: Element | null = el;
  while (node) {
    path.unshift(node.tagName.toLowerCase());
    node = node.parentElement;
  }
  return path;
}

function truncate(s: string, max: number): string {
  return s.length <= max ? s : s.slice(0, max);
}
