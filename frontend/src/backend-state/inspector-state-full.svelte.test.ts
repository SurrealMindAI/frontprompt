/**
 * InspectorState — comprehensive tests covering hydrate + all intent methods.
 *
 * The dedup-regression test lives in inspector-state.svelte.test.ts.
 * This file covers hydrate, activate, cancel, selectPick, updateComment,
 * deletePick, submitRelation, deleteRelation, updateRelation,
 * submitRegion, deleteRegion, updateRegion, selectRegion.
 */
const send = vi.hoisted(() => vi.fn());
vi.mock('../bridge/bridge.svelte', () => ({ bridge: { send } }));

import { describe, expect, test, vi, beforeEach } from 'vitest';
import { InspectorState } from './inspector-state.svelte';
import type { Pick, Region, Relation } from '../_generated/state';

function makePick(id: string, selector = `#el-${id}`): Pick {
  return {
    pick_id: id,
    url: 'https://example.com',
    timestamp_ms: 0,
    color_index: 0,
    element: {
      selector,
      fingerprint: { tag: 'div', attributes: {}, text: '', path: [], parent_name: '', parent_attribs: {}, siblings: [] },
      text_snippet: '',
      rect: { x: 0, y: 0, width: 10, height: 10 },
    },
    comment: '',
  } as unknown as Pick;
}

function makeRegion(id: string): Region {
  return {
    region_id: id,
    rect: { x: 0, y: 0, width: 100, height: 100 },
    member_pick_ids: [],
    note: null,
    timestamp_ms: 0,
    color_index: 0,
  } as unknown as Region;
}

function makeRelation(id: string, sourceId = 'p1', targetId = 'p2'): Relation {
  return {
    relation_id: id,
    source_id: sourceId,
    source_kind: 'pick',
    target_id: targetId,
    target_kind: 'pick',
    kind: 'relates_to',
    note: null,
    timestamp_ms: 0,
  } as unknown as Relation;
}

beforeEach(() => send.mockClear());

// ---------------------------------------------------------------------------
// hydrate
// ---------------------------------------------------------------------------

describe('InspectorState.hydrate', () => {
  test('hydrate sets active field', () => {
    const ins = new InspectorState();
    ins.hydrate({ active: true, picks: [], relations: [], regions: [] });
    expect(ins.active).toBe(true);
  });

  test('hydrate sets picks list', () => {
    const ins = new InspectorState();
    const pick = makePick('p1');
    ins.hydrate({ active: false, picks: [pick], relations: [], regions: [] });
    expect(ins.picks).toHaveLength(1);
    expect(ins.picks[0]!.pick_id).toBe('p1');
  });

  test('hydrate sets activePickId', () => {
    const ins = new InspectorState();
    ins.hydrate({ active: false, picks: [makePick('p1')], active_pick_id: 'p1', relations: [], regions: [] });
    expect(ins.activePickId).toBe('p1');
  });

  test('hydrate sets relations', () => {
    const ins = new InspectorState();
    const rel = makeRelation('r1');
    ins.hydrate({ active: false, picks: [], relations: [rel], regions: [] });
    expect(ins.relations).toHaveLength(1);
  });

  test('hydrate sets regions', () => {
    const ins = new InspectorState();
    const reg = makeRegion('reg1');
    ins.hydrate({ active: false, picks: [], relations: [], regions: [reg] });
    expect(ins.regions).toHaveLength(1);
  });

  test('hydrate sets activeRegionId', () => {
    const ins = new InspectorState();
    ins.hydrate({ active: false, picks: [], relations: [], regions: [makeRegion('reg1')], active_region_id: 'reg1' });
    expect(ins.activeRegionId).toBe('reg1');
  });

  test('hydrate with undefined fields is tolerant (forward-compat)', () => {
    const ins = new InspectorState();
    // Should not throw with partial view
    ins.hydrate({} as never);
    expect(ins.active).toBe(false);
    expect(ins.picks).toEqual([]);
  });
});

