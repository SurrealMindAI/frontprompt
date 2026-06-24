/**
 * fingerprintHash — canonical key für Pick-Identity-via-DOM-Position.
 *
 * Zweck: zwei Picks die das gleiche DOM-Element treffen sollen denselben
 * pick_id teilen (no duplicates): picks sollten per id > fingerprint
 * einzigartig werden.
 *
 * Strategy (Phase 1, frontend-side dedupe):
 *   - inspector-state.submitPick() berechnet diesen Hash vor add-to-list
 *   - wenn ein existing Pick mit demselben Hash da ist → reuse seine pick_id
 *   - sonst → neuer Pick mit der client-uuid
 *
 * Hash-Inputs (canonical, sorted für JSON-determinism):
 *   - tag
 *   - path (DOM-ancestor-chain tags)
 *   - attributes (sorted key-value pairs)
 *   - parent_name + parent_attribs (DOM-context)
 *   - siblings (Geschwister-tags, Scrapling-excludes-self)
 *
 * EXCLUDED:
 *   - text / text_snippet — content kann sich ändern (i18n, edits)
 *   - rect — position kann sich ändern (responsive, scroll)
 *   - timestamp — trivially unique
 *
 * Phase-2-Erweiterung: backend-side mirror der Hash-Funktion für multi-client-
 * consistency (siehe pyzod-codegen-shared-helper-todo).
 */
import type { ElementFingerprint } from '../../_generated/state';

/**
 * Stabil-deterministischer string-hash vom fingerprint. NICHT crypto-secure —
 * nur als equality-key. Identical fingerprints → identical strings.
 */
export function fingerprintHash(fp: ElementFingerprint): string {
  return JSON.stringify({
    tag: fp.tag,
    path: fp.path ?? [],
    attributes: sortedEntries(fp.attributes ?? {}),
    parent_name: fp.parent_name ?? null,
    parent_attribs: sortedEntries(fp.parent_attribs ?? {}),
    siblings: fp.siblings ?? [],
  });
}

function sortedEntries(obj: Record<string, string>): Array<[string, string]> {
  return Object.entries(obj).sort(([a], [b]) => (a < b ? -1 : a > b ? 1 : 0));
}
