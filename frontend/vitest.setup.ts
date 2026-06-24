/**
 * Vitest global setup — runs before module evaluation in each test file.
 *
 * Bun 1.3.x + vitest 4.x + jsdom: ``MutationObserver`` is available in the
 * jsdom DOM, but the test runner evaluates module-level code (singletons like
 * ``export const positionService = new PositionService()``) before jsdom fully
 * exposes all globals. This shim makes ``MutationObserver`` available at module
 * eval time so the singleton constructor succeeds.
 *
 * Using the real jsdom ``MutationObserver`` where available, falling back to a
 * no-op stub — so real mutation-observer tests still work.
 */

if (typeof globalThis.MutationObserver === 'undefined') {
  globalThis.MutationObserver = class MockMutationObserver {
    private _callback: MutationCallback;
    constructor(callback: MutationCallback) {
      this._callback = callback;
    }
    observe(_target: Node, _options?: MutationObserverInit): void {}
    disconnect(): void {}
    takeRecords(): MutationRecord[] {
      return [];
    }
  } as unknown as typeof MutationObserver;
}