// ---------------------------------------------------------------------------
// activate / cancel
// ---------------------------------------------------------------------------

describe('InspectorState.activate', () => {
  test('sets active=true and sends inspector_activate_requested', () => {
    const ins = new InspectorState();
    ins.activate();
    expect(ins.active).toBe(true);
    expect(send).toHaveBeenCalledOnce();
    expect(send).toHaveBeenCalledWith(expect.objectContaining({ kind: 'inspector_activate_requested' }));
  });
});

describe('InspectorState.cancel', () => {
  test('sets active=false and sends inspector_canceled_requested', () => {
    const ins = new InspectorState();
    ins.hydrate({ active: true, picks: [], relations: [], regions: [] });
    ins.cancel();
    expect(ins.active).toBe(false);
    expect(send).toHaveBeenCalledWith(expect.objectContaining({ kind: 'inspector_canceled_requested' }));
  });
});

// ---------------------------------------------------------------------------
// selectPick
// ---------------------------------------------------------------------------

describe('InspectorState.selectPick', () => {
  test('sets activePickId and clears activeRegionId, sends pick_selected_requested', () => {
    const ins = new InspectorState();
    ins.hydrate({ active: false, picks: [makePick('p1')], relations: [], regions: [makeRegion('r1')], active_region_id: 'r1' });
    ins.selectPick('p1');
    expect(ins.activePickId).toBe('p1');
    expect(ins.activeRegionId).toBeNull();
    expect(send).toHaveBeenCalledWith(expect.objectContaining({ kind: 'pick_selected_requested', pick_id: 'p1' }));
  });
});

// ---------------------------------------------------------------------------
// updateComment
// ---------------------------------------------------------------------------

describe('InspectorState.updateComment', () => {
  test('updates comment on existing pick and sends pick_comment_updated_requested', () => {
    const ins = new InspectorState();
    ins.hydrate({ active: false, picks: [makePick('p1')], relations: [], regions: [] });
    ins.updateComment('p1', 'my comment');
    expect(ins.picks[0]!.comment).toBe('my comment');
    expect(send).toHaveBeenCalledWith(
      expect.objectContaining({ kind: 'pick_comment_updated_requested', pick_id: 'p1', comment: 'my comment' })
    );
  });

  test('updateComment on unknown pick id still sends wire-message', () => {
    const ins = new InspectorState();
    ins.updateComment('unknown', 'comment');
    expect(send).toHaveBeenCalledWith(expect.objectContaining({ kind: 'pick_comment_updated_requested' }));
  });
});

// ---------------------------------------------------------------------------
// deletePick
// ---------------------------------------------------------------------------

describe('InspectorState.deletePick', () => {
  test('removes pick from list and sends pick_deleted_requested', () => {
    const ins = new InspectorState();
    ins.hydrate({ active: false, picks: [makePick('p1'), makePick('p2')], relations: [], regions: [] });
    ins.deletePick('p1');
    expect(ins.picks).toHaveLength(1);
    expect(ins.picks[0]!.pick_id).toBe('p2');
    expect(send).toHaveBeenCalledWith(expect.objectContaining({ kind: 'pick_deleted_requested', pick_id: 'p1' }));
  });

  test('clears activePickId when the active pick is deleted', () => {
    const ins = new InspectorState();
    ins.hydrate({ active: false, picks: [makePick('p1')], active_pick_id: 'p1', relations: [], regions: [] });
    ins.deletePick('p1');
    expect(ins.activePickId).toBeNull();
  });

  test('cascades relation removal for pick-kind endpoints', () => {
    const ins = new InspectorState();
    const rel1 = makeRelation('r1', 'p1', 'p2'); // p1 is source
    const rel2 = makeRelation('r2', 'p2', 'p1'); // p1 is target
    ins.hydrate({ active: false, picks: [makePick('p1'), makePick('p2')], relations: [rel1, rel2], regions: [] });
    ins.deletePick('p1');
    // Both relations involving p1 should be removed
    expect(ins.relations).toHaveLength(0);
  });

  test('removes pick from region member_pick_ids on delete', () => {
    const ins = new InspectorState();
    const reg = { ...makeRegion('reg1'), member_pick_ids: ['p1', 'p2'] };
    ins.hydrate({ active: false, picks: [makePick('p1'), makePick('p2')], relations: [], regions: [reg] });
    ins.deletePick('p1');
    expect(ins.regions[0]!.member_pick_ids).toEqual(['p2']);
  });
});

