/**
 * keyboard service unit tests (vitest + jsdom).
 */
import { afterEach, describe, expect, test, vi } from 'vitest';
import { keyboard } from './keyboard.svelte';

afterEach(() => {
  keyboard._reset();
});

function dispatchKey(key: string): void {
  const e = new KeyboardEvent('keydown', { key, bubbles: true, cancelable: true });
  window.dispatchEvent(e);
}

describe('keyboard.subscribe', () => {
  test('fires registered handler on matching key', () => {
    const handler = vi.fn();
    keyboard.subscribe('Escape', handler);
    dispatchKey('Escape');
    expect(handler).toHaveBeenCalledTimes(1);
  });

  test('does not fire for unrelated key', () => {
    const handler = vi.fn();
    keyboard.subscribe('Escape', handler);
    dispatchKey('Enter');
    expect(handler).not.toHaveBeenCalled();
  });

  test('multiple subscribers on same key all fire', () => {
    const a = vi.fn();
    const b = vi.fn();
    keyboard.subscribe('Escape', a);
    keyboard.subscribe('Escape', b);
    dispatchKey('Escape');
    expect(a).toHaveBeenCalledTimes(1);
    expect(b).toHaveBeenCalledTimes(1);
  });

  test('unsubscribe stops firing for that handler', () => {
    const handler = vi.fn();
    const unsub = keyboard.subscribe('Escape', handler);
    dispatchKey('Escape');
    unsub();
    dispatchKey('Escape');
    expect(handler).toHaveBeenCalledTimes(1);
  });

  test('unsubscribe of one does not affect siblings', () => {
    const a = vi.fn();
    const b = vi.fn();
    const unsubA = keyboard.subscribe('Escape', a);
    keyboard.subscribe('Escape', b);
    unsubA();
    dispatchKey('Escape');
    expect(a).not.toHaveBeenCalled();
    expect(b).toHaveBeenCalledTimes(1);
  });

  test('subscribing same handler twice is idempotent (Set-semantics)', () => {
    const handler = vi.fn();
    keyboard.subscribe('Escape', handler);
    keyboard.subscribe('Escape', handler);
    dispatchKey('Escape');
    expect(handler).toHaveBeenCalledTimes(1);
  });

  test('handler that throws does not block other handlers', () => {
    const thrower = vi.fn(() => {
      throw new Error('boom');
    });
    const good = vi.fn();
    // eslint-disable-next-line @typescript-eslint/no-empty-function
    const consoleSpy = vi.spyOn(console, 'error').mockImplementation(() => {});
    keyboard.subscribe('Escape', thrower);
    keyboard.subscribe('Escape', good);
    dispatchKey('Escape');
    expect(thrower).toHaveBeenCalledTimes(1);
    expect(good).toHaveBeenCalledTimes(1);
    consoleSpy.mockRestore();
  });
});
