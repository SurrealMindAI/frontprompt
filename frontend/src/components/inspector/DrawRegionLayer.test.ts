/**
 * DrawRegionLayer smoke tests.
 *
 * Tests: hint text when no origin, preview rect when draft.rect is set,
 * pointer-down sets origin, ESC key cancels draft.
 */
import { describe, expect, test, afterEach, beforeEach, vi } from 'vitest';
import { render, cleanup, fireEvent } from '@testing-library/svelte';
import DrawRegionLayer from './DrawRegionLayer.svelte';
import { regionDraft } from '../../services/regions';
import { keyboard } from '../../services/keyboard/keyboard.svelte';

afterEach(() => {
  cleanup();
  regionDraft.cancel();
  // Reset keyboard subscriptions so ESC handlers from this test don't leak.
  keyboard._reset();
});

beforeEach(() => {
  regionDraft.cancel();
});

describe('DrawRegionLayer — hint text', () => {
  test('shows hint text when no origin', () => {
    regionDraft.start();
    const { getByText } = render(DrawRegionLayer);
    expect(getByText(/Drag to mark a region/)).toBeTruthy();
  });

  test('renders the .draw-region-layer div', () => {
    regionDraft.start();
    const { container } = render(DrawRegionLayer);
    expect(container.querySelector('.draw-region-layer')).not.toBeNull();
  });

  test('does not show preview rect when draft.rect is null', () => {
    regionDraft.start();
    const { container } = render(DrawRegionLayer);
    expect(container.querySelector('.draw-region-preview')).toBeNull();
  });
});

describe('DrawRegionLayer — pointer events', () => {
  test('pointerdown with left button sets origin on regionDraft', () => {
    regionDraft.start();
    const { container } = render(DrawRegionLayer);
    const layer = container.querySelector('.draw-region-layer') as HTMLElement;
    fireEvent.pointerDown(layer, { button: 0, clientX: 50, clientY: 80, pointerId: 1 });
    expect(regionDraft.origin).not.toBeNull();
  });

  test('pointerdown with right button (button=2) is ignored', () => {
    regionDraft.start();
    const { container } = render(DrawRegionLayer);
    const layer = container.querySelector('.draw-region-layer') as HTMLElement;
    fireEvent.pointerDown(layer, { button: 2, clientX: 50, clientY: 80, pointerId: 1 });
    // origin stays null for right clicks
    expect(regionDraft.origin).toBeNull();
  });

  test('pointermove updates rect when origin is set', () => {
    regionDraft.start();
    const { container } = render(DrawRegionLayer);
    const layer = container.querySelector('.draw-region-layer') as HTMLElement;
    fireEvent.pointerDown(layer, { button: 0, clientX: 10, clientY: 10, pointerId: 1 });
    fireEvent.pointerMove(layer, { clientX: 60, clientY: 90, pointerId: 1 });
    expect(regionDraft.rect).not.toBeNull();
  });

  test('pointerup calls commit() (cancels draft on DOM-less commit)', () => {
    regionDraft.start();
    const { container } = render(DrawRegionLayer);
    const layer = container.querySelector('.draw-region-layer') as HTMLElement;
    fireEvent.pointerDown(layer, { button: 0, clientX: 10, clientY: 10, pointerId: 1 });
    // commit() calls scanRegion which needs DOM picks — in jsdom it returns 0 picks
    // but it should not throw
    expect(() => {
      fireEvent.pointerUp(layer, { clientX: 60, clientY: 90, pointerId: 1 });
    }).not.toThrow();
  });
});

describe('DrawRegionLayer — wheel and keyboard', () => {
  test('wheel event on layer forwards to scroll-router (covers onWheel branch)', () => {
    // forwardWheel() calls document.elementsFromPoint — mock it so jsdom doesn't throw.
    Object.defineProperty(document, 'elementsFromPoint', {
      value: vi.fn().mockReturnValue([]),
      configurable: true,
      writable: true,
    });
    regionDraft.start();
    const { container } = render(DrawRegionLayer);
    const layer = container.querySelector('.draw-region-layer') as HTMLElement;
    expect(() => fireEvent.wheel(layer, { deltaX: 5, deltaY: 10 })).not.toThrow();
  });

  test('Escape key cancels an active draft (covers keyboard ESC subscription)', () => {
    regionDraft.start();
    regionDraft.setOrigin(10, 10);
    expect(regionDraft.origin).not.toBeNull();
    render(DrawRegionLayer);
    // The $effect registers keyboard.subscribe('Escape', ...).
    // Firing a keydown event on window triggers the callback → regionDraft.cancel().
    fireEvent.keyDown(window, { key: 'Escape' });
    expect(regionDraft.origin).toBeNull();
    expect(regionDraft.drafting).toBe(false);
  });
});

describe('DrawRegionLayer — preview rect', () => {
  test('shows preview rect after origin+current are set', () => {
    regionDraft.start();
    regionDraft.setOrigin(10, 10);
    regionDraft.updateCurrent(60, 90);
    const { container } = render(DrawRegionLayer);
    expect(container.querySelector('.draw-region-preview')).not.toBeNull();
  });

  test('preview rect has correct position style', () => {
    regionDraft.start();
    regionDraft.setOrigin(10, 10);
    regionDraft.updateCurrent(110, 210);
    const { container } = render(DrawRegionLayer);
    const preview = container.querySelector('.draw-region-preview') as HTMLElement;
    expect(preview?.style.left).toBe('10px');
    expect(preview?.style.top).toBe('10px');
  });
});
