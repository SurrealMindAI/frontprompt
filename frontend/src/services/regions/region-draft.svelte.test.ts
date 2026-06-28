/**
 * RegionDraft — state-machine tests.
 *
 * Covers: start, setOrigin, updateCurrent, cancel, and the rect derived.
 * commit() is NOT tested here — it calls scanRegion + window.scrollX/Y +
 * DOM APIs which are not available in jsdom without a real overlay.
 *
 * bridge is mocked to silence any indirect send calls.
 */
const send = vi.hoisted(() => vi.fn());
vi.mock('../../bridge/bridge.svelte', () => ({ bridge: { send } }));

const submitRegion = vi.hoisted(() => vi.fn());
const submitPick = vi.hoisted(() => vi.fn(() => 'pick-id'));
const submitRelation = vi.hoisted(() => vi.fn());
vi.mock('../../backend-state/backend-state.svelte', () => ({
  backendState: {
    inspector: {
      submitRegion,
      submitPick,
      submitRelation,
      picks: [],
      relations: [],
      regions: [],
      active: false,
    },
  },
}));

import { describe, expect, test, beforeEach } from 'vitest';
import { regionDraft } from './region-draft.svelte';

beforeEach(() => {
  send.mockClear();
  submitRegion.mockClear();
  submitPick.mockClear();
  submitRelation.mockClear();
  // Reset to idle state
  regionDraft.cancel();
});

// ---------------------------------------------------------------------------
// Initial state
// ---------------------------------------------------------------------------

describe('regionDraft initial state', () => {
  test('drafting starts as false', () => {
    expect(regionDraft.drafting).toBe(false);
  });

  test('origin starts as null', () => {
    expect(regionDraft.origin).toBeNull();
  });

  test('current starts as null', () => {
    expect(regionDraft.current).toBeNull();
  });

  test('rect starts as null', () => {
    expect(regionDraft.rect).toBeNull();
  });
});

// ---------------------------------------------------------------------------
// start
// ---------------------------------------------------------------------------

describe('regionDraft.start', () => {
  test('sets drafting to true', () => {
    regionDraft.start();
    expect(regionDraft.drafting).toBe(true);
  });

  test('clears origin and current', () => {
    // pre-set some state
    regionDraft.start();
    regionDraft.setOrigin(10, 10);
    regionDraft.start();
    expect(regionDraft.origin).toBeNull();
    expect(regionDraft.current).toBeNull();
  });

  test('rect is null after start', () => {
    regionDraft.start();
    expect(regionDraft.rect).toBeNull();
  });
});

// ---------------------------------------------------------------------------
// setOrigin
// ---------------------------------------------------------------------------

describe('regionDraft.setOrigin', () => {
  test('sets origin and current to same point', () => {
    regionDraft.start();
    regionDraft.setOrigin(50, 75);
    expect(regionDraft.origin).toEqual({ x: 50, y: 75 });
    expect(regionDraft.current).toEqual({ x: 50, y: 75 });
  });

  test('rect is zero-area (point) after setOrigin', () => {
    regionDraft.start();
    regionDraft.setOrigin(20, 30);
    const r = regionDraft.rect;
    expect(r).not.toBeNull();
    expect(r!.width).toBe(0);
    expect(r!.height).toBe(0);
  });
});

// ---------------------------------------------------------------------------
// updateCurrent
// ---------------------------------------------------------------------------

describe('regionDraft.updateCurrent', () => {
  test('updates current pointer position', () => {
    regionDraft.start();
    regionDraft.setOrigin(10, 10);
    regionDraft.updateCurrent(60, 90);
    expect(regionDraft.current).toEqual({ x: 60, y: 90 });
  });

  test('is a no-op when origin is null', () => {
    regionDraft.start();
    regionDraft.updateCurrent(60, 90); // no setOrigin called first
    expect(regionDraft.current).toBeNull();
  });
});

// ---------------------------------------------------------------------------
// rect derived
// ---------------------------------------------------------------------------

describe('regionDraft rect derived', () => {
  test('rect is null when both origin and current are null', () => {
    regionDraft.cancel();
    expect(regionDraft.rect).toBeNull();
  });

  test('rect has correct width and height for simple drag', () => {
    regionDraft.start();
    regionDraft.setOrigin(10, 20);
    regionDraft.updateCurrent(110, 120);
    const r = regionDraft.rect;
    expect(r!.width).toBe(100);
    expect(r!.height).toBe(100);
    expect(r!.x).toBe(10);
    expect(r!.y).toBe(20);
  });

  test('rect is normalized for reverse-direction drag (current < origin)', () => {
    regionDraft.start();
    regionDraft.setOrigin(100, 100);
    regionDraft.updateCurrent(10, 20);
    const r = regionDraft.rect;
    // x = min(100, 10) = 10
    expect(r!.x).toBe(10);
    expect(r!.y).toBe(20);
    // width = abs(10 - 100) = 90, height = abs(20 - 100) = 80
    expect(r!.width).toBe(90);
    expect(r!.height).toBe(80);
  });

  test('rect updates reactively as current changes', () => {
    regionDraft.start();
    regionDraft.setOrigin(0, 0);
    regionDraft.updateCurrent(50, 50);
    expect(regionDraft.rect!.width).toBe(50);
    regionDraft.updateCurrent(200, 200);
    expect(regionDraft.rect!.width).toBe(200);
  });
});

