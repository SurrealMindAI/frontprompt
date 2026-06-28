/**
 * visible-groups.ts unit tests — visibleGroups domain-scoped owner-aware projection.
 *
 * Test-Surface:
 *   - own across multiple domains: owned entities grouped by domain, each isOwned:true
 *   - foreign only current hostname: foreign on current domain included; foreign on other domain absent
 *   - greyed flag: isOwned reflects ownership correctly
 *   - own no-domain fallback: own entity with null domain → "(unknown)" group; foreign null domain → absent
 *   - ordering: current hostname first, rest alphabetical, "(unknown)" last
 *   - null degrade: currentSessionId === null → single "(all)" group, all isOwned:true
 */
import { describe, expect, test } from 'vitest';
import { visibleGroups } from './visible-groups';

// ---------------------------------------------------------------------------
// Minimal entity type for testing (matches constraint { origin_session?: string | null })
// ---------------------------------------------------------------------------

interface TestEntity {
  id: string;
  origin_session?: string | null;
}

function ent(id: string, sessionId: string | null | undefined): TestEntity {
  return { id, origin_session: sessionId };
}

// ---------------------------------------------------------------------------
// own across multiple domains
// ---------------------------------------------------------------------------

describe('own across multiple domains', () => {
  test('entities owned by currentSessionId grouped by their domain, all isOwned:true', () => {
    const session = 'sess-1';
    const e1 = ent('e1', session); // domain a.com
    const e2 = ent('e2', session); // domain b.com
    const e3 = ent('e3', session); // domain a.com (second item on a.com)

    const groups = visibleGroups([e1, e2, e3], {
      currentSessionId: session,
      currentHostname: 'a.com',
      domainOf: (e) => {
        if (e.id === 'e1' || e.id === 'e3') return 'a.com';
        if (e.id === 'e2') return 'b.com';
        return null;
      },
    });

    expect(groups).toHaveLength(2);

    const groupA = groups.find((g) => g.hostname === 'a.com');
    const groupB = groups.find((g) => g.hostname === 'b.com');

    expect(groupA).toBeDefined();
    expect(groupB).toBeDefined();

    // a.com group contains e1 and e3
    expect(groupA!.items.map((i) => i.entity.id)).toEqual(['e1', 'e3']);
    expect(groupA!.items.every((i) => i.isOwned)).toBe(true);

    // b.com group contains e2
    expect(groupB!.items.map((i) => i.entity.id)).toEqual(['e2']);
    expect(groupB!.items.every((i) => i.isOwned)).toBe(true);
  });
});

// ---------------------------------------------------------------------------
// foreign only current hostname
// ---------------------------------------------------------------------------

describe('foreign only current hostname', () => {
  test('foreign entity with domain === currentHostname is included as isOwned:false', () => {
    const session = 'sess-1';
    const foreign = ent('f1', 'other-session');

    const groups = visibleGroups([foreign], {
      currentSessionId: session,
      currentHostname: 'a.com',
      domainOf: () => 'a.com',
    });

    expect(groups).toHaveLength(1);
    const group = groups[0];
    if (!group) throw new Error('missing groups[0] in test result');
    expect(group.hostname).toBe('a.com');
    expect(group.items).toHaveLength(1);
    const item = group.items[0];
    if (!item) throw new Error('missing items[0] in test result');
    expect(item.isOwned).toBe(false);
    expect(item.entity).toBe(foreign);
  });

  test('foreign entity with domain !== currentHostname is absent', () => {
    const session = 'sess-1';
    const foreign = ent('f2', 'other-session');

    const groups = visibleGroups([foreign], {
      currentSessionId: session,
      currentHostname: 'a.com',
      domainOf: () => 'b.com',
    });

    expect(groups).toHaveLength(0);
  });
});

// ---------------------------------------------------------------------------
// greyed flag (isOwned)
// ---------------------------------------------------------------------------

