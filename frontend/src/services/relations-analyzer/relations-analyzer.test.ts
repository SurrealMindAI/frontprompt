/**
 * RelationsAnalyzer — DOM-relation discovery tests.
 *
 * Uses jsdom DOM to create real parent-child element trees and verifies that
 * analyzeDomRelations correctly identifies:
 *   - parent.contains(child) → part_of relation (child → parent)
 *   - siblings within threshold → relates_to relation
 *   - deduplication against existing relations
 *   - deduplication within a single run (symmetric relates_to)
 *
 * Appended directly to a real document body so Element.contains() and
 * parentElement traversal work correctly.
 */
import { describe, expect, test, beforeEach, afterEach } from 'vitest';
import { analyzeDomRelations, type PickElementRef } from './relations-analyzer';
import type { Relation } from '../../_generated/state';

// Helper: create a standalone div element
function mkEl(tag = 'div'): HTMLElement {
  return document.createElement(tag);
}

// Helper: build a PickElementRef
function mkRef(pickId: string, element: Element): PickElementRef {
  return { pickId, element };
}

// Container appended to body so containment/parent traversal works
let container: HTMLDivElement;

beforeEach(() => {
  container = document.createElement('div');
  document.body.appendChild(container);
});

afterEach(() => {
  document.body.removeChild(container);
});

// ---------------------------------------------------------------------------
// empty input
// ---------------------------------------------------------------------------

describe('analyzeDomRelations — empty input', () => {
  test('returns empty array for empty picks list', () => {
    expect(analyzeDomRelations([])).toHaveLength(0);
  });

  test('returns empty array for single pick (no pairs)', () => {
    const el = mkEl();
    container.appendChild(el);
    expect(analyzeDomRelations([mkRef('p1', el)])).toHaveLength(0);
  });
});

// ---------------------------------------------------------------------------
// containment → part_of
// ---------------------------------------------------------------------------

describe('analyzeDomRelations — containment (part_of)', () => {
  test('child-of-a → part_of with source=child, target=parent', () => {
    const parent = mkEl();
    const child = mkEl();
    parent.appendChild(child);
    container.appendChild(parent);

    const relations = analyzeDomRelations([mkRef('parent', parent), mkRef('child', child)]);
    expect(relations).toHaveLength(1);
    expect(relations[0]!.kind).toBe('part_of');
    // child is part_of parent: source=child, target=parent
    expect(relations[0]!.source_id).toBe('child');
    expect(relations[0]!.target_id).toBe('parent');
  });

  test('grand-child → part_of with source=grandchild, target=grandparent', () => {
    const gp = mkEl();
    const p = mkEl();
    const gc = mkEl();
    gp.appendChild(p);
    p.appendChild(gc);
    container.appendChild(gp);

    const relations = analyzeDomRelations([mkRef('gp', gp), mkRef('gc', gc)]);
    expect(relations).toHaveLength(1);
    expect(relations[0]!.kind).toBe('part_of');
    expect(relations[0]!.source_id).toBe('gc');
    expect(relations[0]!.target_id).toBe('gp');
  });

  test('b contains a → part_of with source=a, target=b', () => {
    const outer = mkEl();
    const inner = mkEl();
    outer.appendChild(inner);
    container.appendChild(outer);

    const relations = analyzeDomRelations([mkRef('inner', inner), mkRef('outer', outer)]);
    expect(relations).toHaveLength(1);
    expect(relations[0]!.source_id).toBe('inner');
    expect(relations[0]!.target_id).toBe('outer');
  });
});

// ---------------------------------------------------------------------------
// siblings → relates_to
// ---------------------------------------------------------------------------