// ---------------------------------------------------------------------------
// commit
// ---------------------------------------------------------------------------

describe('regionDraft.commit', () => {
  test('commit() with too-small rect calls cancel() instead of submitRegion', () => {
    regionDraft.start();
    regionDraft.setOrigin(10, 10);
    regionDraft.updateCurrent(13, 13); // 3x3 rect — below 5x5 threshold
    regionDraft.commit();
    expect(submitRegion).not.toHaveBeenCalled();
    expect(regionDraft.drafting).toBe(false); // canceled
  });

  test('commit() with no rect (origin only) calls cancel() without submitRegion', () => {
    regionDraft.start();
    regionDraft.setOrigin(10, 10);
    // No updateCurrent call — rect is 0x0
    regionDraft.commit();
    expect(submitRegion).not.toHaveBeenCalled();
    expect(regionDraft.drafting).toBe(false);
  });

  test('commit() with valid rect calls submitRegion', () => {
    regionDraft.start();
    regionDraft.setOrigin(10, 10);
    regionDraft.updateCurrent(100, 100); // 90x90 rect — valid
    regionDraft.commit();
    expect(submitRegion).toHaveBeenCalledOnce();
  });

  test('commit() with valid rect resets drafting to false', () => {
    regionDraft.start();
    regionDraft.setOrigin(10, 10);
    regionDraft.updateCurrent(100, 100);
    expect(regionDraft.drafting).toBe(true);
    regionDraft.commit();
    expect(regionDraft.drafting).toBe(false);
  });

  test('commit() with valid rect resets origin and current to null', () => {
    regionDraft.start();
    regionDraft.setOrigin(20, 30);
    regionDraft.updateCurrent(200, 300);
    regionDraft.commit();
    expect(regionDraft.origin).toBeNull();
    expect(regionDraft.current).toBeNull();
  });

  test('commit() passes page-absolute rect to submitRegion', () => {
    regionDraft.start();
    regionDraft.setOrigin(10, 20);
    regionDraft.updateCurrent(110, 120); // 100x100 rect
    regionDraft.commit();
    const callArg = submitRegion.mock.calls[0]![0];
    // rect should include window.scrollX/Y offset (both 0 in jsdom)
    expect(callArg.rect.width).toBe(100);
    expect(callArg.rect.height).toBe(100);
  });

  test('commit() passes viewport_snapshot to submitRegion', () => {
    regionDraft.start();
    regionDraft.setOrigin(10, 10);
    regionDraft.updateCurrent(100, 100);
    regionDraft.commit();
    const callArg = submitRegion.mock.calls[0]![0];
    expect(callArg.viewport_snapshot).toBeDefined();
    expect(typeof callArg.viewport_snapshot.scroll_x).toBe('number');
    expect(typeof callArg.viewport_snapshot.document_w).toBe('number');
  });

  test('commit() called without start() does nothing (rect is null)', () => {
    // regionDraft is in idle state (cancel() was called in beforeEach)
    regionDraft.commit();
    expect(submitRegion).not.toHaveBeenCalled();
    expect(regionDraft.drafting).toBe(false);
  });
});

// ---------------------------------------------------------------------------
// cancel
// ---------------------------------------------------------------------------

describe('regionDraft.cancel', () => {
  test('sets drafting to false', () => {
    regionDraft.start();
    regionDraft.cancel();
    expect(regionDraft.drafting).toBe(false);
  });

  test('clears origin', () => {
    regionDraft.start();
    regionDraft.setOrigin(10, 20);
    regionDraft.cancel();
    expect(regionDraft.origin).toBeNull();
  });

  test('clears current', () => {
    regionDraft.start();
    regionDraft.setOrigin(10, 20);
    regionDraft.updateCurrent(50, 60);
    regionDraft.cancel();
    expect(regionDraft.current).toBeNull();
  });

  test('rect is null after cancel', () => {
    regionDraft.start();
    regionDraft.setOrigin(10, 10);
    regionDraft.updateCurrent(100, 100);
    regionDraft.cancel();
    expect(regionDraft.rect).toBeNull();
  });
});
