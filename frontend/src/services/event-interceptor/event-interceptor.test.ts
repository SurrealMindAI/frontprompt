/**
 * event-interceptor tests (vitest + jsdom).
 *
 * Was wird abgedeckt:
 *   - lifecycle: start()/stop() idempotent, listeners registriert/entfernt
 *   - FIFO cap (events array max 500)
 *   - composedPath-classification: in_fp_overlay, in_inspector_layer
 *   - isHudChrome helper
 *   - countsByType incrementiert auch wenn !enabled
 *   - elementsWithEvents excluded hud-chrome targets
 *   - toggle / clear behavior
 *
 * Hinweis: das interceptor-singleton lebt module-scoped. Wir nutzen
 * ``stop() + clear() + counters-reset`` pattern für test-isolation. Single
 * test-file daher safe.
 */
import { afterEach, beforeEach, describe, expect, test } from 'vitest';
import { eventInterceptor, isHudChrome, type InterceptedEvent } from './index';

beforeEach(() => {
  eventInterceptor.start();
  eventInterceptor.clear();
  // Reset enabled state explicitly (could be paused from prior test)
  if (!eventInterceptor.enabled) {
    eventInterceptor.toggle();
  }
  // Reset cross-test counters — singleton-state leaked sonst
  for (const k of Object.keys(eventInterceptor.countsByType)) {
    eventInterceptor.countsByType[k as keyof typeof eventInterceptor.countsByType] = 0;
  }
});

afterEach(() => {
  eventInterceptor.stop();
  eventInterceptor.clear();
  document.body.innerHTML = '';
});

// ---------------------------------------------------------------------------
// isHudChrome helper
// ---------------------------------------------------------------------------

describe('isHudChrome', () => {
  test('returns true für HUD-chrome (overlay aber nicht inspector-layer)', () => {
    const e = {
      in_fp_overlay: true,
      in_inspector_layer: false,
    } as InterceptedEvent;
    expect(isHudChrome(e)).toBe(true);
  });

  test('returns false für inspector-layer events (passthrough)', () => {
    const e = {
      in_fp_overlay: true,
      in_inspector_layer: true,
    } as InterceptedEvent;
    expect(isHudChrome(e)).toBe(false);
  });

  test('returns false für reine page-events', () => {
    const e = {
      in_fp_overlay: false,
      in_inspector_layer: false,
    } as InterceptedEvent;
    expect(isHudChrome(e)).toBe(false);
  });
});

// ---------------------------------------------------------------------------
// Lifecycle
// ---------------------------------------------------------------------------

describe('lifecycle', () => {
  test('start() ist idempotent (multiple calls = single install)', () => {
    // start() in beforeEach hat schon installed. Erneuter call sollte no-op sein.
    eventInterceptor.start();
    // Smoke: events feuern weiterhin (kein double-recording)
    document.body.innerHTML = '<button id="b">x</button>';
    const btn = document.getElementById('b')!;
    btn.click();
    expect(eventInterceptor.events.length).toBe(1);
  });

  test('stop() entfernt listeners — events feuern nicht mehr', () => {
    eventInterceptor.stop();
    document.body.innerHTML = '<button id="b">x</button>';
    const btn = document.getElementById('b')!;
    btn.click();
    expect(eventInterceptor.events.length).toBe(0);
  });

  test('clear() leert events aber behält countsByType', () => {
    document.body.innerHTML = '<button id="b">x</button>';
    const btn = document.getElementById('b')!;
    btn.click();
    btn.click();
    expect(eventInterceptor.events.length).toBe(2);
    expect(eventInterceptor.countsByType.click).toBe(2);

    eventInterceptor.clear();
    expect(eventInterceptor.events.length).toBe(0);
    expect(eventInterceptor.countsByType.click).toBe(2); // bleibt
  });

  test('toggle() pausiert recording aber countsByType läuft weiter', () => {
    document.body.innerHTML = '<button id="b">x</button>';
    const btn = document.getElementById('b')!;
    btn.click();
    const beforeCount = eventInterceptor.countsByType.click;

    eventInterceptor.toggle(); // enabled → false
    expect(eventInterceptor.enabled).toBe(false);

    btn.click();
    // events NICHT gepusht weil paused
    expect(eventInterceptor.events.length).toBe(1);
    // counts laufen WEITER (zählen alles)
    expect(eventInterceptor.countsByType.click).toBe(beforeCount + 1);
  });
});

// ---------------------------------------------------------------------------
// Event recording — classification
// ---------------------------------------------------------------------------

