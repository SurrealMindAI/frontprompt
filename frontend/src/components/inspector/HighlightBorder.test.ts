/**
 * HighlightBorder smoke tests.
 *
 * Simple display component that wraps a rect with a fixed-position border.
 * Tests: renders with correct position/size CSS vars, renders without element prop.
 */
import { describe, expect, test, afterEach } from 'vitest';
import { render, cleanup } from '@testing-library/svelte';
import HighlightBorder from './HighlightBorder.svelte';

afterEach(() => cleanup());

describe('HighlightBorder — rendering', () => {
  test('renders .highlight-border div', () => {
    const { container } = render(HighlightBorder, {
      rect: { x: 10, y: 20, width: 100, height: 50 },
    });
    expect(container.querySelector('.highlight-border')).not.toBeNull();
  });

  test('applies left CSS var from rect.x', () => {
    const { container } = render(HighlightBorder, {
      rect: { x: 15, y: 25, width: 80, height: 40 },
    });
    const el = container.querySelector('.highlight-border') as HTMLElement;
    expect(el.style.left).toBe('15px');
  });

  test('applies top CSS var from rect.y', () => {
    const { container } = render(HighlightBorder, {
      rect: { x: 15, y: 25, width: 80, height: 40 },
    });
    const el = container.querySelector('.highlight-border') as HTMLElement;
    expect(el.style.top).toBe('25px');
  });

  test('applies width from rect.width', () => {
    const { container } = render(HighlightBorder, {
      rect: { x: 0, y: 0, width: 120, height: 60 },
    });
    const el = container.querySelector('.highlight-border') as HTMLElement;
    expect(el.style.width).toBe('120px');
  });

  test('applies height from rect.height', () => {
    const { container } = render(HighlightBorder, {
      rect: { x: 0, y: 0, width: 120, height: 60 },
    });
    const el = container.querySelector('.highlight-border') as HTMLElement;
    expect(el.style.height).toBe('60px');
  });

  test('renders without element prop (default null)', () => {
    const { container } = render(HighlightBorder, {
      rect: { x: 0, y: 0, width: 50, height: 50 },
    });
    expect(container.querySelector('.highlight-border')).not.toBeNull();
  });

  test('renders with a real DOM element passed as element prop', () => {
    const el = document.createElement('div');
    document.body.appendChild(el);
    const { container } = render(HighlightBorder, {
      rect: { x: 5, y: 5, width: 200, height: 100 },
      element: el,
    });
    expect(container.querySelector('.highlight-border')).not.toBeNull();
    document.body.removeChild(el);
  });
});