describe('greyed flag', () => {
  test('own entities have isOwned:true, foreign entities have isOwned:false', () => {
    const session = 'sess-1';
    const own = ent('own', session);
    const foreign = ent('foreign', 'other-session');

    const groups = visibleGroups([own, foreign], {
      currentSessionId: session,
      currentHostname: 'a.com',
      domainOf: () => 'a.com',
    });

    expect(groups).toHaveLength(1);
    const aGroup = groups[0];
    if (!aGroup) throw new Error('missing groups[0] in test result');
    const ownItem = aGroup.items.find((i) => i.entity.id === 'own');
    const foreignItem = aGroup.items.find((i) => i.entity.id === 'foreign');

    expect(ownItem).toBeDefined();
    expect(foreignItem).toBeDefined();
    if (!ownItem || !foreignItem) return;
    expect(ownItem.isOwned).toBe(true);
    expect(foreignItem.isOwned).toBe(false);
  });
});

// ---------------------------------------------------------------------------
// own no-domain fallback
// ---------------------------------------------------------------------------

describe('own no-domain fallback', () => {
  test('own entity with null domain goes into "(unknown)" group', () => {
    const session = 'sess-1';
    const own = ent('own-null', session);

    const groups = visibleGroups([own], {
      currentSessionId: session,
      currentHostname: 'a.com',
      domainOf: () => null,
    });

    expect(groups).toHaveLength(1);
    const unknownGroup = groups[0];
    if (!unknownGroup) throw new Error('missing groups[0] in test result');
    expect(unknownGroup.hostname).toBe('(unknown)');
    expect(unknownGroup.items).toHaveLength(1);
    const unknownItem = unknownGroup.items[0];
    if (!unknownItem) throw new Error('missing items[0] in test result');
    expect(unknownItem.isOwned).toBe(true);
  });

  test('foreign entity with null domain is absent', () => {
    const session = 'sess-1';
    const foreign = ent('foreign-null', 'other-session');

    const groups = visibleGroups([foreign], {
      currentSessionId: session,
      currentHostname: 'a.com',
      domainOf: () => null,
    });

    expect(groups).toHaveLength(0);
  });
});

// ---------------------------------------------------------------------------
// ordering
// ---------------------------------------------------------------------------

describe('ordering', () => {
  test('current hostname first, remaining own-domain groups alphabetical, "(unknown)" last', () => {
    const session = 'sess-1';
    // Entities on different domains — all owned so all groups appear
    const eC = ent('eC', session); // currentHostname c.com
    const eA = ent('eA', session); // a.com
    const eZ = ent('eZ', session); // z.com
    const eB = ent('eB', session); // b.com
    const eNull = ent('eNull', session); // no domain → (unknown)

    const groups = visibleGroups([eC, eA, eZ, eB, eNull], {
      currentSessionId: session,
      currentHostname: 'c.com',
      domainOf: (e) => {
        if (e.id === 'eC') return 'c.com';
        if (e.id === 'eA') return 'a.com';
        if (e.id === 'eZ') return 'z.com';
        if (e.id === 'eB') return 'b.com';
        return null; // eNull
      },
    });

    expect(groups).toHaveLength(5);
    const [g0, g1, g2, g3, g4] = groups;
    if (!g0 || !g1 || !g2 || !g3 || !g4) throw new Error('expected 5 groups in test result');
    expect(g0.hostname).toBe('c.com'); // current first
    expect(g1.hostname).toBe('a.com'); // alphabetical
    expect(g2.hostname).toBe('b.com');
    expect(g3.hostname).toBe('z.com');
    expect(g4.hostname).toBe('(unknown)'); // unknown last
  });
});

// ---------------------------------------------------------------------------
// sort comparator edge cases — ensure all branches in the sort fn are taken
// ---------------------------------------------------------------------------

