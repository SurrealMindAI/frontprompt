/**
 * overlay-context.test.ts — the OverlayContext SSoT + factory.
 *
 * OverlayContext is the single source of truth for "where we are": the page
 * URL + the current backend session id, plus the ownership/origin helpers that
 * the overlay render gate and the visibility grouping consult.
 *
 * The bug this fixes (fix/overlay-context-gating): the old `sessionInfo` was
 * set ONCE at mount from the getState() seed envelope and never updated. When
 * that seed read was null/stale at mount, the gate degraded to render-all
 * forever — foreign-session picks rendered boxes. The context is instead
 * *reconstructable* and the live factory re-derives the session id on demand
 * from `window.__fp.getState()` (the only envelope that carries
 * `current_session_id`) and the URL from `window.location`.
 *
 * Test cases:
 *   1. pure constructor `overlayContextFrom` exposes url/sessionId + helpers
 *   2. hostname() derives lowercase hostname from the URL (null when no URL)
 *   3. isOwned() — owned true, foreign false, null-session degrades to true
 *   4. sameOrigin() compares hostnames
 *   5. the live factory derives sessionId from a stubbed getState() envelope
 *      and hostname from a stubbed window.location — and is reconstructable
 *      (a second derive after the stub changes reflects the NEW value, proving
 *      it is not a frozen mount snapshot)
 *
 * New cases:
 *   P1–P5. isAboutBlankFor() pure function
 *   G6–G8. overlayContext.isAboutBlank reactive getter via setForTests/resetForTests
 *   S9. SCHEMA_VERSION shared const equals '0.7.0'
 */
import { afterEach, beforeEach, describe, expect, test, vi } from 'vitest';
import { createOverlayContext, isAboutBlankFor, overlayContextFrom } from './overlay-context';
import { overlayContext } from './overlay-context.svelte';
import { SCHEMA_VERSION } from '../../schema-version';

describe('overlayContextFrom (pure reconstruction)', () => {
  test('1: exposes url + currentSessionId', () => {
    const ctx = overlayContextFrom({
      url: new URL('https://Example.com/path'),
      currentSessionId: 'sess-1',
    });
    expect(ctx.currentSessionId).toBe('sess-1');
    expect(ctx.url?.href).toBe('https://example.com/path');
  });

  test('2: hostname() is lowercase; null when no URL', () => {
    expect(
      overlayContextFrom({
        url: new URL('https://Example.COM/x'),
        currentSessionId: null,
      }).hostname()
    ).toBe('example.com');
    expect(overlayContextFrom({ url: null, currentSessionId: null }).hostname()).toBeNull();
  });

  test('3: isOwned() — owned true, foreign false, null-session degrades to true', () => {
    const ctx = overlayContextFrom({ url: null, currentSessionId: 'sess-1' });
    expect(ctx.isOwned({ origin_session: 'sess-1' })).toBe(true);
    expect(ctx.isOwned({ origin_session: 'sess-other' })).toBe(false);
    expect(ctx.isOwned({ origin_session: null })).toBe(false);

    const degraded = overlayContextFrom({ url: null, currentSessionId: null });
    expect(degraded.isOwned({ origin_session: 'sess-other' })).toBe(true);
  });

  test('4: sameOrigin() compares hostnames case-insensitively', () => {
    const ctx = overlayContextFrom({
      url: new URL('https://example.com/a'),
      currentSessionId: null,
    });
    expect(ctx.sameOrigin('https://Example.com/b')).toBe(true);
    expect(ctx.sameOrigin('https://other.com/b')).toBe(false);
    expect(ctx.sameOrigin(null)).toBe(false);
  });
});

describe('createOverlayContext (live main-world derive)', () => {
  const originalFp = window.__fp;

  beforeEach(() => {
    // jsdom default location is http://localhost/ — override hostname for the test.
    Object.defineProperty(window, 'location', {
      configurable: true,
      value: new URL('https://example.com/page'),
    });
  });

  afterEach(() => {
    window.__fp = originalFp;
    vi.restoreAllMocks();
  });

  test('5: derives sessionId from getState() envelope + hostname from window.location, and is reconstructable', async () => {
    // Stub the live main-world getState envelope. current_session_id lives at
    // the top-level wire envelope (alongside integrity_token), NOT inside the
    // StateSnapshot domain model.
    let sessionInEnvelope: string | null = 'sess-live-1';
    window.__fp = Object.assign(() => Promise.resolve(undefined), {
      dispatch: () => {},
      version: {
        schema_version: '0.7.0',
        bundle_build_session: 't',
        bundle_build_version: 't',
        bundle_build_git_sha: 't',
      },
      getState: () =>
        Promise.resolve({
          panel_state: {},
          current_session_id: sessionInEnvelope,
        } as unknown as Awaited<ReturnType<NonNullable<typeof window.__fp>['getState']>>),
    }) as NonNullable<typeof window.__fp>;

    const first = await createOverlayContext();
    expect(first.currentSessionId).toBe('sess-live-1');
    expect(first.hostname()).toBe('example.com');

    // Reconstructable: NOT a frozen mount snapshot. After the live envelope
    // changes, a fresh derive reflects the NEW value.
    sessionInEnvelope = 'sess-live-2';
    const second = await createOverlayContext();
    expect(second.currentSessionId).toBe('sess-live-2');
  });

  test('6: getState() returning null leaves currentSessionId null (degrade)', async () => {
    window.__fp = Object.assign(() => Promise.resolve(undefined), {
      dispatch: () => {},
      version: {
        schema_version: '0.7.0',
        bundle_build_session: 't',
        bundle_build_version: 't',
        bundle_build_git_sha: 't',
      },
      getState: () => Promise.resolve(null),
    }) as NonNullable<typeof window.__fp>;

    const ctx = await createOverlayContext();
    expect(ctx.currentSessionId).toBeNull();
    expect(ctx.hostname()).toBe('example.com');
  });
});

describe('isAboutBlankFor (pure function)', () => {
  test('P1: canonical about:blank returns true', () => {
    expect(isAboutBlankFor(new URL('about:blank'))).toBe(true);
  });

  test('P2: real https URL returns false', () => {
    expect(isAboutBlankFor(new URL('https://example.com'))).toBe(false);
  });

  test('P3: real URL with path returns false', () => {
    expect(isAboutBlankFor(new URL('https://example.com/page'))).toBe(false);
  });

  test('P4: other about: scheme returns false', () => {
    expect(isAboutBlankFor(new URL('about:newtab'))).toBe(false);
  });

  test('P5: null URL (degraded) returns false', () => {
    expect(isAboutBlankFor(null)).toBe(false);
  });
});

describe('overlayContext.isAboutBlank (reactive getter)', () => {
  afterEach(() => {
    overlayContext.resetForTests();
  });

  test('G6: getter is true when url is about:blank', () => {
    overlayContext.setForTests({ url: new URL('about:blank'), currentSessionId: null });
    expect(overlayContext.isAboutBlank).toBe(true);
  });

  test('G7: getter is false when url is a real URL', () => {
    overlayContext.setForTests({ url: new URL('https://example.com'), currentSessionId: 's1' });
    expect(overlayContext.isAboutBlank).toBe(false);
  });

  test('G8: getter is false on default degraded store (url null)', () => {
    overlayContext.resetForTests();
    expect(overlayContext.isAboutBlank).toBe(false);
  });
});

describe('SCHEMA_VERSION shared const', () => {
  test('S9: SCHEMA_VERSION equals the current Pydantic SSoT value 0.9.0', () => {
    expect(SCHEMA_VERSION).toBe('0.9.0');
  });
});
