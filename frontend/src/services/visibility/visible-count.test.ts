/**
 * visible-count.ts unit tests — visibleCount returns the total item count across
 * all groups returned by visibleGroups.
 *
 * Test-Surface:
 *   - own-multi-domain (current = a.com): 2 own (a.com, b.com) + 1 foreign a.com
 *     + 1 foreign b.com → visibleCount === 3 (2 own + 1 foreign-on-current;
 *     b.com foreign is hidden because foreign entities only show on current hostname)
 *   - null degrade: currentSessionId === null → counts ALL entities
 */
import { describe, expect, test } from 'vitest';
import { visibleCount } from './visible-groups';

interface TestEntity {
  id: string;
  origin_session?: string | null;
}

function ent(id: string, sessionId: string | null | undefined): TestEntity {
  return { id, origin_session: sessionId };
}

describe('visibleCount', () => {
  test('own-multi-domain: 2 own + 1 foreign-on-current + 1 foreign-on-other → 3', () => {
    const session = 'sess-1';
    const ownA = ent('own-a', session); // domain a.com
    const ownB = ent('own-b', session); // domain b.com
    const foreignA = ent('foreign-a', 'other-session'); // domain a.com (current) → included
    const foreignB = ent('foreign-b', 'other-session'); // domain b.com (not current) → excluded

    const count = visibleCount([ownA, ownB, foreignA, foreignB], {
      currentSessionId: session,
      currentHostname: 'a.com',
      domainOf: (e) => {
        if (e.id === 'own-a' || e.id === 'foreign-a') return 'a.com';
        if (e.id === 'own-b' || e.id === 'foreign-b') return 'b.com';
        return null;
      },
    });

    expect(count).toBe(3);
  });

  test('null degrade: currentSessionId === null → counts all entities', () => {
    const e1 = ent('e1', 'some-session');
    const e2 = ent('e2', null);
    const e3 = ent('e3', undefined);

    const count = visibleCount([e1, e2, e3], {
      currentSessionId: null,
      currentHostname: 'a.com',
      domainOf: () => null,
    });

    expect(count).toBe(3);
  });
});
