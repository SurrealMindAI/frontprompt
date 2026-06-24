import { afterEach, describe, expect, it } from 'vitest';

import { clearBackgroundCache, contrastingColor, effectiveBackgroundColor } from './background';
import { parseHsl } from './contrast';

afterEach(() => {
  document.body.innerHTML = '';
  document.body.removeAttribute('style');
  clearBackgroundCache();
});

describe('effectiveBackgroundColor', () => {
  it('returns the element own opaque background', () => {
    const el = document.createElement('div');
    el.style.backgroundColor = 'rgb(10, 20, 30)';
    document.body.appendChild(el);
    expect(effectiveBackgroundColor(el)).toEqual({ r: 10, g: 20, b: 30 });
  });

  it('walks up past transparent ancestors to the first opaque background', () => {
    const parent = document.createElement('div');
    parent.style.backgroundColor = 'rgb(5, 5, 5)';
    const child = document.createElement('div'); // no bg → transparent
    parent.appendChild(child);
    document.body.appendChild(parent);
    expect(effectiveBackgroundColor(child)).toEqual({ r: 5, g: 5, b: 5 });
  });

  it('falls back to white when no opaque background exists', () => {
    const el = document.createElement('div');
    document.body.appendChild(el);
    // body + html have no bg in jsdom default → white canvas
    expect(effectiveBackgroundColor(el)).toEqual({ r: 255, g: 255, b: 255 });
  });

  it('skips a mostly-transparent background and keeps walking', () => {
    const parent = document.createElement('div');
    parent.style.backgroundColor = 'rgb(200, 0, 0)';
    const child = document.createElement('div');
    child.style.backgroundColor = 'rgba(0, 0, 255, 0.2)'; // alpha < 0.5 → skipped
    parent.appendChild(child);
    document.body.appendChild(parent);
    expect(effectiveBackgroundColor(child)).toEqual({ r: 200, g: 0, b: 0 });
  });

  it('returns white for a null element', () => {
    expect(effectiveBackgroundColor(null)).toEqual({ r: 255, g: 255, b: 255 });
  });
});

describe('contrastingColor', () => {
  it('preserves hue while adapting against a dark element background', () => {
    const el = document.createElement('div');
    el.style.backgroundColor = 'rgb(0, 0, 0)';
    document.body.appendChild(el);
    const out = contrastingColor('hsl(240.0, 78%, 30%)', el); // dark blue on black
    const hsl = parseHsl(out);
    expect(hsl?.h).toBe(240); // hue preserved
    expect(hsl!.l).toBeGreaterThan(30); // lightened to contrast
  });

  it('returns the input unchanged when it is not an hsl string', () => {
    const el = document.createElement('div');
    expect(contrastingColor('rgb(1,2,3)', el)).toBe('rgb(1,2,3)');
  });
});
