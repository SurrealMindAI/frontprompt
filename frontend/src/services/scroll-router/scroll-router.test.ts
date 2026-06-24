/**
 * scroll-router tests (vitest + jsdom).
 *
 * Note zur jsdom-limitation: jsdom liefert ``scrollHeight``, ``clientHeight``
 * als 0 by default — der layout-engine "rendert" nicht. Wir mocken die
 * properties per ``Object.defineProperty`` direkt am element für die tests
 * die scrollable-detection prüfen.
 */
import { afterEach, beforeEach, describe, expect, test, vi } from 'vitest';
import { findScrollableAncestor, isScrollable, forwardWheel } from './index';

// jsdom liefert ``document.elementsFromPoint`` nicht als own-property —
// vi.spyOn würde fehlschlagen. Direkt monkey-patchen pro test.
const originalElementsFromPoint = (document as Document).elementsFromPoint;

beforeEach(() => {
  // Default: empty stack (no elements under cursor)
  (document as Document).elementsFromPoint = vi.fn(() => []);
});

afterEach(() => {
  document.body.innerHTML = '';
  if (originalElementsFromPoint) {
    (document as Document).elementsFromPoint = originalElementsFromPoint;
  }
});

/** Setze die mock-liste was elementsFromPoint zurückgibt. */
function mockElementsAtPoint(elements: Element[]): void {
  (document as Document).elementsFromPoint = vi.fn(() => elements);
}

// ---------------------------------------------------------------------------
// Helpers — jsdom layout-engine workarounds
// ---------------------------------------------------------------------------

/** Patch ein element so dass es als scrollable detected wird (jsdom mock). */
function makeScrollable(
  el: Element,
  opts: { axis?: 'x' | 'y' | 'both'; overflow?: 'auto' | 'scroll' } = {}
): void {
  const axis = opts.axis ?? 'y';
  const overflow = opts.overflow ?? 'auto';
  if (axis === 'y' || axis === 'both') {
    Object.defineProperty(el, 'scrollHeight', { value: 1000, configurable: true });
    Object.defineProperty(el, 'clientHeight', { value: 100, configurable: true });
    (el as HTMLElement).style.overflowY = overflow;
  }
  if (axis === 'x' || axis === 'both') {
    Object.defineProperty(el, 'scrollWidth', { value: 1000, configurable: true });
    Object.defineProperty(el, 'clientWidth', { value: 100, configurable: true });
    (el as HTMLElement).style.overflowX = overflow;
  }
}

// ---------------------------------------------------------------------------
// isScrollable
// ---------------------------------------------------------------------------

describe('isScrollable', () => {
  test('returns false for plain div with default overflow', () => {
    document.body.innerHTML = '<div id="x">content</div>';
    const el = document.getElementById('x')!;
    expect(isScrollable(el)).toBe(false);
  });

  test('returns false for overflow:auto wenn content NICHT overflowt', () => {
    document.body.innerHTML = '<div id="x" style="overflow-y:auto">tiny</div>';
    const el = document.getElementById('x')!;
    // jsdom: default scrollHeight/clientHeight both 0 → kein overflow
    expect(isScrollable(el)).toBe(false);
  });

  test('returns true for overflow:auto + content overflowt (y-axis)', () => {
    document.body.innerHTML = '<div id="x">x</div>';
    const el = document.getElementById('x')!;
    makeScrollable(el, { axis: 'y', overflow: 'auto' });
    expect(isScrollable(el)).toBe(true);
  });

  test('returns true for overflow:scroll + content overflowt', () => {
    document.body.innerHTML = '<div id="x">x</div>';
    const el = document.getElementById('x')!;
    makeScrollable(el, { axis: 'y', overflow: 'scroll' });
    expect(isScrollable(el)).toBe(true);
  });

  test('returns true für x-axis-only scroller', () => {
    document.body.innerHTML = '<div id="x">x</div>';
    const el = document.getElementById('x')!;
    makeScrollable(el, { axis: 'x', overflow: 'auto' });
    expect(isScrollable(el)).toBe(true);
  });

  test('returns false für overflow:hidden trotz overflow', () => {
    document.body.innerHTML = '<div id="x" style="overflow-y:hidden">x</div>';
    const el = document.getElementById('x')!;
    Object.defineProperty(el, 'scrollHeight', { value: 1000, configurable: true });
    Object.defineProperty(el, 'clientHeight', { value: 100, configurable: true });
    expect(isScrollable(el)).toBe(false);
  });

  test('returns false für overflow:visible trotz overflow', () => {
    document.body.innerHTML = '<div id="x">x</div>';
    const el = document.getElementById('x')!;
    Object.defineProperty(el, 'scrollHeight', { value: 1000, configurable: true });
    Object.defineProperty(el, 'clientHeight', { value: 100, configurable: true });
    // overflow:visible ist default
    expect(isScrollable(el)).toBe(false);
  });
});

// ---------------------------------------------------------------------------
// findScrollableAncestor
// ---------------------------------------------------------------------------

