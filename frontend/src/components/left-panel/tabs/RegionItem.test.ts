/**
 * RegionItem drift-indicator tests (vitest + jsdom + @testing-library/svelte).
 *
 * Test-Surface:
 *   - Layout-drift badge (⚠ drift) appears when viewport_snapshot deviates
 *     from current document dimensions by more than the default threshold.
 *   - Badge absent when viewport_snapshot is null.
 */
import { describe, expect, test, vi, afterEach } from 'vitest';
import { render, cleanup } from '@testing-library/svelte';
import RegionItem from './RegionItem.svelte';
import type { Region, Viewport } from '../../../_generated/state';

afterEach(() => {
  cleanup();
  vi.restoreAllMocks();
});

function makeViewport(documentW: number, documentH: number): Viewport {
  return {
    scroll_x: 0,
    scroll_y: 0,
    viewport_w: 1920,
    viewport_h: 1080,
    document_w: documentW,
    document_h: documentH,
  };
}

function makeRegion(overrides: Partial<Region> = {}): Region {
  return {
    region_id: 'r-test-0001',
    rect: { x: 0, y: 0, width: 100, height: 50 },
    member_pick_ids: [],
    timestamp_ms: 0,
    color_index: 0,
    viewport_snapshot: null,
    ...overrides,
  };
}

describe('RegionItem — null fallback branches', () => {
  test('region with null member_pick_ids shows count 0 (covers ?.length ?? 0 null branch)', () => {
    const region = makeRegion({ member_pick_ids: null as any });
    const { container } = render(RegionItem, { props: { region } });
    const count = container.querySelector('.region-item__count');
    expect(count).not.toBeNull();
    expect(count!.textContent).toBe('0');
  });

  test('region with null color_index uses fallback 0 (covers color_index ?? 0 null branch)', () => {
    const region = makeRegion({ color_index: null as any });
    // Should render without throwing — colorForIndex(0) is the fallback
    const { container } = render(RegionItem, { props: { region } });
    expect(container.querySelector('.region-item__icon')).not.toBeNull();
  });

  test('region with non-empty note uses note as display name (covers note?.trim() truthy branch)', () => {
    // region.note?.trim() returns truthy → displayName = region.note
    const region = makeRegion({ note: 'My Region Note' } as any);
    const { getByText } = render(RegionItem, { props: { region } });
    expect(getByText('My Region Note')).toBeTruthy();
  });
});

describe('RegionItem drift indicator', () => {
  test('shows drift badge when document dimensions differ significantly from snapshot', () => {
    // Mock document.documentElement.scrollWidth/Height to simulate layout drift
    Object.defineProperty(document.documentElement, 'scrollWidth', {
      value: 1366,
      configurable: true,
    });
    Object.defineProperty(document.documentElement, 'scrollHeight', {
      value: 800,
      configurable: true,
    });

    const region = makeRegion({
      viewport_snapshot: makeViewport(1920, 1080),
    });

    const { container } = render(RegionItem, { props: { region } });
    const driftBadge = container.querySelector('.region-item__drift');
    expect(driftBadge).not.toBeNull();
    // The badge text contains "drift"
    expect(driftBadge!.textContent).toMatch(/drift/i);
  });

  test('does not show drift badge when viewport_snapshot is null', () => {
    const region = makeRegion({ viewport_snapshot: null });
    const { container } = render(RegionItem, { props: { region } });
    const driftBadge = container.querySelector('.region-item__drift');
    expect(driftBadge).toBeNull();
  });

  test('does not show drift badge when deviation is within threshold', () => {
    // Deviation of 10px — under default threshold of 50px
    Object.defineProperty(document.documentElement, 'scrollWidth', {
      value: 1910,
      configurable: true,
    });
    Object.defineProperty(document.documentElement, 'scrollHeight', {
      value: 1070,
      configurable: true,
    });

    const region = makeRegion({
      viewport_snapshot: makeViewport(1920, 1080),
    });

    const { container } = render(RegionItem, { props: { region } });
    const driftBadge = container.querySelector('.region-item__drift');
    expect(driftBadge).toBeNull();
  });
});