describe('analyzeDomRelations — lateral relations (relates_to)', () => {
  test('direct siblings (distance 2) → relates_to', () => {
    const parent = mkEl();
    const a = mkEl();
    const b = mkEl();
    parent.appendChild(a);
    parent.appendChild(b);
    container.appendChild(parent);

    const relations = analyzeDomRelations([mkRef('a', a), mkRef('b', b)]);
    expect(relations).toHaveLength(1);
    expect(relations[0]!.kind).toBe('relates_to');
  });

  test('uncle-niece (distance 3) → relates_to', () => {
    // gp → uncle, gp → parent → child. distance(uncle, child) = 1+2 = 3
    const gp = mkEl();
    const uncle = mkEl();
    const parent = mkEl();
    const child = mkEl();
    gp.appendChild(uncle);
    gp.appendChild(parent);
    parent.appendChild(child);
    container.appendChild(gp);

    const relations = analyzeDomRelations([mkRef('uncle', uncle), mkRef('child', child)]);
    expect(relations).toHaveLength(1);
    expect(relations[0]!.kind).toBe('relates_to');
  });

  test('cousins (distance 4) → relates_to', () => {
    // gp → p1 → a, gp → p2 → b. distance = 2+2=4
    const gp = mkEl();
    const p1 = mkEl();
    const p2 = mkEl();
    const a = mkEl();
    const b = mkEl();
    gp.appendChild(p1);
    gp.appendChild(p2);
    p1.appendChild(a);
    p2.appendChild(b);
    container.appendChild(gp);

    const relations = analyzeDomRelations([mkRef('a', a), mkRef('b', b)]);
    expect(relations).toHaveLength(1);
    expect(relations[0]!.kind).toBe('relates_to');
  });

  test('distance 5 (2nd-cousins) → NO relation (threshold exceeded)', () => {
    // gp → p1 → c1 → a, gp → p2 → c2 → b. dist = 3+3=6 > 4
    const gp = mkEl();
    const p1 = mkEl(); const c1 = mkEl(); const a = mkEl();
    const p2 = mkEl(); const c2 = mkEl(); const b = mkEl();
    gp.appendChild(p1); p1.appendChild(c1); c1.appendChild(a);
    gp.appendChild(p2); p2.appendChild(c2); c2.appendChild(b);
    container.appendChild(gp);

    const relations = analyzeDomRelations([mkRef('a', a), mkRef('b', b)]);
    expect(relations).toHaveLength(0);
  });
});

// ---------------------------------------------------------------------------
// deduplication against existing relations
// ---------------------------------------------------------------------------

describe('analyzeDomRelations — deduplication', () => {
  test('skips part_of when existing relation has same source+target+kind', () => {
    const parent = mkEl();
    const child = mkEl();
    parent.appendChild(child);
    container.appendChild(parent);

    const existing: Relation[] = [{
      relation_id: 'existing-1',
      source_id: 'child',
      source_kind: 'pick',
      target_id: 'parent',
      target_kind: 'pick',
      kind: 'part_of',
      note: null,
      timestamp_ms: 0,
    }] as unknown as Relation[];

    const relations = analyzeDomRelations(
      [mkRef('parent', parent), mkRef('child', child)],
      existing
    );
    expect(relations).toHaveLength(0);
  });

  test('skips relates_to when existing has same pair (either direction)', () => {
    const parent = mkEl();
    const a = mkEl();
    const b = mkEl();
    parent.appendChild(a);
    parent.appendChild(b);
    container.appendChild(parent);

    const existing: Relation[] = [{
      relation_id: 'existing-2',
      source_id: 'b', // reverse direction
      source_kind: 'pick',
      target_id: 'a',
      target_kind: 'pick',
      kind: 'relates_to',
      note: null,
      timestamp_ms: 0,
    }] as unknown as Relation[];

    const relations = analyzeDomRelations([mkRef('a', a), mkRef('b', b)], existing);
    expect(relations).toHaveLength(0);
  });

  test('does not emit duplicate relates_to within a single run', () => {
    // 3 siblings: a-b, a-c, b-c. Each pair produces exactly one relates_to.
    const parent = mkEl();
    const a = mkEl(); const b = mkEl(); const c = mkEl();
    parent.appendChild(a); parent.appendChild(b); parent.appendChild(c);
    container.appendChild(parent);

    const relations = analyzeDomRelations([mkRef('a', a), mkRef('b', b), mkRef('c', c)]);
    // 3 pairs → 3 relates_to (none duplicated)
    expect(relations).toHaveLength(3);
    expect(relations.every((r) => r.kind === 'relates_to')).toBe(true);
  });
});

// ---------------------------------------------------------------------------
// same element (skipped)
// ---------------------------------------------------------------------------

describe('analyzeDomRelations — same element', () => {
  test('skips pair when both picks point to the same element', () => {
    const el = mkEl();
    container.appendChild(el);
    // Two picks referencing the exact same DOM element
    const relations = analyzeDomRelations([mkRef('p1', el), mkRef('p2', el)]);
    expect(relations).toHaveLength(0);
  });
});

// ---------------------------------------------------------------------------
// generated relation shape
// ---------------------------------------------------------------------------

describe('analyzeDomRelations — output shape', () => {
  test('generated relation has required fields', () => {
    const parent = mkEl();
    const a = mkEl();
    const b = mkEl();
    parent.appendChild(a);
    parent.appendChild(b);
    container.appendChild(parent);

    const [rel] = analyzeDomRelations([mkRef('a', a), mkRef('b', b)]);
    expect(typeof rel!.relation_id).toBe('string');
    expect(rel!.source_kind).toBe('pick');
    expect(rel!.target_kind).toBe('pick');
    expect(rel!.note).toBeNull();
    expect(typeof rel!.timestamp_ms).toBe('number');
  });
});
