/**
 * LookupService — stateless pure-function tests.
 *
 * Covers: relationsFor (outgoing, incoming, empty),
 * pickById, regionById, countFor.
 */
import { describe, expect, test } from 'vitest';
import { lookupService } from './lookup-service.svelte';
import type { Pick, Region, Relation } from '../../_generated/state';

function makePick(id: string): Pick {
  return { pick_id: id } as unknown as Pick;
}

function makeRegion(id: string): Region {
  return { region_id: id } as unknown as Region;
}

function makeRelation(
  sourceId: string,
  targetId: string,
  sourceKind: 'pick' | 'region' = 'pick',
  targetKind: 'pick' | 'region' = 'pick',
  id = 'rel-' + Math.random()
): Relation {
  return {
    relation_id: id,
    source_id: sourceId,
    source_kind: sourceKind,
    target_id: targetId,
    target_kind: targetKind,
    kind: 'relates_to',
    note: null,
    timestamp_ms: 0,
  } as unknown as Relation;
}

// ---------------------------------------------------------------------------
// relationsFor
// ---------------------------------------------------------------------------

describe('lookupService.relationsFor', () => {
  test('returns empty arrays when no relations', () => {
    const result = lookupService.relationsFor('pick-a', 'pick', []);
    expect(result.outgoing).toHaveLength(0);
    expect(result.incoming).toHaveLength(0);
  });

  test('returns outgoing relations for source node', () => {
    const rel = makeRelation('pick-a', 'pick-b');
    const result = lookupService.relationsFor('pick-a', 'pick', [rel]);
    expect(result.outgoing).toHaveLength(1);
    expect(result.outgoing[0]!.relation_id).toBe(rel.relation_id);
  });

  test('returns incoming relations for target node', () => {
    const rel = makeRelation('pick-b', 'pick-a');
    const result = lookupService.relationsFor('pick-a', 'pick', [rel]);
    expect(result.incoming).toHaveLength(1);
    expect(result.incoming[0]!.relation_id).toBe(rel.relation_id);
  });

  test('does not include relation from different kind', () => {
    // same id, but source_kind=region → not a match for nodeKind=pick
    const rel = makeRelation('pick-a', 'pick-b', 'region', 'pick');
    const result = lookupService.relationsFor('pick-a', 'pick', [rel]);
    expect(result.outgoing).toHaveLength(0);
  });

  test('correctly separates outgoing and incoming when both present', () => {
    const out = makeRelation('node-a', 'node-b', 'pick', 'pick', 'rel-out');
    const inc = makeRelation('node-b', 'node-a', 'pick', 'pick', 'rel-inc');
    const result = lookupService.relationsFor('node-a', 'pick', [out, inc]);
    expect(result.outgoing).toHaveLength(1);
    expect(result.outgoing[0]!.relation_id).toBe('rel-out');
    expect(result.incoming).toHaveLength(1);
    expect(result.incoming[0]!.relation_id).toBe('rel-inc');
  });

  test('region-kind endpoint matching', () => {
    const rel = makeRelation('region-r1', 'pick-b', 'region', 'pick');
    const result = lookupService.relationsFor('region-r1', 'region', [rel]);
    expect(result.outgoing).toHaveLength(1);
  });
});

// ---------------------------------------------------------------------------
// pickById
// ---------------------------------------------------------------------------

describe('lookupService.pickById', () => {
  test('returns the pick when found', () => {
    const picks = [makePick('p-1'), makePick('p-2')];
    const result = lookupService.pickById('p-2', picks);
    expect(result?.pick_id).toBe('p-2');
  });

  test('returns null when not found', () => {
    const result = lookupService.pickById('ghost', [makePick('p-1')]);
    expect(result).toBeNull();
  });

  test('returns null when picks list is empty', () => {
    expect(lookupService.pickById('p-1', [])).toBeNull();
  });
});

// ---------------------------------------------------------------------------
// regionById
// ---------------------------------------------------------------------------

describe('lookupService.regionById', () => {
  test('returns the region when found', () => {
    const regions = [makeRegion('r-1'), makeRegion('r-2')];
    const result = lookupService.regionById('r-2', regions);
    expect(result?.region_id).toBe('r-2');
  });

  test('returns null when not found', () => {
    const result = lookupService.regionById('ghost', [makeRegion('r-1')]);
    expect(result).toBeNull();
  });
});

// ---------------------------------------------------------------------------
// countFor
// ---------------------------------------------------------------------------

describe('lookupService.countFor', () => {
  test('returns 0 when no relations', () => {
    expect(lookupService.countFor('node-a', 'pick', [])).toBe(0);
  });

  test('counts both outgoing and incoming', () => {
    const out = makeRelation('node-a', 'node-b');
    const inc = makeRelation('node-b', 'node-a');
    expect(lookupService.countFor('node-a', 'pick', [out, inc])).toBe(2);
  });

  test('counts only outgoing when only outgoing exists', () => {
    const rel = makeRelation('node-a', 'node-b');
    expect(lookupService.countFor('node-a', 'pick', [rel])).toBe(1);
  });

  test('does not count unrelated relations', () => {
    const rel = makeRelation('other-a', 'other-b');
    expect(lookupService.countFor('node-a', 'pick', [rel])).toBe(0);
  });

  test('handles multiple relations correctly', () => {
    const relations = [
      makeRelation('node-a', 'node-b'),
      makeRelation('node-a', 'node-c'),
      makeRelation('node-c', 'node-a'),
      makeRelation('node-b', 'node-c'), // unrelated
    ];
    expect(lookupService.countFor('node-a', 'pick', relations)).toBe(3);
  });
});
