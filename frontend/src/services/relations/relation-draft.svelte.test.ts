/**
 * RelationDraft — state-machine tests.
 *
 * Covers: start, cancel, setSource/setTarget, setKind, setNote, commit,
 * and the canCommit derived (including self-loop prevention).
 *
 * bridge is mocked (commit → backendState.inspector.submitRelation → bridge.send).
 * backendState.inspector.submitRelation is also mocked to avoid needing a full
 * backend state setup.
 */
const send = vi.hoisted(() => vi.fn());
vi.mock('../../bridge/bridge.svelte', () => ({ bridge: { send } }));

// Mock backendState to intercept submitRelation calls without needing a full inspector.
const submitRelation = vi.hoisted(() => vi.fn());
vi.mock('../../backend-state/backend-state.svelte', () => ({
  backendState: {
    inspector: {
      submitRelation,
      picks: [],
      relations: [],
      regions: [],
      active: false,
      active_pick_id: null,
      active_region_id: null,
    },
  },
}));

import { describe, expect, test, vi, beforeEach } from 'vitest';
import { relationDraft } from './relation-draft.svelte';

beforeEach(() => {
  send.mockClear();
  submitRelation.mockClear();
  // Reset state machine to idle
  relationDraft.cancel();
});

// ---------------------------------------------------------------------------
// Initial state
// ---------------------------------------------------------------------------

describe('relationDraft initial state', () => {
  test('drafting starts as false', () => {
    expect(relationDraft.drafting).toBe(false);
  });

  test('source starts as null', () => {
    expect(relationDraft.source).toBeNull();
  });

  test('target starts as null', () => {
    expect(relationDraft.target).toBeNull();
  });

  test('kind starts as relates_to', () => {
    expect(relationDraft.kind).toBe('relates_to');
  });

  test('note starts as empty string', () => {
    expect(relationDraft.note).toBe('');
  });
});

// ---------------------------------------------------------------------------
// start
// ---------------------------------------------------------------------------

describe('relationDraft.start', () => {
  test('sets drafting to true', () => {
    relationDraft.start();
    expect(relationDraft.drafting).toBe(true);
  });

  test('resets source and target to null', () => {
    relationDraft.setSource({ id: 'p1', kind: 'pick' });
    relationDraft.setTarget({ id: 'p2', kind: 'pick' });
    relationDraft.start();
    expect(relationDraft.source).toBeNull();
    expect(relationDraft.target).toBeNull();
  });

  test('resets kind to relates_to', () => {
    relationDraft.setKind('triggers');
    relationDraft.start();
    expect(relationDraft.kind).toBe('relates_to');
  });

  test('resets note to empty string', () => {
    relationDraft.setNote('my note');
    relationDraft.start();
    expect(relationDraft.note).toBe('');
  });
});

// ---------------------------------------------------------------------------
// cancel
// ---------------------------------------------------------------------------

describe('relationDraft.cancel', () => {
  test('sets drafting to false', () => {
    relationDraft.start();
    relationDraft.cancel();
    expect(relationDraft.drafting).toBe(false);
  });

  test('clears source and target', () => {
    relationDraft.start();
    relationDraft.setSource({ id: 'p1', kind: 'pick' });
    relationDraft.cancel();
    expect(relationDraft.source).toBeNull();
    expect(relationDraft.target).toBeNull();
  });

  test('clears note', () => {
    relationDraft.setNote('some note');
    relationDraft.cancel();
    expect(relationDraft.note).toBe('');
  });
});

// ---------------------------------------------------------------------------
// setSource / setTarget
// ---------------------------------------------------------------------------

describe('relationDraft.setSource / setTarget', () => {
  test('setSource sets the source endpoint', () => {
    relationDraft.setSource({ id: 'p1', kind: 'pick' });
    expect(relationDraft.source).toEqual({ id: 'p1', kind: 'pick' });
  });

  test('setSource accepts null to clear', () => {
    relationDraft.setSource({ id: 'p1', kind: 'pick' });
    relationDraft.setSource(null);
    expect(relationDraft.source).toBeNull();
  });

  test('setTarget sets the target endpoint', () => {
    relationDraft.setTarget({ id: 'r1', kind: 'region' });
    expect(relationDraft.target).toEqual({ id: 'r1', kind: 'region' });
  });

  test('setTarget accepts null to clear', () => {
    relationDraft.setTarget({ id: 'p2', kind: 'pick' });
    relationDraft.setTarget(null);
    expect(relationDraft.target).toBeNull();
  });
});

// ---------------------------------------------------------------------------
// setKind
// ---------------------------------------------------------------------------

describe('relationDraft.setKind', () => {
  test('sets kind to triggers', () => {
    relationDraft.setKind('triggers');
    expect(relationDraft.kind).toBe('triggers');
  });

  test('sets kind to part_of', () => {
    relationDraft.setKind('part_of');
    expect(relationDraft.kind).toBe('part_of');
  });

  test('sets kind back to relates_to', () => {
    relationDraft.setKind('triggers');
    relationDraft.setKind('relates_to');
    expect(relationDraft.kind).toBe('relates_to');
  });
});

