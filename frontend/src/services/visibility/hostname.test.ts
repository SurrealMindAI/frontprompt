/**
 * hostname.ts unit tests — hostnameOf + per-kind domain helpers.
 *
 * Test-Surface:
 *   - hostnameOf: parses well-formed URLs; lowercases host; returns null for
 *     non-HTTP URLs, empty string, and invalid input.
 *   - pickDomain: delegates to hostnameOf(pick.url).
 *   - regionDomain: derives hostname from first resolvable member pick's url;
 *     returns null when members list is empty/absent or member ids are missing
 *     from picksById.
 *   - relationDomain: hostname of source endpoint — pick source → pickDomain;
 *     region source → regionDomain. Returns null for unresolvable source.
 */
import { describe, expect, test } from 'vitest';
import { hostnameOf, pickDomain, regionDomain, relationDomain } from './hostname';
import type { Pick, Region, Relation } from '../../_generated/state';

// ---------------------------------------------------------------------------
// Helpers
// ---------------------------------------------------------------------------

function makePick(pickId: string, url: string): Pick {
  return {
    pick_id: pickId,
    url,
    timestamp_ms: 0,
    element: {
      selector: 'div',
      fingerprint: { tag: 'div' },
      text_snippet: '',
      rect: { x: 0, y: 0, width: 0, height: 0 },
    },
    comment: '',
    color_index: 0,
  };
}

function makeRegion(regionId: string, memberPickIds?: string[]): Region {
  return {
    region_id: regionId,
    rect: { x: 0, y: 0, width: 100, height: 100 },
    member_pick_ids: memberPickIds,
    timestamp_ms: 0,
    color_index: 0,
  };
}

function makeRelation(
  relationId: string,
  sourceId: string,
  sourceKind: 'pick' | 'region',
  targetId: string,
  targetKind: 'pick' | 'region'
): Relation {
  return {
    relation_id: relationId,
    source_id: sourceId,
    source_kind: sourceKind,
    target_id: targetId,
    target_kind: targetKind,
    kind: 'relates_to',
    timestamp_ms: 0,
  };
}

// ---------------------------------------------------------------------------
// hostnameOf
// ---------------------------------------------------------------------------

describe('hostnameOf', () => {
  test('extracts hostname from https URL with path and query', () => {
    expect(hostnameOf('https://www.google.com/path?q=1')).toBe('www.google.com');
  });

  test('strips port from http URL', () => {
    expect(hostnameOf('http://example.com:8080/x')).toBe('example.com');
  });

  test('lowercases uppercase host', () => {
    expect(hostnameOf('https://EXAMPLE.COM/page')).toBe('example.com');
  });

  test('returns null for data: URL', () => {
    expect(hostnameOf('data:text/html,<h1>hello</h1>')).toBeNull();
  });

  test('returns null for empty string', () => {
    expect(hostnameOf('')).toBeNull();
  });

  test('returns null for non-URL string', () => {
    expect(hostnameOf('not a url')).toBeNull();
  });

  test('returns null for null input', () => {
    expect(hostnameOf(null)).toBeNull();
  });

  test('returns null for undefined input', () => {
    expect(hostnameOf(undefined)).toBeNull();
  });
});

// ---------------------------------------------------------------------------
// pickDomain
// ---------------------------------------------------------------------------

describe('pickDomain', () => {
  test('returns hostname of pick.url', () => {
    const pick = makePick('p1', 'https://example.com/page');
    expect(pickDomain(pick)).toBe('example.com');
  });

  test('returns null when pick.url is not a valid URL', () => {
    const pick = makePick('p1', 'not-a-url');
    expect(pickDomain(pick)).toBeNull();
  });
});

// ---------------------------------------------------------------------------
// regionDomain
// ---------------------------------------------------------------------------

describe('regionDomain', () => {
  test('returns hostname of first member pick url', () => {
    const pick = makePick('p1', 'https://example.com/');
    const picksById = new Map([['p1', pick]]);
    const region = makeRegion('r1', ['p1']);
    expect(regionDomain(region, picksById)).toBe('example.com');
  });

  test('skips first member if unresolvable and uses second', () => {
    const pick = makePick('p2', 'https://other.com/');
    const picksById = new Map([['p2', pick]]);
    const region = makeRegion('r1', ['missing-id', 'p2']);
    expect(regionDomain(region, picksById)).toBe('other.com');
  });

  test('returns null when member_pick_ids is empty array', () => {
    const picksById = new Map<string, Pick>();
    const region = makeRegion('r1', []);
    expect(regionDomain(region, picksById)).toBeNull();
  });

  test('returns null when member_pick_ids is absent', () => {
    const picksById = new Map<string, Pick>();
    const region = makeRegion('r1', undefined);
    expect(regionDomain(region, picksById)).toBeNull();
  });

  test('returns null when all member ids are unresolvable', () => {
    const picksById = new Map<string, Pick>();
    const region = makeRegion('r1', ['x1', 'x2']);
    expect(regionDomain(region, picksById)).toBeNull();
  });
});

// ---------------------------------------------------------------------------
// relationDomain — source is pick
// ---------------------------------------------------------------------------

describe('relationDomain (source = pick)', () => {
  test('returns hostname of source pick url', () => {
    const pick = makePick('p1', 'https://example.com/');
    const picksById = new Map([['p1', pick]]);
    const regionsById = new Map<string, Region>();
    const rel = makeRelation('rel1', 'p1', 'pick', 'p2', 'pick');
    expect(relationDomain(rel, picksById, regionsById)).toBe('example.com');
  });

  test('returns null when source pick id is not in picksById', () => {
    const picksById = new Map<string, Pick>();
    const regionsById = new Map<string, Region>();
    const rel = makeRelation('rel1', 'missing', 'pick', 'p2', 'pick');
    expect(relationDomain(rel, picksById, regionsById)).toBeNull();
  });
});

// ---------------------------------------------------------------------------
// relationDomain — source is region
// ---------------------------------------------------------------------------

describe('relationDomain (source = region)', () => {
  test('returns domain derived from source region → first member pick', () => {
    const pick = makePick('p1', 'https://example.com/');
    const picksById = new Map([['p1', pick]]);
    const region = makeRegion('r1', ['p1']);
    const regionsById = new Map([['r1', region]]);
    const rel = makeRelation('rel1', 'r1', 'region', 'p2', 'pick');
    expect(relationDomain(rel, picksById, regionsById)).toBe('example.com');
  });

  test('returns null when source region id is not in regionsById', () => {
    const picksById = new Map<string, Pick>();
    const regionsById = new Map<string, Region>();
    const rel = makeRelation('rel1', 'missing-region', 'region', 'p2', 'pick');
    expect(relationDomain(rel, picksById, regionsById)).toBeNull();
  });

  test('returns null when source region has no resolvable member picks', () => {
    const picksById = new Map<string, Pick>();
    const region = makeRegion('r1', ['nonexistent']);
    const regionsById = new Map([['r1', region]]);
    const rel = makeRelation('rel1', 'r1', 'region', 'p2', 'pick');
    expect(relationDomain(rel, picksById, regionsById)).toBeNull();
  });

  test('returns null when source region has no members', () => {
    const picksById = new Map<string, Pick>();
    const region = makeRegion('r1', undefined);
    const regionsById = new Map([['r1', region]]);
    const rel = makeRelation('rel1', 'r1', 'region', 'p2', 'pick');
    expect(relationDomain(rel, picksById, regionsById)).toBeNull();
  });
});