// ---------------------------------------------------------------------------
// submitRelation / deleteRelation / updateRelation
// ---------------------------------------------------------------------------

describe('InspectorState.submitRelation', () => {
  test('appends new relation and sends relation_created_requested', () => {
    const ins = new InspectorState();
    const rel = makeRelation('r1');
    ins.submitRelation(rel);
    expect(ins.relations).toHaveLength(1);
    expect(send).toHaveBeenCalledWith(expect.objectContaining({ kind: 'relation_created_requested', relation: rel }));
  });

  test('overwrites existing relation with same id (last-write-wins)', () => {
    const ins = new InspectorState();
    const rel1 = makeRelation('r1', 'p1', 'p2');
    const rel2 = makeRelation('r1', 'p2', 'p3');
    ins.submitRelation(rel1);
    ins.submitRelation(rel2);
    expect(ins.relations).toHaveLength(1);
    expect(ins.relations[0]!.source_id).toBe('p2');
  });
});

describe('InspectorState.deleteRelation', () => {
  test('removes relation from list and sends relation_deleted_requested', () => {
    const ins = new InspectorState();
    ins.hydrate({ active: false, picks: [], relations: [makeRelation('r1')], regions: [] });
    ins.deleteRelation('r1');
    expect(ins.relations).toHaveLength(0);
    expect(send).toHaveBeenCalledWith(expect.objectContaining({ kind: 'relation_deleted_requested', relation_id: 'r1' }));
  });
});

describe('InspectorState.updateRelation', () => {
  test('updates kind and note on existing relation and sends relation_updated_requested', () => {
    const ins = new InspectorState();
    ins.hydrate({ active: false, picks: [], relations: [makeRelation('r1')], regions: [] });
    ins.updateRelation('r1', 'triggers', 'new note');
    expect(ins.relations[0]!.kind).toBe('triggers');
    expect(ins.relations[0]!.note).toBe('new note');
    expect(send).toHaveBeenCalledWith(
      expect.objectContaining({ kind: 'relation_updated_requested', relation_id: 'r1', relation_kind: 'triggers', note: 'new note' })
    );
  });

  test('updateRelation on unknown id still sends wire-message', () => {
    const ins = new InspectorState();
    ins.updateRelation('unknown', 'part_of', null);
    expect(send).toHaveBeenCalledWith(expect.objectContaining({ kind: 'relation_updated_requested' }));
  });
});

// ---------------------------------------------------------------------------
// submitRegion / deleteRegion / updateRegion / selectRegion
// ---------------------------------------------------------------------------

describe('InspectorState.submitRegion', () => {
  test('appends new region and sets activeRegionId, clears activePickId', () => {
    const ins = new InspectorState();
    ins.hydrate({ active: false, picks: [], relations: [], regions: [], active_pick_id: 'p1' });
    const reg = makeRegion('reg1');
    ins.submitRegion(reg);
    expect(ins.regions).toHaveLength(1);
    expect(ins.activeRegionId).toBe('reg1');
    expect(ins.activePickId).toBeNull();
    expect(send).toHaveBeenCalledWith(expect.objectContaining({ kind: 'region_created_requested' }));
  });

  test('submitRegion assigns color_index if not provided', () => {
    const ins = new InspectorState();
    const reg = { ...makeRegion('reg1'), color_index: undefined };
    ins.submitRegion(reg as unknown as Region);
    expect(ins.regions[0]!.color_index).toBeDefined();
  });

  test('submitRegion overwrites existing region with same id', () => {
    const ins = new InspectorState();
    ins.submitRegion(makeRegion('reg1'));
    const updated = { ...makeRegion('reg1'), note: 'updated note' };
    ins.submitRegion(updated);
    expect(ins.regions).toHaveLength(1);
    expect(ins.regions[0]!.note).toBe('updated note');
  });
});

