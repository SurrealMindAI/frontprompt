/**
 * ownership.ts — pure ownership predicate for the overlay render gate.
 *
 * `isOwnedFor` is the single decision point for whether an entity (pick /
 * region / relation) belongs to the current session, and therefore whether
 * its box / border / edge may be drawn in the overlay.
 *
 * Pure (no Svelte runes, no globals, no side effects) so it can be unit-tested
 * independent of Svelte and reused by both the list view (visibleGroups) and
 * the overlay render gate.
 *
 * Spec: docs/specs/2026-06-01-domain-scoped-owner-aware-visibility-design.md
 * §Ownership & domain model — "Overlay render gate"; §error handling —
 * null degrade applies to BOTH list and overlay.
 */

/**
 * True when the entity is owned by the current session, OR when there is no
 * current session (degrade mode → render all).
 *
 *   - `currentSessionId === null` → `true` (degrade: render every entity)
 *   - owned (`entity.origin_session === currentSessionId`) → `true`
 *   - foreign (`entity.origin_session !== currentSessionId`) → `false`
 */
export function isOwnedFor(
  entity: { origin_session?: string | null },
  currentSessionId: string | null
): boolean {
  return currentSessionId === null || entity.origin_session === currentSessionId;
}
