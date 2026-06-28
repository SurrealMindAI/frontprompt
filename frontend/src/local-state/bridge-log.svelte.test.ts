/**
 * BridgeLog — interceptor tests.
 *
 * BridgeLog registers an interceptor with the Bridge and buffers all events
 * up to MAX_EVENTS (FIFO-drop). Tests use vi.hoisted to capture the
 * interceptor callback so we can fire events without a real Bridge.
 */

const capturedInterceptors = vi.hoisted(() => [] as Array<(e: unknown) => void>);

vi.mock('../bridge/bridge.svelte', () => ({
  bridge: {
    addInterceptor: (fn: (e: unknown) => void) => {
      capturedInterceptors.push(fn);
      // Return unsubscribe noop (matches real Bridge.addInterceptor API).
      return () => {
        const idx = capturedInterceptors.indexOf(fn);
        if (idx !== -1) capturedInterceptors.splice(idx, 1);
      };
    },
  },
}));

import { describe, expect, test, vi, beforeEach } from 'vitest';
import { BridgeLog, MAX_EVENTS } from './bridge-log.svelte';
import type { BridgeEvent } from '../bridge/bridge.svelte';

function makeEvent(direction: BridgeEvent['direction'], kind = 'test_msg'): BridgeEvent {
  return { seq: 0, timestamp_ms: Date.now(), direction, kind, payload: null };
}

// Feed an event to all registered interceptors (simulates bridge firing)
function fireEvent(e: BridgeEvent): void {
  for (const fn of capturedInterceptors) {
    fn(e);
  }
}

beforeEach(() => {
  capturedInterceptors.length = 0;
});

// ---------------------------------------------------------------------------
// initial state + interceptor registration
// ---------------------------------------------------------------------------

describe('BridgeLog initial state', () => {
  test('events list starts empty', () => {
    const log = new BridgeLog();
    expect(log.events).toHaveLength(0);
    // ensure the constructor registered an interceptor
    expect(capturedInterceptors).toHaveLength(1);
  });

  test('countByDirection starts at all zeros', () => {
    const log = new BridgeLog();
    expect(log.countByDirection.outbound).toBe(0);
    expect(log.countByDirection.inbound).toBe(0);
    expect(log.countByDirection.error).toBe(0);
  });
});

// ---------------------------------------------------------------------------
// event buffering
// ---------------------------------------------------------------------------

describe('BridgeLog event buffering', () => {
  test('appends events from bridge interceptor', () => {
    const log = new BridgeLog();
    fireEvent(makeEvent('outbound'));
    expect(log.events).toHaveLength(1);
  });

  test('buffers multiple events in order', () => {
    const log = new BridgeLog();
    fireEvent(makeEvent('outbound', 'msg_1'));
    fireEvent(makeEvent('inbound', 'msg_2'));
    fireEvent(makeEvent('error', 'msg_3'));
    expect(log.events).toHaveLength(3);
    expect(log.events[0]!.direction).toBe('outbound');
    expect(log.events[1]!.direction).toBe('inbound');
    expect(log.events[2]!.direction).toBe('error');
  });

  test('FIFO-drops oldest events when exceeding MAX_EVENTS cap', () => {
    const log = new BridgeLog();
    for (let i = 0; i < MAX_EVENTS + 5; i++) {
      fireEvent(makeEvent('outbound', `msg_${i}`));
    }
    expect(log.events).toHaveLength(MAX_EVENTS);
  });
});

// ---------------------------------------------------------------------------
// clear
// ---------------------------------------------------------------------------

describe('BridgeLog.clear', () => {
  test('empties events list', () => {
    const log = new BridgeLog();
    fireEvent(makeEvent('outbound'));
    fireEvent(makeEvent('inbound'));
    log.clear();
    expect(log.events).toHaveLength(0);
  });

  test('clear resets countByDirection to zeros', () => {
    const log = new BridgeLog();
    fireEvent(makeEvent('outbound'));
    log.clear();
    expect(log.countByDirection.outbound).toBe(0);
  });
});

// ---------------------------------------------------------------------------
// countByDirection derived
// ---------------------------------------------------------------------------

describe('BridgeLog.countByDirection', () => {
  test('counts outbound events', () => {
    const log = new BridgeLog();
    fireEvent(makeEvent('outbound'));
    fireEvent(makeEvent('outbound'));
    expect(log.countByDirection.outbound).toBe(2);
  });

  test('counts inbound events', () => {
    const log = new BridgeLog();
    fireEvent(makeEvent('inbound'));
    expect(log.countByDirection.inbound).toBe(1);
  });

  test('counts error events', () => {
    const log = new BridgeLog();
    fireEvent(makeEvent('error'));
    expect(log.countByDirection.error).toBe(1);
  });

  test('counts all three directions independently', () => {
    const log = new BridgeLog();
    fireEvent(makeEvent('outbound'));
    fireEvent(makeEvent('outbound'));
    fireEvent(makeEvent('inbound'));
    fireEvent(makeEvent('error'));
    fireEvent(makeEvent('error'));
    fireEvent(makeEvent('error'));
    expect(log.countByDirection.outbound).toBe(2);
    expect(log.countByDirection.inbound).toBe(1);
    expect(log.countByDirection.error).toBe(3);
  });
});

// ---------------------------------------------------------------------------
// MAX_EVENTS constant
// ---------------------------------------------------------------------------

describe('MAX_EVENTS', () => {
  test('MAX_EVENTS is 200', () => {
    expect(MAX_EVENTS).toBe(200);
  });
});
