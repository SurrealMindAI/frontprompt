/**
 * PathPlanner — pure function tests.
 *
 * Tests cover:
 * - bezierWithMidpoint: normal case (returns Q-path + midpoint), degenerate case (same point)
 * - quadraticBezier: backward-compat alias
 * - planPaths: happy-path, skip null endpoints, DIRECTED_KINDS, note/origin passthrough
 *
 * PositionService is a mock returning pre-configured centers.
 */
import { describe, expect, test } from 'vitest';
import { bezierWithMidpoint, quadraticBezier, planPaths, type DrawCommand } from './path-planner';
import type { Pick, Region, Relation } from '../../_generated/state';
import type { PositionService } from './position-service.svelte';

// ---------------------------------------------------------------------------
// bezierWithMidpoint
// ---------------------------------------------------------------------------

describe('bezierWithMidpoint — normal case', () => {
  test('returns quadratic-bezier pathD string (M … Q … x y form)', () => {
    const src = { cx: 0, cy: 0 };
    const tgt = { cx: 100, cy: 0 };
    const { pathD } = bezierWithMidpoint(src, tgt);
    // Must start with M and contain Q (quadratic bezier)
    expect(pathD).toMatch(/^M 0 0 Q /);
    expect(pathD).toMatch(/Q .+ 100 0$/);
  });

  test('midpoint lies at t=0.5 on the curve (formula check)', () => {
    // Horizontal line from (0,0) to (100,0): sag is vertical
    const src = { cx: 0, cy: 0 };
    const tgt = { cx: 100, cy: 0 };
    const { midpoint } = bezierWithMidpoint(src, tgt);
    // cx should be 50 (symmetric; sag is vertical so no horizontal displacement)
    expect(midpoint.cx).toBeCloseTo(50, 1);
    // cy should be non-zero (sag offset applied)
    expect(midpoint.cy).not.toBeCloseTo(0, 1);
  });

  test('SAG_FACTOR 0.15 — control-point is offset perpendicularly', () => {
    // Horizontal line: src=(0,0), tgt=(100,0), dist=100, sag=15
    // nx=-dy/dist=0, ny=dx/dist=1 → ctrlX=50, ctrlY=0+1*15=15
    const src = { cx: 0, cy: 0 };
    const tgt = { cx: 100, cy: 0 };
    const { pathD } = bezierWithMidpoint(src, tgt);
    const match = pathD.match(/Q ([\d.-]+) ([\d.-]+)/);
    expect(match).not.toBeNull();
    const ctrlY = Number(match![2]);
    expect(Math.abs(ctrlY)).toBeCloseTo(15, 1);
  });

  test('diagonal path produces non-trivial midpoint', () => {
    const { midpoint } = bezierWithMidpoint({ cx: 0, cy: 0 }, { cx: 100, cy: 100 });
    // Midpoint should not be exactly at (50, 50) due to the sag
    expect(midpoint.cx).not.toBeCloseTo(50, 5); // sag displaces it
  });
});

describe('bezierWithMidpoint — degenerate case (src == tgt)', () => {
  test('returns straight line L-command', () => {
    const src = { cx: 50, cy: 75 };
    const { pathD } = bezierWithMidpoint(src, src);
    expect(pathD).toMatch(/^M 50 75 L 50 75$/);
  });

  test('midpoint equals src when degenerate', () => {
    const src = { cx: 30, cy: 40 };
    const { midpoint } = bezierWithMidpoint(src, src);
    expect(midpoint.cx).toBe(30);
    expect(midpoint.cy).toBe(40);
  });
});

// ---------------------------------------------------------------------------
// quadraticBezier (backward-compat alias)
// ---------------------------------------------------------------------------

describe('quadraticBezier', () => {
  test('returns same pathD as bezierWithMidpoint', () => {
    const src = { cx: 10, cy: 20 };
    const tgt = { cx: 80, cy: 60 };
    expect(quadraticBezier(src, tgt)).toBe(bezierWithMidpoint(src, tgt).pathD);
  });
});

// ---------------------------------------------------------------------------
// planPaths
// ---------------------------------------------------------------------------

function makeRelation(overrides: Partial<Relation> = {}): Relation {
  return {
    relation_id: 'rel-1',
    source_id: 'pick-a',
    source_kind: 'pick',
    target_id: 'pick-b',
    target_kind: 'pick',
    kind: 'relates_to',
    note: null,
    origin_session: null,
    timestamp_ms: 0,
    ...overrides,
  } as unknown as Relation;
}

