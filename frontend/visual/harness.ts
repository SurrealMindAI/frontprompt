/**
 * Visual-regression harness entry.
 *
 * Mounts the REAL <fp-overlay> custom element with a deterministic, fully
 * offline stub of the Python bridge (window.__fp), so Playwright can screenshot
 * the actual overlay chrome rendered by the real components + design tokens —
 * no Python daemon, no Chromium-from-Python, no network.
 *
 * Contract reminder (see src/bridge/bridge.svelte.ts):
 *   - window.__fp is a callable (outbound send) with attached props.
 *   - getState() === null is the documented cold-boot path → the overlay
 *     renders its default state instead of hydrating a snapshot.
 */
import type { StateSnapshot } from '../src/_generated/state';

type FpStub = ((message: unknown) => Promise<unknown>) & {
  getState: () => Promise<StateSnapshot | null>;
};

const fp: FpStub = Object.assign(
  // Outbound: resolve every send to a no-op (no backend to answer).
  async (_message: unknown): Promise<unknown> => undefined,
  // Cold-boot: no snapshot to seed → overlay uses defaults.
  { getState: async (): Promise<StateSnapshot | null> => null }
);

(window as unknown as { __fp: FpStub }).__fp = fp;

// Importing the entry self-mounts the overlay (it runs mountOverlay() on load).
// window.__fp is already in place, so setupBridge() + the pre-mount getState()
// both see the stub.
await import('../src/main.ts');
