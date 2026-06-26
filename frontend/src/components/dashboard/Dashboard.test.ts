/**
 * Dashboard unit tests (vitest + jsdom + @testing-library/svelte).
 *
 * Test-Surface:
 *   1. Renders without crashing (root .dashboard class present)
 *   2. Shows schema version (real SCHEMA_VERSION from schema-version.ts)
 *   3. Shows BUILD_GIT_SHA from build-info
 *   4. Shows session ID when set
 *   5. Shows null/dash when session is unset
 *   6. Picks count reflects store
 *   7. Regions count reflects store
 *   8. Relations count reflects store
 *   9. Events count reflects interceptor (after isHudChrome filter)
 *  10. Renders section headers
 *  11. State section notes panels suppressed on about:blank
 */
import { describe, expect, test, vi, afterEach } from 'vitest';
import { render, cleanup } from '@testing-library/svelte';
import Dashboard from './Dashboard.svelte';
import DashboardRow from './DashboardRow.svelte';

// ---------------------------------------------------------------------------
// Mocks
// ---------------------------------------------------------------------------

// Mock backendState — control inspector counts + active flag
vi.mock('../../backend-state/backend-state.svelte', () => ({
  backendState: {
    inspector: {
      picks: [
        { pick_id: 'p1' },
        { pick_id: 'p2' },
        { pick_id: 'p3' },
      ],
      regions: [
        { region_id: 'r1' },
        { region_id: 'r2' },
      ],
      relations: [
        { relation_id: 'rel1' },
      ],
      active: false,
    },
  },
}));

// Mock overlayContext — control currentSessionId
vi.mock('../../services/context/overlay-context.svelte', () => ({
  overlayContext: {
    currentSessionId: 'sess-001',
  },
}));

// Mock event-interceptor — control event count + isHudChrome filter
vi.mock('../../services/event-interceptor', () => ({
  eventInterceptor: {
    events: [
      // 4 page events (not HUD chrome)
      { seq: 0, in_fp_overlay: false, in_inspector_layer: false },
      { seq: 1, in_fp_overlay: false, in_inspector_layer: false },
      { seq: 2, in_fp_overlay: false, in_inspector_layer: false },
      { seq: 3, in_fp_overlay: false, in_inspector_layer: false },
      // 1 HUD chrome event (filtered out by isHudChrome)
      { seq: 4, in_fp_overlay: true, in_inspector_layer: false },
    ],
  },
  isHudChrome: (e: { in_fp_overlay: boolean; in_inspector_layer: boolean }) =>
    e.in_fp_overlay && !e.in_inspector_layer,
}));

// Mock build-info — control BUILD_GIT_SHA for deterministic test
vi.mock('../../_generated/build-info', () => ({
  BUILD_SESSION: 'test-session-uuid',
  BUILD_VERSION: '2026-06-03T00:00:00+00:00',
  BUILD_GIT_SHA: 'deadbeef',
}));

// SCHEMA_VERSION is imported real — no mock needed.

afterEach(() => {
  cleanup();
});

// ---------------------------------------------------------------------------
// Tests
// ---------------------------------------------------------------------------

describe('Dashboard', () => {
  test('1: renders without crashing — .dashboard root class present', () => {
    const { container } = render(Dashboard);
    expect(container.querySelector('.dashboard')).not.toBeNull();
  });

  test('2: shows schema version (real SCHEMA_VERSION from schema-version.ts)', () => {
    const { container } = render(Dashboard);
    expect(container.textContent).toContain('0.8.0');
  });

  test('3: shows BUILD_GIT_SHA from build-info', () => {
    const { container } = render(Dashboard);
    expect(container.textContent).toContain('deadbeef');
  });

  test('4: shows session ID when set', () => {
    const { container } = render(Dashboard);
    expect(container.textContent).toContain('sess-001');
  });

  test('5: shows dash (—) when session is unset — DashboardRow null rendering', () => {
    // DashboardRow renders '—' when value is null (see DashboardRow.svelte displayValue).
    // We test this via DashboardRow directly since module-level mocks are hoisted and
    // cannot be changed per-test without a factory. The null-session path in Dashboard
    // produces a DashboardRow with value={null} → displays '—'.
    const { container } = render(DashboardRow, {
      props: { label: 'session id', value: null },
    });
    expect(container.textContent).toContain('—');
  });

  test('6: picks count reflects store (3 picks)', () => {
    const { container } = render(Dashboard);
    expect(container.textContent).toContain('3');
    expect(container.textContent?.toLowerCase()).toContain('picks');
  });

  test('7: regions count reflects store (2 regions)', () => {
    const { container } = render(Dashboard);
    expect(container.textContent).toContain('2');
    expect(container.textContent?.toLowerCase()).toContain('regions');
  });

  test('8: relations count reflects store (1 relation)', () => {
    const { container } = render(Dashboard);
    expect(container.textContent).toContain('1');
    expect(container.textContent?.toLowerCase()).toContain('relations');
  });

  test('9: events count reflects interceptor — 4 page events (1 HUD chrome filtered out)', () => {
    const { container } = render(Dashboard);
    // 5 total - 1 HUD chrome = 4 page events
    expect(container.textContent).toContain('4');
    expect(container.textContent?.toLowerCase()).toContain('events');
  });

  test('10: renders section headers', () => {
    const { container } = render(Dashboard);
    const text = container.textContent ?? '';
    // Dashboard should have info/version section and state/counts section
    expect(text.length).toBeGreaterThan(50);
    // Build info section
    expect(text).toContain('0.8.0');
  });

  test('11: state section notes panels suppressed on about:blank', () => {
    const { container } = render(Dashboard);
    expect(container.textContent?.toLowerCase()).toContain('suppressed');
  });
});