describe('sort comparator edge cases', () => {
  test('localeCompare branch: two non-current non-unknown own domains are sorted alphabetically', () => {
    // 'b.com' and 'a.com' are both non-currentHostname ('z.com') and non-UNKNOWN.
    // The sort comparator MUST compare them via localeCompare → covers line 115.
    const session = 'sort-sess';
    const e1 = ent('e1', session); // b.com
    const e2 = ent('e2', session); // a.com

    const groups = visibleGroups([e1, e2], {
      currentSessionId: session,
      currentHostname: 'z.com', // different from both → neither key is 'z.com'
      domainOf: (e) => (e.id === 'e1' ? 'b.com' : 'a.com'),
    });

    expect(groups).toHaveLength(2);
    // localeCompare: 'a.com' < 'b.com' → a.com first
    expect(groups[0]?.hostname).toBe('a.com');
    expect(groups[1]?.hostname).toBe('b.com');
  });

  test('b===UNKNOWN branch: exactly [non-current, UNKNOWN] forces sort to compare them directly', () => {
    // Only 2 groups: 'a.com' and '(unknown)'. The sort MUST call comparator for these.
    // Comparator path for (a='a.com', b='(unknown)'):
    //   a !== currentHostname, b !== currentHostname, a !== UNKNOWN → if(b===UNKNOWN) TRUE → line 114
    const session = 'sort-sess-2';
    const e1 = ent('e1', session); // a.com (owned)
    const e2 = ent('e2', session); // null domain → (unknown)

    const groups = visibleGroups([e1, e2], {
      currentSessionId: session,
      currentHostname: 'different.com', // no entities on this domain
      domainOf: (e) => (e.id === 'e1' ? 'a.com' : null),
    });

    expect(groups).toHaveLength(2);
    expect(groups[0]?.hostname).toBe('a.com'); // non-unknown before unknown
    expect(groups[1]?.hostname).toBe('(unknown)');
  });

  test('a===currentHostname branch: currentHostname entity processed SECOND — covers line 111', () => {
    // V8 binary insertion sort calls comparefn(pivot, sorted_elem).
    // To get a===currentHostname, currentHostname must be the PIVOT (inserted second).
    // keys insertion order: ['other.com', 'current.com'] → when inserting 'current.com':
    //   comparefn('current.com', 'other.com') → a='current.com'=currentHostname → line 111 TRUE
    const session = 'sort-sess-111';
    const eOther = ent('eOther', session); // processed first → 'other.com' first in keys
    const eCurrent = ent('eCurrent', session); // processed second → 'current.com' second (pivot)

    const groups = visibleGroups([eOther, eCurrent], {
      currentSessionId: session,
      currentHostname: 'current.com',
      domainOf: (e) => (e.id === 'eOther' ? 'other.com' : 'current.com'),
    });

    expect(groups).toHaveLength(2);
    expect(groups[0]?.hostname).toBe('current.com'); // currentHostname sorts first
    expect(groups[1]?.hostname).toBe('other.com');
  });

  test('b===UNKNOWN branch: UNKNOWN entity processed FIRST, regular domain second — covers line 114', () => {
    // V8 binary insertion sort calls comparefn(pivot, sorted_elem).
    // To get b===UNKNOWN, UNKNOWN must be the SORTED ELEMENT (inserted first).
    // keys insertion order: ['(unknown)', 'regular.com'] → when inserting 'regular.com':
    //   comparefn('regular.com', '(unknown)') → b='(unknown)'=UNKNOWN → line 114 TRUE
    const session = 'sort-sess-114';
    const eUnknown = ent('eUnknown', session); // null domain → '(unknown)' first in keys
    const eRegular = ent('eRegular', session); // 'regular.com' second (pivot)

    const groups = visibleGroups([eUnknown, eRegular], {
      currentSessionId: session,
      currentHostname: 'different.com', // not involved
      domainOf: (e) => (e.id === 'eRegular' ? 'regular.com' : null),
    });

    expect(groups).toHaveLength(2);
    expect(groups[0]?.hostname).toBe('regular.com'); // regular before unknown
    expect(groups[1]?.hostname).toBe('(unknown)');
  });
});

// ---------------------------------------------------------------------------
// null degrade
// ---------------------------------------------------------------------------

describe('null degrade (currentSessionId === null)', () => {
  test('returns a single "(all)" group with every entity as isOwned:true', () => {
    const e1 = ent('e1', 'some-session');
    const e2 = ent('e2', null);
    const e3 = ent('e3', undefined);

    const groups = visibleGroups([e1, e2, e3], {
      currentSessionId: null,
      currentHostname: 'a.com',
      domainOf: () => null,
    });

    expect(groups).toHaveLength(1);
    const allGroup = groups[0];
    if (!allGroup) throw new Error('missing groups[0] in test result');
    expect(allGroup.hostname).toBe('(all)');
    expect(allGroup.items).toHaveLength(3);
    expect(allGroup.items.every((i) => i.isOwned)).toBe(true);
    expect(allGroup.items.map((i) => i.entity.id)).toEqual(['e1', 'e2', 'e3']);
  });
});