describe('event recording', () => {
  test('zeichnet click auf body als page-event auf (nicht hud-chrome)', () => {
    document.body.innerHTML = '<button id="b">x</button>';
    const btn = document.getElementById('b')!;
    btn.click();

    expect(eventInterceptor.events.length).toBe(1);
    const ev = eventInterceptor.events[0]!;
    expect(ev.type).toBe('click');
    expect(ev.target).toContain('button#b');
    expect(ev.in_fp_overlay).toBe(false);
    expect(ev.in_inspector_layer).toBe(false);
    expect(isHudChrome(ev)).toBe(false);
  });

  test('classifies element inside <fp-overlay> as in_fp_overlay', () => {
    document.body.innerHTML = `
      <fp-overlay>
        <button id="hud">x</button>
      </fp-overlay>
    `;
    const btn = document.getElementById('hud')!;
    btn.click();

    expect(eventInterceptor.events.length).toBe(1);
    const ev = eventInterceptor.events[0]!;
    expect(ev.in_fp_overlay).toBe(true);
    expect(ev.in_inspector_layer).toBe(false);
    expect(isHudChrome(ev)).toBe(true);
  });

  test('classifies element inside .inspector-layer as in_inspector_layer (NOT hud-chrome)', () => {
    document.body.innerHTML = `
      <fp-overlay>
        <div class="inspector-layer">
          <button id="passthrough">x</button>
        </div>
      </fp-overlay>
    `;
    const btn = document.getElementById('passthrough')!;
    btn.click();

    expect(eventInterceptor.events.length).toBe(1);
    const ev = eventInterceptor.events[0]!;
    expect(ev.in_fp_overlay).toBe(true);
    expect(ev.in_inspector_layer).toBe(true);
    // Wichtig: inspector-layer ist NICHT hud-chrome (= user-intent zur page)
    expect(isHudChrome(ev)).toBe(false);
  });

  test('countsByType incrementiert pro event-type', () => {
    document.body.innerHTML = '<input id="i" />';
    const input = document.getElementById('i') as HTMLInputElement;
    input.dispatchEvent(new KeyboardEvent('keydown', { key: 'a', bubbles: true }));
    input.dispatchEvent(new KeyboardEvent('keydown', { key: 'b', bubbles: true }));
    expect(eventInterceptor.countsByType.keydown).toBeGreaterThanOrEqual(2);
  });

  test('elementsWithEvents excluded HUD-chrome targets', () => {
    const beforeCount = eventInterceptor.elementsWithEvents;
    document.body.innerHTML = `
      <fp-overlay>
        <button id="hud">x</button>
      </fp-overlay>
    `;
    const btn = document.getElementById('hud')!;
    btn.click();

    // HUD-chrome click → counter sollte NICHT inkrementiert sein
    expect(eventInterceptor.elementsWithEvents).toBe(beforeCount);
  });

  test('elementsWithEvents INCLUDES inspector-layer events (page-intent)', () => {
    const beforeCount = eventInterceptor.elementsWithEvents;
    document.body.innerHTML = `
      <fp-overlay>
        <div class="inspector-layer">
          <button id="passthrough">x</button>
        </div>
      </fp-overlay>
    `;
    const btn = document.getElementById('passthrough')!;
    btn.click();

    // inspector-layer click → counter INKREMENTIERT (= user-intent zur page)
    expect(eventInterceptor.elementsWithEvents).toBeGreaterThan(beforeCount);
  });

  test('records wheel deltas', () => {
    document.body.innerHTML = '<div id="x">x</div>';
    const el = document.getElementById('x')!;
    el.dispatchEvent(new WheelEvent('wheel', { deltaX: 5, deltaY: 50, bubbles: true }));
    const wheelEvents = eventInterceptor.events.filter((e) => e.type === 'wheel');
    expect(wheelEvents.length).toBe(1);
    expect(wheelEvents[0]!.delta_x).toBe(5);
    expect(wheelEvents[0]!.delta_y).toBe(50);
  });

  test('records keydown key', () => {
    document.body.dispatchEvent(new KeyboardEvent('keydown', { key: 'Escape', bubbles: true }));
    const kd = eventInterceptor.events.filter((e) => e.type === 'keydown');
    expect(kd.length).toBe(1);
    expect(kd[0]!.key).toBe('Escape');
  });
});

// ---------------------------------------------------------------------------
// FIFO cap (large-volume burst)
// ---------------------------------------------------------------------------

describe('FIFO cap', () => {
  test('events array bleibt unter cap (500)', () => {
    // Burst 600 events. Cap muss greifen.
    for (let i = 0; i < 600; i++) {
      document.body.dispatchEvent(new KeyboardEvent('keydown', { key: `key-${i}`, bubbles: true }));
    }
    expect(eventInterceptor.events.length).toBeLessThanOrEqual(500);
    expect(eventInterceptor.events.length).toBeGreaterThan(400); // ungefähr cap
  });

  test('FIFO behavior — neuste events bleiben, älteste fliegen', () => {
    for (let i = 0; i < 510; i++) {
      document.body.dispatchEvent(new KeyboardEvent('keydown', { key: `key-${i}`, bubbles: true }));
    }
    // last event sollte key-509 sein
    const last = eventInterceptor.events[eventInterceptor.events.length - 1]!;
    expect(last.key).toBe('key-509');
    // first event sollte NICHT mehr key-0 sein
    const first = eventInterceptor.events[0]!;
    expect(first.key).not.toBe('key-0');
  });
});
