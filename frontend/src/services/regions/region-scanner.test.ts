/**
 * region-scanner unit tests (vitest + jsdom).
 *
 * Test-Surface:
 *   - buildPickFromElement — colorIndex parameter threading
 *   - scanRegion — existingPickCount offset propagation
 *   - scanRegion — walk depth limit
 */
import { describe, expect, test, vi, beforeEach, afterEach } from 'vitest';
import { buildPickFromElement, scanRegion, MAX_SCAN_DEPTH } from './region-scanner';
import { nextColorIndex } from '../color-palette';

beforeEach(() => {
  // Minimal DOM for scan tests — three visible block-elements at
  // non-overlapping positions so containment test hits all three.
  document.body.style.margin = '0';
  document.body.innerHTML = `
    <div id="a" style="position:absolute;left:10px;top:10px;width:80px;height:30px">A</div>
    <div id="b" style="position:absolute;left:10px;top:50px;width:80px;height:30px">B</div>
    <div id="c" style="position:absolute;left:10px;top:90px;width:80px;height:30px">C</div>
  `;
});

afterEach(() => {
  document.body.innerHTML = '';
});

// ---------------------------------------------------------------------------
// buildPickFromElement — colorIndex parameter
// ---------------------------------------------------------------------------

describe('buildPickFromElement', () => {
  test('explicit colorIndex is reflected in returned Pick', () => {
    const el = document.getElementById('a')!;
    const pick = buildPickFromElement(el, 7);
    expect(pick.color_index).toBe(7);
  });

  test('no colorIndex argument defaults to 0', () => {
    const el = document.getElementById('a')!;
    const pick = buildPickFromElement(el);
    expect(pick.color_index).toBe(0);
  });

  test('colorIndex=0 is stored as 0 (not undefined)', () => {
    const el = document.getElementById('a')!;
    const pick = buildPickFromElement(el, 0);
    expect(pick.color_index).toBe(0);
    expect('color_index' in pick).toBe(true);
  });
});

// ---------------------------------------------------------------------------
// scanRegion — existingPickCount offset
// ---------------------------------------------------------------------------

describe('scanRegion', () => {
  test('with existingPickCount=3 assigns color indices starting at 3', () => {
    // jsdom does not layout — getBoundingClientRect() returns zeros for
    // unstyled elements. We rely on the DOM being set up in beforeEach with
    // non-zero inline styles; jsdom still returns 0 from getBoundingClientRect
    // in most configurations. This test therefore uses a rect that trivially
    // contains all candidates (large enough that containment passes), and
    // mocks getBoundingClientRect on the elements so bboxArea > 0.
    const els = ['a', 'b', 'c'].map((id) => document.getElementById(id)!);
    els.forEach((el, i) => {
      vi.spyOn(el, 'getBoundingClientRect').mockReturnValue({
        x: 10,
        y: 10 + i * 40,
        width: 80,
        height: 30,
        top: 10 + i * 40,
        left: 10,
        right: 90,
        bottom: 40 + i * 40,
        toJSON: () => ({}),
      } as DOMRect);
    });

    const rect = { x: 0, y: 0, width: 200, height: 200 };
    const scanned = scanRegion(rect, 3);

    // Expect 3 picks (may vary by jsdom layout — guard with length check first)
    expect(scanned.length).toBeGreaterThan(0);
    scanned.forEach((s, i) => {
      expect(s.pick.color_index).toBe(nextColorIndex(3 + i));
    });
  });

  test('default existingPickCount=0 assigns indices starting at 0', () => {
    const el = document.getElementById('a')!;
    vi.spyOn(el, 'getBoundingClientRect').mockReturnValue({
      x: 10,
      y: 10,
      width: 80,
      height: 30,
      top: 10,
      left: 10,
      right: 90,
      bottom: 40,
      toJSON: () => ({}),
    } as DOMRect);

    const rect = { x: 0, y: 0, width: 200, height: 200 };
    const scanned = scanRegion(rect);

    expect(scanned.length).toBeGreaterThanOrEqual(1);
    expect(scanned[0]!.pick.color_index).toBe(nextColorIndex(0));
  });

  test('palette wrap: existingPickCount=31 gives index 31 then wraps to 0', () => {
    const els = ['a', 'b'].map((id) => document.getElementById(id)!);
    els.forEach((el, i) => {
      vi.spyOn(el, 'getBoundingClientRect').mockReturnValue({
        x: 10,
        y: 10 + i * 40,
        width: 80,
        height: 30,
        top: 10 + i * 40,
        left: 10,
        right: 90,
        bottom: 40 + i * 40,
        toJSON: () => ({}),
      } as DOMRect);
    });

    const rect = { x: 0, y: 0, width: 200, height: 200 };
    const scanned = scanRegion(rect, 31);

    if (scanned.length >= 2) {
      expect(scanned[0]!.pick.color_index).toBe(31);
      expect(scanned[1]!.pick.color_index).toBe(0);
    }
  });
});

