/**
 * PositionService + setupPositionTracker unit tests (vitest + jsdom).
 *
 * Test-Surface:
 *   - liveRectForPick querySelector result cache
 *   - MutationObserver cache invalidation
 *   - RAF-batched positionTracker.bump (setupPositionTracker)
 *   - padding-preservation: liveRectForRegion expands by drawn padding delta
 *   - drift-detection: detectLayoutDrift helper
 */
import { describe, expect, test, vi, beforeEach, afterEach } from 'vitest';
import { PositionService, detectLayoutDrift } from './position-service.svelte';
import { positionTracker, setupPositionTracker } from './position-tracker.svelte';
import type { Pick, Region, Viewport } from '../../_generated/state';

// ---------------------------------------------------------------------------
// Helpers
// ---------------------------------------------------------------------------

function makePick(pickId: string, selector: string): Pick {
  return {
    pick_id: pickId,
    url: 'https://example.com',
    timestamp_ms: 0,
    element: {
      selector,
      fingerprint: {
        tag: 'div',
        attributes: {},
        text: '',
        path: [],
        parent_name: null,
        parent_attribs: {},
        parent_text: '',
        siblings: [],
        children: [],
      },
      text_snippet: '',
      rect: { x: 0, y: 0, width: 0, height: 0 },
    },
    comment: '',
    color_index: 0,
  };
}

function makeRegion(
  regionId: string,
  memberPickIds: string[],
  rect: { x: number; y: number; width: number; height: number },
  viewportSnapshot?: Viewport | null
): Region {
  return {
    region_id: regionId,
    rect,
    member_pick_ids: memberPickIds,
    timestamp_ms: 0,
    color_index: 0,
    viewport_snapshot: viewportSnapshot ?? null,
  };
}

// ---------------------------------------------------------------------------
// Test A: querySelector cache hit
// ---------------------------------------------------------------------------

describe('liveRectForPick', () => {
  let service: PositionService;

  beforeEach(() => {
    service = new PositionService();
    document.body.innerHTML = '<div id="target" style="width:100px;height:50px">Target</div>';
  });

  afterEach(() => {
    service.dispose();
    document.body.innerHTML = '';
    vi.restoreAllMocks();
  });

  test('A: querySelector called exactly once for two calls on same pick', () => {
    const spy = vi.spyOn(document, 'querySelector');
    const pick = makePick('p1', '#target');
    service.liveRectForPick(pick);
    service.liveRectForPick(pick);
    // querySelector should only be called once — second call hits cache
    expect(spy).toHaveBeenCalledTimes(1);
  });

  test('B: cache invalidated on DOM mutation — querySelector called again', async () => {
    const spy = vi.spyOn(document, 'querySelector');
    const pick = makePick('p1', '#target');
    // Prime the cache
    service.liveRectForPick(pick);
    expect(spy).toHaveBeenCalledTimes(1);

    // Mutate the DOM to trigger MutationObserver
    const newEl = document.createElement('span');
    document.body.appendChild(newEl);

    // Wait for MutationObserver callback (microtask queue)
    await new Promise((resolve) => setTimeout(resolve, 0));

    // Call again — cache should have been cleared by MutationObserver
    service.liveRectForPick(pick);
    expect(spy).toHaveBeenCalledTimes(2);
  });
});

// ---------------------------------------------------------------------------
// Test C: RAF batching in setupPositionTracker
// ---------------------------------------------------------------------------

describe('setupPositionTracker RAF batching', () => {
  let cleanup: (() => void) | null = null;
  let initialTick: number;

  beforeEach(() => {
    vi.useFakeTimers();
    initialTick = positionTracker.tick;
    cleanup = setupPositionTracker();
  });

  afterEach(() => {
    if (cleanup) {
      cleanup();
      cleanup = null;
    }
    vi.useRealTimers();
  });

  test('C1: 3 rapid scroll events produce 0 tick increments before rAF fires', () => {
    // Dispatch 3 scroll events synchronously
    window.dispatchEvent(new Event('scroll'));
    window.dispatchEvent(new Event('scroll'));
    window.dispatchEvent(new Event('scroll'));
    // Before rAF fires, tick must not have changed
    expect(positionTracker.tick).toBe(initialTick);
  });

  test('C2: after rAF fires, tick increments exactly once for 3 rapid scrolls', () => {
    window.dispatchEvent(new Event('scroll'));
    window.dispatchEvent(new Event('scroll'));
    window.dispatchEvent(new Event('scroll'));
    // Fire all timers (including rAF)
    vi.runAllTimers();
    expect(positionTracker.tick).toBe(initialTick + 1);
  });

  test('C3: second scroll after first rAF fires schedules another increment', () => {
    // First batch
    window.dispatchEvent(new Event('scroll'));
    vi.runAllTimers();
    expect(positionTracker.tick).toBe(initialTick + 1);

    // Second batch
    window.dispatchEvent(new Event('scroll'));
    vi.runAllTimers();
    expect(positionTracker.tick).toBe(initialTick + 2);
  });
});

// ---------------------------------------------------------------------------
// Test D: Drawn-padding preservation in liveRectForRegion
// ---------------------------------------------------------------------------