describe('InspectorState.deleteRegion', () => {
  test('removes region and clears activeRegionId if active', () => {
    const ins = new InspectorState();
    ins.hydrate({ active: false, picks: [], relations: [], regions: [makeRegion('reg1')], active_region_id: 'reg1' });
    ins.deleteRegion('reg1');
    expect(ins.regions).toHaveLength(0);
    expect(ins.activeRegionId).toBeNull();
    expect(send).toHaveBeenCalledWith(expect.objectContaining({ kind: 'region_deleted_requested', region_id: 'reg1' }));
  });

  test('cascades relation removal for region-kind endpoints on delete', () => {
    const ins = new InspectorState();
    const rel = {
      ...makeRelation('r1'),
      source_kind: 'region' as const,
      source_id: 'reg1',
      target_kind: 'pick' as const,
      target_id: 'p2',
    };
    ins.hydrate({ active: false, picks: [], relations: [rel], regions: [makeRegion('reg1')] });
    ins.deleteRegion('reg1');
    expect(ins.relations).toHaveLength(0);
  });
});

describe('InspectorState.updateRegion', () => {
  test('updates note on existing region and sends region_updated_requested', () => {
    const ins = new InspectorState();
    ins.hydrate({ active: false, picks: [], relations: [], regions: [makeRegion('reg1')] });
    ins.updateRegion('reg1', 'my region note');
    expect(ins.regions[0]!.note).toBe('my region note');
    expect(send).toHaveBeenCalledWith(
      expect.objectContaining({ kind: 'region_updated_requested', region_id: 'reg1', note: 'my region note' })
    );
  });
});

describe('InspectorState.selectRegion', () => {
  test('sets activeRegionId and clears activePickId, sends region_selected_requested', () => {
    const ins = new InspectorState();
    ins.hydrate({ active: false, picks: [], relations: [], regions: [makeRegion('reg1')], active_pick_id: 'p1' });
    ins.selectRegion('reg1');
    expect(ins.activeRegionId).toBe('reg1');
    expect(ins.activePickId).toBeNull();
    expect(send).toHaveBeenCalledWith(expect.objectContaining({ kind: 'region_selected_requested', region_id: 'reg1' }));
  });
});

// ---------------------------------------------------------------------------
// derived: activePick / activeRegion
// ---------------------------------------------------------------------------

describe('InspectorState derived accessors', () => {
  test('activePick returns the pick matching activePickId', () => {
    const ins = new InspectorState();
    const pick = makePick('p1');
    ins.hydrate({ active: false, picks: [pick], active_pick_id: 'p1', relations: [], regions: [] });
    expect(ins.activePick).toBe(ins.picks[0]);
  });

  test('activePick returns null when no active pick', () => {
    const ins = new InspectorState();
    ins.hydrate({ active: false, picks: [makePick('p1')], active_pick_id: null, relations: [], regions: [] });
    expect(ins.activePick).toBeNull();
  });

  test('activeRegion returns the region matching activeRegionId', () => {
    const ins = new InspectorState();
    const reg = makeRegion('reg1');
    ins.hydrate({ active: false, picks: [], relations: [], regions: [reg], active_region_id: 'reg1' });
    expect(ins.activeRegion).toBe(ins.regions[0]);
  });

  test('activeRegion returns null when no active region', () => {
    const ins = new InspectorState();
    ins.hydrate({ active: false, picks: [], relations: [], regions: [makeRegion('reg1')], active_region_id: null });
    expect(ins.activeRegion).toBeNull();
  });
});
