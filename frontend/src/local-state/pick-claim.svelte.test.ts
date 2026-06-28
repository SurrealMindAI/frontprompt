/**
 * PickClaim — coordination tests.
 *
 * The pick-claim singleton manages "which button owns pick mode" via
 * acquire/release/releaseSilently/routePick/routeCancel.
 *
 * Bridge + backendState are mocked so no real wire-send happens.
 */
const send = vi.hoisted(() => vi.fn());
vi.mock('../bridge/bridge.svelte', () => ({ bridge: { send } }));

import { describe, expect, test, vi, beforeEach } from 'vitest';
import { pickClaim, GLOBAL_PICK_ID } from './pick-claim.svelte';
import { backendState } from '../backend-state/backend-state.svelte';
import type { Pick } from '../_generated/state';

function makePick(id = 'p1'): Pick {
  return {
    pick_id: id,
    url: 'https://example.com',
    timestamp_ms: 0,
    color_index: 0,
    element: {
      selector: `#${id}`,
      fingerprint: { tag: 'div', attributes: {}, text: '', path: [], parent_name: '', parent_attribs: {}, siblings: [] },
      text_snippet: '',
      rect: { x: 0, y: 0, width: 10, height: 10 },
    },
    comment: '',
  } as unknown as Pick;
}

beforeEach(() => {
  send.mockClear();
  // Reset claim state between tests
  pickClaim.current = null;
  // Reset inspector active state
  backendState.inspector.active = false;
});

// ---------------------------------------------------------------------------
// acquire
// ---------------------------------------------------------------------------

describe('pickClaim.acquire', () => {
  test('sets current claim', () => {
    const onPick = vi.fn();
    pickClaim.acquire({ id: 'btn-a', onPick });
    expect(pickClaim.current?.id).toBe('btn-a');
  });

  test('activates inspector if not already active', () => {
    backendState.inspector.active = false;
    const onPick = vi.fn();
    pickClaim.acquire({ id: 'btn-a', onPick });
    expect(backendState.inspector.active).toBe(true);
    expect(send).toHaveBeenCalledWith(expect.objectContaining({ kind: 'inspector_activate_requested' }));
  });

  test('does not double-activate inspector if already active', () => {
    backendState.inspector.active = true;
    const onPick = vi.fn();
    pickClaim.acquire({ id: 'btn-a', onPick });
    // Should not call activate again
    expect(send).not.toHaveBeenCalled();
  });

  test('fires onCancel of previous claim when a new acquire preempts it', () => {
    const onCancelA = vi.fn();
    const onPickA = vi.fn();
    const onPickB = vi.fn();
    pickClaim.acquire({ id: 'btn-a', onPick: onPickA, onCancel: onCancelA });
    pickClaim.acquire({ id: 'btn-b', onPick: onPickB });
    expect(onCancelA).toHaveBeenCalledOnce();
    expect(pickClaim.current?.id).toBe('btn-b');
  });

  test('does not fire onCancel when re-acquiring with same id', () => {
    const onCancel = vi.fn();
    const onPick = vi.fn();
    pickClaim.acquire({ id: 'btn-a', onPick, onCancel });
    pickClaim.acquire({ id: 'btn-a', onPick, onCancel });
    expect(onCancel).not.toHaveBeenCalled();
  });
});

// ---------------------------------------------------------------------------
// isClaimedBy
// ---------------------------------------------------------------------------

describe('pickClaim.isClaimedBy', () => {
  test('returns true when id matches current claim', () => {
    pickClaim.acquire({ id: 'my-btn', onPick: vi.fn() });
    expect(pickClaim.isClaimedBy('my-btn')).toBe(true);
  });

  test('returns false when no claim', () => {
    expect(pickClaim.isClaimedBy('my-btn')).toBe(false);
  });

  test('returns false when different id holds claim', () => {
    pickClaim.acquire({ id: 'other-btn', onPick: vi.fn() });
    expect(pickClaim.isClaimedBy('my-btn')).toBe(false);
  });
});

// ---------------------------------------------------------------------------
// releaseSilently
// ---------------------------------------------------------------------------

describe('pickClaim.releaseSilently', () => {
  test('clears current claim without firing onCancel', () => {
    const onCancel = vi.fn();
    pickClaim.acquire({ id: 'btn-a', onPick: vi.fn(), onCancel });
    pickClaim.releaseSilently();
    expect(pickClaim.current).toBeNull();
    expect(onCancel).not.toHaveBeenCalled();
  });

  test('cancels inspector if active', () => {
    backendState.inspector.active = true;
    pickClaim.releaseSilently();
    expect(backendState.inspector.active).toBe(false);
    expect(send).toHaveBeenCalledWith(expect.objectContaining({ kind: 'inspector_canceled_requested' }));
  });
});

// ---------------------------------------------------------------------------
// release
// ---------------------------------------------------------------------------

describe('pickClaim.release', () => {
  test('clears current claim and fires onCancel', () => {
    const onCancel = vi.fn();
    pickClaim.acquire({ id: 'btn-a', onPick: vi.fn(), onCancel });
    // Prevent double activate by setting active directly
    send.mockClear();
    pickClaim.release();
    expect(pickClaim.current).toBeNull();
    expect(onCancel).toHaveBeenCalledOnce();
  });

  test('cancels inspector if active', () => {
    backendState.inspector.active = true;
    pickClaim.acquire({ id: 'btn-a', onPick: vi.fn() });
    send.mockClear();
    backendState.inspector.active = true;
    pickClaim.release();
    expect(send).toHaveBeenCalledWith(expect.objectContaining({ kind: 'inspector_canceled_requested' }));
  });

  test('does not throw when releasing with no current claim', () => {
    pickClaim.current = null;
    backendState.inspector.active = false;
    expect(() => pickClaim.release()).not.toThrow();
  });
});

// ---------------------------------------------------------------------------
// routePick
// ---------------------------------------------------------------------------

describe('pickClaim.routePick', () => {
  test('calls onPick with the captured pick and then releases silently', () => {
    const onPick = vi.fn();
    const pick = makePick('p1');
    pickClaim.acquire({ id: 'btn-a', onPick });
    send.mockClear();
    backendState.inspector.active = false; // prevent cancel call
    pickClaim.routePick(pick);
    expect(onPick).toHaveBeenCalledWith(pick);
    expect(pickClaim.current).toBeNull();
  });

  test('is a no-op (no throw) when no claim is set', () => {
    expect(() => pickClaim.routePick(makePick())).not.toThrow();
  });
});

// ---------------------------------------------------------------------------
// routeCancel
// ---------------------------------------------------------------------------

describe('pickClaim.routeCancel', () => {
  test('fires onCancel and releases silently', () => {
    const onCancel = vi.fn();
    pickClaim.acquire({ id: 'btn-a', onPick: vi.fn(), onCancel });
    send.mockClear();
    backendState.inspector.active = false;
    pickClaim.routeCancel();
    expect(onCancel).toHaveBeenCalledOnce();
    expect(pickClaim.current).toBeNull();
  });

  test('does not throw when no claim is set', () => {
    expect(() => pickClaim.routeCancel()).not.toThrow();
  });
});

// ---------------------------------------------------------------------------
// GLOBAL_PICK_ID constant
// ---------------------------------------------------------------------------

describe('GLOBAL_PICK_ID', () => {
  test('is the expected string for the global toggle button', () => {
    expect(GLOBAL_PICK_ID).toBe('pick:global');
  });
});
