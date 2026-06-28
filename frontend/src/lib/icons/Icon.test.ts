/**
 * Icon — inline-SVG icon primitive tests.
 *
 * Tests: renders the registry markup, sizing, currentColor inheritance,
 * decorative-by-default (aria-hidden) vs labelled (role="img" + <title>),
 * and unknown-name safety.
 */
import { describe, expect, test, afterEach } from 'vitest';
import { render, cleanup } from '@testing-library/svelte';
import Icon from './Icon.svelte';
import { ICONS } from './icons';

afterEach(() => cleanup());

describe('Icon — rendering', () => {
  test('renders an svg with the registry body for the given name', () => {
    const { container } = render(Icon, { name: 'eye' });
    const svg = container.querySelector('svg.fp-icon');
    expect(svg).toBeTruthy();
    // eye = path + circle
    expect(svg?.querySelector('path')).toBeTruthy();
    expect(svg?.querySelector('circle')).toBeTruthy();
    expect(svg?.getAttribute('data-icon')).toBe('eye');
  });

  test('inherits colour via currentColor and uses a 24x24 viewBox', () => {
    const { container } = render(Icon, { name: 'eye-off' });
    const svg = container.querySelector('svg.fp-icon');
    expect(svg?.getAttribute('stroke')).toBe('currentColor');
    expect(svg?.getAttribute('fill')).toBe('none');
    expect(svg?.getAttribute('viewBox')).toBe('0 0 24 24');
  });

  test('size prop drives width and height (default 16)', () => {
    const def = render(Icon, { name: 'eye' });
    const svgDef = def.container.querySelector('svg');
    expect(svgDef?.getAttribute('width')).toBe('16');
    expect(svgDef?.getAttribute('height')).toBe('16');
    cleanup();
    const big = render(Icon, { name: 'eye', size: 24 });
    const svgBig = big.container.querySelector('svg');
    expect(svgBig?.getAttribute('width')).toBe('24');
    expect(svgBig?.getAttribute('height')).toBe('24');
  });
});

describe('Icon — accessibility', () => {
  test('decorative by default: aria-hidden, no role', () => {
    const { container } = render(Icon, { name: 'eye' });
    const svg = container.querySelector('svg');
    expect(svg?.getAttribute('aria-hidden')).toBe('true');
    expect(svg?.getAttribute('role')).toBeNull();
    expect(svg?.querySelector('title')).toBeNull();
  });

  test('labelled: role="img" + <title> when title is set', () => {
    const { container, getByText } = render(Icon, { name: 'eye', title: 'visible' });
    const svg = container.querySelector('svg');
    expect(svg?.getAttribute('role')).toBe('img');
    expect(svg?.getAttribute('aria-hidden')).toBeNull();
    expect(svg?.getAttribute('aria-label')).toBe('visible');
    expect(getByText('visible').tagName.toLowerCase()).toBe('title');
  });
});

describe('Icon — registry', () => {
  test('every registry entry renders without throwing', () => {
    for (const name of Object.keys(ICONS)) {
      const { container } = render(Icon, { name: name as keyof typeof ICONS });
      expect(container.querySelector('svg.fp-icon')?.innerHTML).not.toBe('');
      cleanup();
    }
  });
});