describe('liveRectForRegion padding-preservation', () => {
  let service: PositionService;

  beforeEach(() => {
    service = new PositionService();
  });

  afterEach(() => {
    service.dispose();
    vi.restoreAllMocks();
  });

  test('D1: liveRectForRegion expands live member bbox by drawn padding delta', () => {
    // Drawn rect (page-absolute): drawn with 20px padding on all sides around member
    // region.rect = {x:50, y:100, width:200, height:150}
    // member live rect (viewport, zero scroll): {x:70, y:120, width:160, height:110}
    // padding deltas: left=20, top=20, right=20, bottom=20
    // expected expanded rect = region.rect converted to viewport (zero scroll = same)

    document.body.innerHTML = '<div id="member" style="width:1px;height:1px">M</div>';
    const memberEl = document.getElementById('member')!;
    vi.spyOn(memberEl, 'getBoundingClientRect').mockReturnValue({
      x: 70,
      y: 120,
      width: 160,
      height: 110,
      top: 120,
      left: 70,
      bottom: 230,
      right: 230,
      toJSON: () => ({}),
    });

    const pick = makePick('p1', '#member');
    const region = makeRegion('r1', ['p1'], { x: 50, y: 100, width: 200, height: 150 });

    const result = service.liveRectForRegion(region, [pick]);

    expect(result).not.toBeNull();
    // At zero scroll, the padding-expanded rect should equal region.rect
    expect(result!.x).toBeCloseTo(50);
    expect(result!.y).toBeCloseTo(100);
    expect(result!.width).toBeCloseTo(200);
    expect(result!.height).toBeCloseTo(150);
  });

  test('D2: when member exceeds drawn rect (negative padding), clamps to zero — never shrinks below member bbox', () => {
    // Member live rect is LARGER than drawn rect → negative padding → clamp to 0
    // region.rect = {x:80, y:130, width:100, height:80}  (smaller than member)
    // member live rect = {x:70, y:120, width:160, height:110}
    // padLeft = 70 - 80 = -10 → clamped to 0
    // result should equal member bbox (no expansion, no shrink)

    document.body.innerHTML = '<div id="m2" style="width:1px;height:1px">M</div>';
    const memberEl = document.getElementById('m2')!;
    vi.spyOn(memberEl, 'getBoundingClientRect').mockReturnValue({
      x: 70,
      y: 120,
      width: 160,
      height: 110,
      top: 120,
      left: 70,
      bottom: 230,
      right: 230,
      toJSON: () => ({}),
    });

    const pick = makePick('p2', '#m2');
    const region = makeRegion('r2', ['p2'], { x: 80, y: 130, width: 100, height: 80 });

    const result = service.liveRectForRegion(region, [pick]);

    expect(result).not.toBeNull();
    // Clamped to member bbox (no negative expansion)
    expect(result!.x).toBeCloseTo(70);
    expect(result!.y).toBeCloseTo(120);
    expect(result!.width).toBeCloseTo(160);
    expect(result!.height).toBeCloseTo(110);
  });

  test('D3: no member picks → still returns null (ground-truth principle)', () => {
    const region = makeRegion('r3', [], { x: 50, y: 100, width: 200, height: 150 });
    const result = service.liveRectForRegion(region, []);
    expect(result).toBeNull();
  });
});

// ---------------------------------------------------------------------------
// Test E: detectLayoutDrift helper
// ---------------------------------------------------------------------------

describe('detectLayoutDrift', () => {
  function makeViewport(documentW: number, documentH: number): Viewport {
    return {
      scroll_x: 0,
      scroll_y: 0,
      viewport_w: 1920,
      viewport_h: 1080,
      document_w: documentW,
      document_h: documentH,
    };
  }

  test('E1: drift detected when document_w deviates by more than default threshold (50px)', () => {
    const stored = makeViewport(1920, 1080);
    // 1920 → 1366: diff = 554, threshold = 50
    expect(detectLayoutDrift(stored, 1366, 1080)).toBe(true);
  });

  test('E2: no drift when deviation is within threshold', () => {
    const stored = makeViewport(1920, 1080);
    // diff = 10, threshold = 50
    expect(detectLayoutDrift(stored, 1930, 1080)).toBe(false);
  });

  test('E3: drift detected when document_h deviates by more than threshold', () => {
    const stored = makeViewport(1920, 1080);
    // height diff = 100, threshold = 50
    expect(detectLayoutDrift(stored, 1920, 1180)).toBe(true);
  });

  test('E4: no drift when both dimensions are within threshold', () => {
    const stored = makeViewport(1920, 1080);
    expect(detectLayoutDrift(stored, 1940, 1060)).toBe(false);
  });

  test('E5: custom threshold respected', () => {
    const stored = makeViewport(1920, 1080);
    // diff = 10, custom threshold = 5 → drift
    expect(detectLayoutDrift(stored, 1930, 1080, 5)).toBe(true);
    // diff = 10, custom threshold = 15 → no drift
    expect(detectLayoutDrift(stored, 1930, 1080, 15)).toBe(false);
  });
});