// ---------------------------------------------------------------------------
// setNote
// ---------------------------------------------------------------------------

describe('relationDraft.setNote', () => {
  test('sets the note', () => {
    relationDraft.setNote('hello world');
    expect(relationDraft.note).toBe('hello world');
  });

  test('empty string clears the note', () => {
    relationDraft.setNote('text');
    relationDraft.setNote('');
    expect(relationDraft.note).toBe('');
  });
});

// ---------------------------------------------------------------------------
// canCommit derived
// ---------------------------------------------------------------------------

describe('relationDraft.canCommit', () => {
  test('false when both endpoints are null', () => {
    relationDraft.cancel();
    expect(relationDraft.canCommit).toBe(false);
  });

  test('false when only source is set', () => {
    relationDraft.setSource({ id: 'p1', kind: 'pick' });
    expect(relationDraft.canCommit).toBe(false);
  });

  test('false when only target is set', () => {
    relationDraft.setTarget({ id: 'p2', kind: 'pick' });
    expect(relationDraft.canCommit).toBe(false);
  });

  test('true when both source and target are different', () => {
    relationDraft.setSource({ id: 'p1', kind: 'pick' });
    relationDraft.setTarget({ id: 'p2', kind: 'pick' });
    expect(relationDraft.canCommit).toBe(true);
  });

  test('false for self-loop (same id AND same kind)', () => {
    relationDraft.setSource({ id: 'p1', kind: 'pick' });
    relationDraft.setTarget({ id: 'p1', kind: 'pick' });
    expect(relationDraft.canCommit).toBe(false);
  });

  test('true when same id but different kind (pick→region cross)', () => {
    // Same id string but different kinds → not a self-loop
    relationDraft.setSource({ id: 'shared-id', kind: 'pick' });
    relationDraft.setTarget({ id: 'shared-id', kind: 'region' });
    expect(relationDraft.canCommit).toBe(true);
  });
});

// ---------------------------------------------------------------------------
// commit
// ---------------------------------------------------------------------------

describe('relationDraft.commit', () => {
  test('calls submitRelation and resets to idle', () => {
    relationDraft.start();
    relationDraft.setSource({ id: 'p1', kind: 'pick' });
    relationDraft.setTarget({ id: 'p2', kind: 'pick' });
    relationDraft.setKind('triggers');
    relationDraft.setNote('important');
    relationDraft.commit();

    expect(submitRelation).toHaveBeenCalledOnce();
    const arg = submitRelation.mock.calls[0]![0];
    expect(arg.source_id).toBe('p1');
    expect(arg.source_kind).toBe('pick');
    expect(arg.target_id).toBe('p2');
    expect(arg.target_kind).toBe('pick');
    expect(arg.kind).toBe('triggers');
    expect(arg.note).toBe('important');
    expect(typeof arg.relation_id).toBe('string');

    // after commit, draft resets
    expect(relationDraft.drafting).toBe(false);
    expect(relationDraft.source).toBeNull();
  });

  test('trims whitespace-only note to null', () => {
    relationDraft.start();
    relationDraft.setSource({ id: 'p1', kind: 'pick' });
    relationDraft.setTarget({ id: 'p2', kind: 'pick' });
    relationDraft.setNote('   ');
    relationDraft.commit();

    const arg = submitRelation.mock.calls[0]![0];
    expect(arg.note).toBeNull();
  });

  test('trims whitespace from note', () => {
    relationDraft.start();
    relationDraft.setSource({ id: 'p1', kind: 'pick' });
    relationDraft.setTarget({ id: 'p2', kind: 'pick' });
    relationDraft.setNote('  hello  ');
    relationDraft.commit();

    const arg = submitRelation.mock.calls[0]![0];
    expect(arg.note).toBe('hello');
  });

  test('is a no-op when canCommit is false (source missing)', () => {
    relationDraft.setTarget({ id: 'p2', kind: 'pick' });
    relationDraft.commit();
    expect(submitRelation).not.toHaveBeenCalled();
  });

  test('is a no-op when canCommit is false (self-loop)', () => {
    relationDraft.setSource({ id: 'p1', kind: 'pick' });
    relationDraft.setTarget({ id: 'p1', kind: 'pick' });
    relationDraft.commit();
    expect(submitRelation).not.toHaveBeenCalled();
  });

  test('generates a unique relation_id per commit', () => {
    relationDraft.start();
    relationDraft.setSource({ id: 'p1', kind: 'pick' });
    relationDraft.setTarget({ id: 'p2', kind: 'pick' });
    relationDraft.commit();

    relationDraft.start();
    relationDraft.setSource({ id: 'p1', kind: 'pick' });
    relationDraft.setTarget({ id: 'p2', kind: 'pick' });
    relationDraft.commit();

    const id1 = submitRelation.mock.calls[0]![0].relation_id;
    const id2 = submitRelation.mock.calls[1]![0].relation_id;
    expect(id1).not.toBe(id2);
  });
});
