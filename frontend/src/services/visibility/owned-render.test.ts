/**
 * owned-render.test.ts — unit tests for the `isOwnedFor` overlay render gate.
 *
 * `isOwnedFor(entity, currentSessionId)` is the single ownership predicate that
 * gates whether an entity's box/border/edge is drawn in the overlay. It is
 * isolated here so the gate logic is unit-tested independent of Svelte runes.
 *
 * Rules (matches the §Ownership & domain model "Overlay render gate" spec):
 *   - owned entity (origin_session === currentSessionId) → true
 *   - foreign entity (origin_session !== currentSessionId) → false
 *   - currentSessionId === null → true (degrade: render all)
 *
 * Spec: docs/specs/2026-06-01-domain-scoped-owner-aware-visibility-design.md
 */
import { describe, expect, test } from 'vitest';
import { isOwnedFor } from './ownership';

describe('isOwnedFor', () => {
  test('owned entity (origin_session === currentSessionId) → true', () => {
    expect(isOwnedFor({ origin_session: 'sess-1' }, 'sess-1')).toBe(true);
  });

  test('foreign entity (origin_session !== currentSessionId) → false', () => {
    expect(isOwnedFor({ origin_session: 'sess-other' }, 'sess-1')).toBe(false);
  });

  test('currentSessionId === null → true (degrade: render all)', () => {
    expect(isOwnedFor({ origin_session: 'sess-other' }, null)).toBe(true);
    expect(isOwnedFor({ origin_session: null }, null)).toBe(true);
    expect(isOwnedFor({ origin_session: undefined }, null)).toBe(true);
  });

  test('entity with null origin_session is foreign to a concrete session', () => {
    expect(isOwnedFor({ origin_session: null }, 'sess-1')).toBe(false);
  });

  test('entity with undefined origin_session is foreign to a concrete session', () => {
    expect(isOwnedFor({ origin_session: undefined }, 'sess-1')).toBe(false);
    expect(isOwnedFor({}, 'sess-1')).toBe(false);
  });
});
