/**
 * QuickCommentMode store tests — enter/exit lifecycle, pending-input
 * open/commit/cancel, and the live commented-counter.
 *
 * The store is a $state singleton; each test resets it via exit() + a fresh
 * enter() where needed so cases don't leak state into each other.
 */
import { describe, expect, test, beforeEach } from 'vitest';
import { quickCommentMode } from './quick-comment-mode.svelte';

beforeEach(() => {
  // Hard reset to a known-off state between tests.
  quickCommentMode.exit();
  quickCommentMode.commentedCount = 0;
});

describe('QuickCommentMode enter/exit', () => {
  test('starts inactive with no pending and a zero counter', () => {
    expect(quickCommentMode.active).toBe(false);
    expect(quickCommentMode.pending).toBeNull();
    expect(quickCommentMode.commentedCount).toBe(0);
  });

  test('enter() activates the mode and resets pending + counter', () => {
    quickCommentMode.commentedCount = 5;
    quickCommentMode.pending = { pickId: 'stale', rect: null };

    quickCommentMode.enter();

    expect(quickCommentMode.active).toBe(true);
    expect(quickCommentMode.pending).toBeNull();
    expect(quickCommentMode.commentedCount).toBe(0);
  });

  test('exit() deactivates and clears pending', () => {
    quickCommentMode.enter();
    quickCommentMode.openInput('p1', null);

    quickCommentMode.exit();

    expect(quickCommentMode.active).toBe(false);
    expect(quickCommentMode.pending).toBeNull();
  });

  test('exit() leaves the counter intact (a session summary survives until re-enter)', () => {
    quickCommentMode.enter();
    quickCommentMode.openInput('p1', null);
    quickCommentMode.commitInput(true);

    quickCommentMode.exit();

    expect(quickCommentMode.commentedCount).toBe(1);
  });
});

describe('QuickCommentMode pending input', () => {
  test('openInput() sets the pending pick + rect when active', () => {
    quickCommentMode.enter();
    const rect = { x: 10, y: 20, width: 100, height: 40 };

    quickCommentMode.openInput('pick-42', rect);

    expect(quickCommentMode.pending).toEqual({ pickId: 'pick-42', rect });
  });

  test('openInput() accepts a null rect (fallback to hovering box)', () => {
    quickCommentMode.enter();

    quickCommentMode.openInput('pick-7', null);

    expect(quickCommentMode.pending).toEqual({ pickId: 'pick-7', rect: null });
  });

  test('openInput() is a no-op when the mode is inactive', () => {
    // never entered
    quickCommentMode.openInput('pick-1', null);

    expect(quickCommentMode.pending).toBeNull();
  });
});

describe('QuickCommentMode commit / cancel', () => {
  test('commitInput(true) bumps the counter and clears pending', () => {
    quickCommentMode.enter();
    quickCommentMode.openInput('p1', null);

    quickCommentMode.commitInput(true);

    expect(quickCommentMode.commentedCount).toBe(1);
    expect(quickCommentMode.pending).toBeNull();
  });

  test('commitInput(false) clears pending without bumping the counter', () => {
    quickCommentMode.enter();
    quickCommentMode.openInput('p1', null);

    quickCommentMode.commitInput(false);

    expect(quickCommentMode.commentedCount).toBe(0);
    expect(quickCommentMode.pending).toBeNull();
  });

  test('multiple commits accumulate the counter across the rapid loop', () => {
    quickCommentMode.enter();

    quickCommentMode.openInput('p1', null);
    quickCommentMode.commitInput(true);
    quickCommentMode.openInput('p2', null);
    quickCommentMode.commitInput(true);
    quickCommentMode.openInput('p3', null);
    quickCommentMode.commitInput(false); // empty — no bump

    expect(quickCommentMode.commentedCount).toBe(2);
    expect(quickCommentMode.pending).toBeNull();
  });

  test('cancelInput() clears pending and never touches the counter', () => {
    quickCommentMode.enter();
    quickCommentMode.openInput('p1', null);

    quickCommentMode.cancelInput();

    expect(quickCommentMode.pending).toBeNull();
    expect(quickCommentMode.commentedCount).toBe(0);
  });
});