const STATIC_CENTERS: Record<string, { cx: number; cy: number }> = {
  'pick-a': { cx: 0, cy: 0 },
  'pick-b': { cx: 100, cy: 100 },
  'region-r1': { cx: 50, cy: 50 },
};

const mockPositions: PositionService = {
  centerForNode(id: string, _kind: string, _picks: readonly Pick[], _regions: readonly Region[]) {
    return STATIC_CENTERS[id] ?? null;
  },
} as unknown as PositionService;

describe('planPaths — happy path', () => {
  test('returns one DrawCommand for a valid relation', () => {
    const rels = [makeRelation()];
    const out = planPaths(rels, [], [], mockPositions);
    expect(out).toHaveLength(1);
  });

  test('DrawCommand carries correct relationId and source/target', () => {
    const rels = [makeRelation({ relation_id: 'my-rel' })];
    const [cmd] = planPaths(rels, [], [], mockPositions);
    expect(cmd!.relationId).toBe('my-rel');
    expect(cmd!.source).toEqual({ cx: 0, cy: 0 });
    expect(cmd!.target).toEqual({ cx: 100, cy: 100 });
  });

  test('DrawCommand.pathD is a non-empty string', () => {
    const [cmd] = planPaths([makeRelation()], [], [], mockPositions);
    expect(typeof cmd!.pathD).toBe('string');
    expect(cmd!.pathD.length).toBeGreaterThan(0);
  });

  test('DrawCommand.midpoint is populated', () => {
    const [cmd] = planPaths([makeRelation()], [], [], mockPositions);
    expect(cmd!.midpoint).toHaveProperty('cx');
    expect(cmd!.midpoint).toHaveProperty('cy');
  });

  test('note is passed through when set', () => {
    const [cmd] = planPaths([makeRelation({ note: 'my note' })], [], [], mockPositions);
    expect(cmd!.note).toBe('my note');
  });

  test('note is null when absent', () => {
    const [cmd] = planPaths([makeRelation({ note: null })], [], [], mockPositions);
    expect(cmd!.note).toBeNull();
  });

  test('origin_session is passed through', () => {
    const [cmd] = planPaths([makeRelation({ origin_session: 'sess-xyz' })], [], [], mockPositions);
    expect(cmd!.origin_session).toBe('sess-xyz');
  });
});

describe('planPaths — DIRECTED_KINDS', () => {
  test('"triggers" kind → isDirected=true', () => {
    const [cmd] = planPaths([makeRelation({ kind: 'triggers' })], [], [], mockPositions);
    expect(cmd!.isDirected).toBe(true);
  });

  test('"part_of" kind → isDirected=true', () => {
    const [cmd] = planPaths([makeRelation({ kind: 'part_of' })], [], [], mockPositions);
    expect(cmd!.isDirected).toBe(true);
  });

  test('"relates_to" kind → isDirected=false', () => {
    const [cmd] = planPaths([makeRelation({ kind: 'relates_to' })], [], [], mockPositions);
    expect(cmd!.isDirected).toBe(false);
  });
});

describe('planPaths — missing endpoints skipped', () => {
  test('skips relation when source not found', () => {
    const rel = makeRelation({ source_id: 'unknown-node' });
    const out = planPaths([rel], [], [], mockPositions);
    expect(out).toHaveLength(0);
  });

  test('skips relation when target not found', () => {
    const rel = makeRelation({ target_id: 'unknown-node' });
    const out = planPaths([rel], [], [], mockPositions);
    expect(out).toHaveLength(0);
  });

  test('still includes valid relations when some are skipped', () => {
    const valid = makeRelation({ relation_id: 'rel-good' });
    const bad = makeRelation({ relation_id: 'rel-bad', source_id: 'ghost-node' });
    const out = planPaths([bad, valid], [], [], mockPositions);
    expect(out).toHaveLength(1);
    expect(out[0]!.relationId).toBe('rel-good');
  });

  test('empty relations → empty output', () => {
    expect(planPaths([], [], [], mockPositions)).toHaveLength(0);
  });
});

describe('planPaths — multiple relations', () => {
  test('processes multiple relations', () => {
    const rels = [
      makeRelation({ relation_id: 'rel-1', source_id: 'pick-a', target_id: 'pick-b' }),
      makeRelation({ relation_id: 'rel-2', source_id: 'pick-b', target_id: 'region-r1', target_kind: 'region' }),
    ];
    const out = planPaths(rels, [], [], mockPositions);
    expect(out).toHaveLength(2);
    expect(out.map((c: DrawCommand) => c.relationId)).toEqual(['rel-1', 'rel-2']);
  });
});
