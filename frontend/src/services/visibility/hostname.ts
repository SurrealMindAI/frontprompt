/**
 * hostname.ts — pure hostname-extraction and per-kind entity-domain helpers.
 *
 * All functions are pure (no Svelte runes, no globals, no side effects).
 * Consumed by visibleGroups (Task 4) and the overlay render gate.
 *
 * Spec: docs/specs/2026-06-01-domain-scoped-owner-aware-visibility-design.md
 * §Ownership & domain model
 */

import type { Pick, Region, Relation } from '../../_generated/state';

/**
 * Extracts the lowercased hostname from a URL string.
 *
 * Uses `new URL()` for parsing — treats any parse failure, empty string,
 * or a URL with an empty hostname (e.g. `data:` URLs) as a non-resolvable
 * address and returns `null`.
 *
 * Port numbers are stripped (`.hostname` excludes the port per the WHATWG
 * URL standard).
 */
export function hostnameOf(url: string | null | undefined): string | null {
  if (!url) return null;
  try {
    const hostname = new URL(url).hostname;
    if (!hostname) return null;
    return hostname.toLowerCase();
  } catch {
    return null;
  }
}

/**
 * Returns the hostname of a Pick's URL, or null if unparseable.
 */
export function pickDomain(pick: Pick): string | null {
  return hostnameOf(pick.url);
}

/**
 * Returns the hostname of a Region's first resolvable member Pick URL.
 *
 * Iterates `member_pick_ids` in order, looks each up in `picksById`, and
 * returns the hostname of the first one whose URL parses successfully.
 * Returns `null` when:
 *   - `member_pick_ids` is absent or empty
 *   - no member id resolves in `picksById`
 *   - all resolved member picks have unparseable URLs
 */
export function regionDomain(region: Region, picksById: Map<string, Pick>): string | null {
  const members = region.member_pick_ids;
  if (!members || members.length === 0) return null;
  for (const id of members) {
    const pick = picksById.get(id);
    if (!pick) continue;
    const domain = hostnameOf(pick.url);
    if (domain !== null) return domain;
  }
  return null;
}

/**
 * Returns the hostname of a Relation's source endpoint.
 *
 * - `source_kind === 'pick'`   → looks up the pick in `picksById`, returns its domain.
 * - `source_kind === 'region'` → looks up the region in `regionsById`, then derives
 *                                 its domain via `regionDomain` (first resolvable member).
 *
 * Returns `null` when the source id is missing from the respective map, or
 * when the derived domain is unresolvable.
 */
export function relationDomain(
  relation: Relation,
  picksById: Map<string, Pick>,
  regionsById: Map<string, Region>
): string | null {
  if (relation.source_kind === 'pick') {
    const pick = picksById.get(relation.source_id);
    if (!pick) return null;
    return pickDomain(pick);
  }
  // source_kind === 'region'
  const region = regionsById.get(relation.source_id);
  if (!region) return null;
  return regionDomain(region, picksById);
}
