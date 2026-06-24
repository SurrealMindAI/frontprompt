/**
 * Tests for Bridge integrity-token validation.
 *
 * window.__fp.dispatch must validate a per-session integrity token
 * before accepting `state_snapshot` envelopes. Forged or missing tokens must
 * be rejected; the correct token must pass through.
 *
 * Security rationale: page JS running inside the Playwright-controlled browser
 * can call window.__fp.dispatch with a crafted state_snapshot. Without a token
 * check, the overlay's backendState mirror could be corrupted by hostile page
 * scripts. The token is generated once at Python startup (secrets.token_hex(32))
 * and delivered via the initial getState() seed — it is never derivable from
 * page JS alone.
 *
 * Test cases:
 *   1. Forged snapshot without token is rejected (module token set)
 *   2. Forged snapshot with wrong token is rejected
 *   3. Correct token passes through — handler invoked
 *   4. No token configured → dispatch accepts all snapshots (no enforcement)
 *   5. Non-snapshot messages are never token-checked (heartbeat passes)
 */

import { afterEach, describe, expect, test, vi } from 'vitest';
import { bridge, setupBridge } from './bridge.svelte';

// ---------------------------------------------------------------------------
// Test helpers
// ---------------------------------------------------------------------------

/** Minimal mock for window.__fp — satisfies the guard in setupBridge(). */
function installMockFp(): void {
  const fp = Object.assign(
    (_msg: unknown): Promise<unknown> => Promise.resolve(null),
    {}
  ) as typeof window.__fp;
  // setupBridge checks for fp existence; our mock is enough
  (window as Window & { __fp?: unknown }).__fp = fp;
}

function removeMockFp(): void {
  delete (window as Window & { __fp?: unknown }).__fp;
}

// ---------------------------------------------------------------------------
// Tests
// ---------------------------------------------------------------------------

describe('bridge integrity-token validation', () => {
  afterEach(() => {
    bridge.resetForTests();
    removeMockFp();
  });

  test('1: forged snapshot without integrity_token is rejected when session token is set', () => {
    installMockFp();
    setupBridge('0.6.0', 'abc123');

    const handler = vi.fn();
    bridge.on('state_snapshot', handler);

    // No integrity_token field on this payload
    window.__fp!.dispatch({
      kind: 'state_snapshot',
      schema_version: '0.6.0',
      snapshot: {},
    });

    expect(handler).not.toHaveBeenCalled();
  });

  test('2: snapshot with wrong token is rejected', () => {
    installMockFp();
    setupBridge('0.6.0', 'abc123');

    const handler = vi.fn();
    bridge.on('state_snapshot', handler);

    window.__fp!.dispatch({
      kind: 'state_snapshot',
      schema_version: '0.6.0',
      snapshot: {},
      integrity_token: 'wrong-token',
    });

    expect(handler).not.toHaveBeenCalled();
  });

  test('3: snapshot with correct token passes through — handler invoked', () => {
    installMockFp();
    setupBridge('0.6.0', 'abc123');

    const handler = vi.fn();
    bridge.on('state_snapshot', handler);

    window.__fp!.dispatch({
      kind: 'state_snapshot',
      schema_version: '0.6.0',
      snapshot: {},
      integrity_token: 'abc123',
    });

    expect(handler).toHaveBeenCalledOnce();
  });

  test('4: no token configured — dispatch accepts all snapshots (no enforcement)', () => {
    installMockFp();
    // Pass null for token → no enforcement
    setupBridge('0.6.0', null);

    const handler = vi.fn();
    bridge.on('state_snapshot', handler);

    window.__fp!.dispatch({
      kind: 'state_snapshot',
      schema_version: '0.6.0',
      snapshot: {},
      // no integrity_token
    });

    expect(handler).toHaveBeenCalledOnce();
  });

  test('5: non-snapshot messages are never token-checked (heartbeat passes)', () => {
    installMockFp();
    setupBridge('0.6.0', 'abc123');

    const handler = vi.fn();
    bridge.on('heartbeat', handler);

    window.__fp!.dispatch({
      kind: 'heartbeat',
      schema_version: '0.6.0',
      seq: 1,
      server_send_time_ns: 0,
      // no integrity_token — but it doesn't matter for heartbeat
    });

    expect(handler).toHaveBeenCalledOnce();
  });

  test('rejected snapshot emits integrity_token_mismatch error event', () => {
    installMockFp();
    setupBridge('0.6.0', 'abc123');

    const errorEvents: unknown[] = [];
    bridge.addInterceptor((event) => {
      if (event.direction === 'error') {
        errorEvents.push(event);
      }
    });

    window.__fp!.dispatch({
      kind: 'state_snapshot',
      schema_version: '0.6.0',
      snapshot: {},
      // missing integrity_token
    });

    expect(errorEvents.length).toBe(1);
    const errorEvent = errorEvents[0] as { kind: string };
    expect(errorEvent.kind).toBe('integrity_token_mismatch');
  });
});