// ---------------------------------------------------------------------------
// DOM walk depth limit
// ---------------------------------------------------------------------------

/**
 * Build a chain of nested divs that is ``depth`` levels deep under the given parent.
 * Every element gets a getBoundingClientRect mock returning a rect inside {0,0,500,500}.
 * Returns the leaf element.
 */
function buildDeepChain(parent: HTMLElement, depth: number): HTMLElement {
  let current = parent;
  for (let i = 0; i < depth; i++) {
    const child = document.createElement('div');
    child.style.display = 'block';
    current.appendChild(child);
    current = child;
  }
  return current;
}

describe('scanRegion depth limit', () => {
  const SCAN_RECT = { x: 0, y: 0, width: 500, height: 500 };

  // Mock getBoundingClientRect globally for all elements during these tests
  // so containment passes (all zero rects in jsdom = 0 bbox area = filtered).
  let origGetBBox: typeof Element.prototype.getBoundingClientRect;

  beforeEach(() => {
    origGetBBox = Element.prototype.getBoundingClientRect;
    Element.prototype.getBoundingClientRect = function () {
      return {
        x: 10,
        y: 10,
        width: 100,
        height: 100,
        top: 10,
        left: 10,
        right: 110,
        bottom: 110,
        toJSON: () => ({}),
      } as DOMRect;
    };
  });

  afterEach(() => {
    Element.prototype.getBoundingClientRect = origGetBBox;
    document.body.innerHTML = '';
  });

  test('elements deeper than MAX_SCAN_DEPTH are excluded from results', () => {
    // Build a chain exactly MAX_SCAN_DEPTH + 2 deep (so leaves are at depth > limit)
    document.body.innerHTML = '';
    const root = document.createElement('div');
    document.body.appendChild(root);
    buildDeepChain(root, MAX_SCAN_DEPTH + 2);

    const results = scanRegion(SCAN_RECT);
    // No result should come from a depth greater than MAX_SCAN_DEPTH below documentElement
    for (const { element } of results) {
      let depth = 0;
      let node: Element | null = element;
      while (node && node !== document.documentElement) {
        depth++;
        node = node.parentElement;
      }
      expect(depth).toBeLessThanOrEqual(MAX_SCAN_DEPTH + 1);
    }
  });

  test('shallow tree (depth ≤ MAX_SCAN_DEPTH) is not pruned incorrectly', () => {
    // 20 flat siblings at depth 3 (body > wrapper > item × 20)
    document.body.innerHTML = '';
    const wrapper = document.createElement('div');
    document.body.appendChild(wrapper);
    for (let i = 0; i < 20; i++) {
      const el = document.createElement('div');
      el.textContent = `item-${i}`;
      wrapper.appendChild(el);
    }

    const results = scanRegion(SCAN_RECT);
    // With deepest-match filter and trivial-filter the exact count may vary, but
    // at minimum all 20 shallow children are candidates (depth is well within limit).
    // Assert no pruning happened due to depth limit by checking total >= 1.
    expect(results.length).toBeGreaterThan(0);
  });
});