describe('findScrollableAncestor', () => {
  test('returns start-element wenn es selbst scrollable ist', () => {
    document.body.innerHTML = '<div id="x">x</div>';
    const el = document.getElementById('x')!;
    makeScrollable(el);
    expect(findScrollableAncestor(el)).toBe(el);
  });

  test('walks up bis zum scrollable ancestor', () => {
    document.body.innerHTML = `
      <div id="scroller">
        <div id="middle">
          <span id="leaf">x</span>
        </div>
      </div>
    `;
    const scroller = document.getElementById('scroller')!;
    const leaf = document.getElementById('leaf')!;
    makeScrollable(scroller);
    expect(findScrollableAncestor(leaf)).toBe(scroller);
  });

  test('returns scrollingElement wenn kein scrollable ancestor', () => {
    document.body.innerHTML = '<div id="x">x</div>';
    const el = document.getElementById('x')!;
    const result = findScrollableAncestor(el);
    // jsdom: documentElement ist nicht intrinsisch scrollable per jsdom-layout
    // fallback ist scrollingElement (= documentElement)
    expect(result === document.scrollingElement || result === document.documentElement).toBe(true);
  });

  test('respects DOM-order bei nested scrollers — innerer wins', () => {
    document.body.innerHTML = `
      <div id="outer">
        <div id="inner">
          <span id="leaf">x</span>
        </div>
      </div>
    `;
    const outer = document.getElementById('outer')!;
    const inner = document.getElementById('inner')!;
    const leaf = document.getElementById('leaf')!;
    makeScrollable(outer);
    makeScrollable(inner);
    expect(findScrollableAncestor(leaf)).toBe(inner);
  });

  test('handles orphan element (kein parent in document)', () => {
    const orphan = document.createElement('span');
    const result = findScrollableAncestor(orphan);
    expect(result === document.scrollingElement || result === document.documentElement).toBe(true);
  });
});

// ---------------------------------------------------------------------------
// forwardWheel
// ---------------------------------------------------------------------------

describe('forwardWheel', () => {
  test('scrollt den ancestor des under-cursor-element', () => {
    document.body.innerHTML = `
      <div id="scroller">
        <p id="target">click here</p>
      </div>
    `;
    const scroller = document.getElementById('scroller')!;
    const target = document.getElementById('target')!;
    makeScrollable(scroller);

    // mock: target ist unter cursor
    mockElementsAtPoint([target, scroller, document.body]);
    const scrollSpy = vi.fn();
    scroller.scrollBy = scrollSpy;

    const event = new WheelEvent('wheel', { clientX: 100, clientY: 50, deltaX: 0, deltaY: 50 });
    forwardWheel(event);

    expect(scrollSpy).toHaveBeenCalledWith({ left: 0, top: 50, behavior: 'auto' });
  });

  test('skipped overlay-elements via default predicate', () => {
    document.body.innerHTML = `
      <div id="page-scroller">
        <p id="page-target">page content</p>
      </div>
      <fp-overlay>
        <div id="overlay-element">overlay surface</div>
      </fp-overlay>
    `;
    const pageScroller = document.getElementById('page-scroller')!;
    const pageTarget = document.getElementById('page-target')!;
    const overlayEl = document.getElementById('overlay-element')!;
    makeScrollable(pageScroller);

    // mock: overlay-element ist topmost (über page-target)
    mockElementsAtPoint([overlayEl, pageTarget, pageScroller, document.body]);
    const pageScrollSpy = vi.fn();
    pageScroller.scrollBy = pageScrollSpy;

    const event = new WheelEvent('wheel', { clientX: 100, clientY: 50, deltaY: 30 });
    forwardWheel(event);

    // overlay was skipped, page-scroller wurde gescrollt
    expect(pageScrollSpy).toHaveBeenCalledWith({ left: 0, top: 30, behavior: 'auto' });
  });

  test('no-op wenn nichts unter cursor (außer overlay)', () => {
    document.body.innerHTML = `
      <fp-overlay>
        <div id="overlay-element">x</div>
      </fp-overlay>
    `;
    const overlayEl = document.getElementById('overlay-element')!;
    mockElementsAtPoint([overlayEl]);

    // shouldn't throw
    const event = new WheelEvent('wheel', { clientX: 0, clientY: 0, deltaY: 10 });
    expect(() => forwardWheel(event)).not.toThrow();
  });

  test('custom skipPredicate funktioniert', () => {
    document.body.innerHTML = `
      <div id="scroller">
        <p id="target">x</p>
      </div>
    `;
    const scroller = document.getElementById('scroller')!;
    const target = document.getElementById('target')!;
    makeScrollable(scroller);

    mockElementsAtPoint([target, scroller]);

    let calls = 0;
    const customSkip = (el: Element): boolean => {
      calls++;
      // skip p-tags
      return el.tagName === 'P';
    };

    const scrollSpy = vi.fn();
    scroller.scrollBy = scrollSpy;
    const event = new WheelEvent('wheel', { deltaY: 10 });
    forwardWheel(event, { skipPredicate: customSkip });

    // p (target) wurde skipped, scroller wird gefunden → walked-up
    expect(calls).toBeGreaterThan(0);
    expect(scrollSpy).toHaveBeenCalled();
  });
});
