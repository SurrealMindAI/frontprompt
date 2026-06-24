import { describe, expect, it } from 'vitest';

import {
  adaptHslForContrast,
  contrastRatio,
  formatHsl,
  hslToRgb,
  parseCssColorToRgb,
  parseHsl,
  relativeLuminance,
} from './contrast';

describe('parseHsl', () => {
  it('parses a palette-style hsl string', () => {
    expect(parseHsl('hsl(45.0, 78%, 62%)')).toEqual({ h: 45, s: 78, l: 62 });
  });
  it('parses hsla', () => {
    expect(parseHsl('hsla(200, 50%, 40%, 0.5)')).toEqual({ h: 200, s: 50, l: 40 });
  });
  it('returns null for non-hsl', () => {
    expect(parseHsl('rgb(1,2,3)')).toBeNull();
  });
});

describe('hslToRgb', () => {
  it('maps primary red', () => {
    const { r, g, b } = hslToRgb({ h: 0, s: 100, l: 50 });
    expect([Math.round(r), Math.round(g), Math.round(b)]).toEqual([255, 0, 0]);
  });
  it('maps white and black via lightness', () => {
    expect(Math.round(hslToRgb({ h: 0, s: 0, l: 100 }).r)).toBe(255);
    expect(Math.round(hslToRgb({ h: 0, s: 0, l: 0 }).r)).toBe(0);
  });
});

describe('relativeLuminance', () => {
  it('is 1 for white, 0 for black', () => {
    expect(relativeLuminance({ r: 255, g: 255, b: 255 })).toBeCloseTo(1, 5);
    expect(relativeLuminance({ r: 0, g: 0, b: 0 })).toBeCloseTo(0, 5);
  });
});

describe('contrastRatio', () => {
  it('is 21 for black vs white', () => {
    expect(contrastRatio(0, 1)).toBeCloseTo(21, 5);
  });
  it('is 1 for identical luminances', () => {
    expect(contrastRatio(0.5, 0.5)).toBeCloseTo(1, 5);
  });
});

describe('parseCssColorToRgb', () => {
  it('parses rgb()', () => {
    expect(parseCssColorToRgb('rgb(10, 20, 30)')).toEqual({
      rgb: { r: 10, g: 20, b: 30 },
      alpha: 1,
    });
  });
  it('parses rgba() with alpha', () => {
    expect(parseCssColorToRgb('rgba(10, 20, 30, 0.4)')).toEqual({
      rgb: { r: 10, g: 20, b: 30 },
      alpha: 0.4,
    });
  });
  it('parses modern space/slash rgb syntax', () => {
    expect(parseCssColorToRgb('rgb(10 20 30 / 0.5)')).toEqual({
      rgb: { r: 10, g: 20, b: 30 },
      alpha: 0.5,
    });
  });
  it('parses #hex', () => {
    expect(parseCssColorToRgb('#ff8000')).toEqual({ rgb: { r: 255, g: 128, b: 0 }, alpha: 1 });
  });
  it('treats transparent as alpha 0', () => {
    expect(parseCssColorToRgb('transparent')?.alpha).toBe(0);
    expect(parseCssColorToRgb('')?.alpha).toBe(0);
  });
});

describe('adaptHslForContrast', () => {
  const target = 3;

  it('leaves a colour unchanged when it already meets the target', () => {
    // bright yellow on black already exceeds 3:1
    const hsl = { h: 60, s: 100, l: 50 };
    expect(adaptHslForContrast(hsl, 0, target)).toEqual(hsl);
  });

  it('lightens a dark colour on a dark background until it contrasts', () => {
    const hsl = { h: 240, s: 78, l: 30 }; // dark blue
    const bgLum = 0.02; // near-black bg
    const out = adaptHslForContrast(hsl, bgLum, target);
    expect(out.h).toBe(hsl.h); // hue preserved
    expect(out.s).toBe(hsl.s); // saturation preserved
    expect(out.l).toBeGreaterThan(hsl.l); // pushed lighter
    expect(contrastRatio(relativeLuminance(hslToRgb(out)), bgLum)).toBeGreaterThanOrEqual(target);
  });

  it('darkens a light colour on a light background until it contrasts', () => {
    const hsl = { h: 50, s: 78, l: 75 }; // light yellow
    const bgLum = relativeLuminance({ r: 255, g: 255, b: 255 }); // white bg
    const out = adaptHslForContrast(hsl, bgLum, target);
    expect(out.h).toBe(hsl.h);
    expect(out.l).toBeLessThan(hsl.l); // pushed darker
    expect(contrastRatio(relativeLuminance(hslToRgb(out)), bgLum)).toBeGreaterThanOrEqual(target);
  });
});

describe('formatHsl', () => {
  it('round-trips through parseHsl', () => {
    expect(parseHsl(formatHsl({ h: 120, s: 78, l: 50 }))).toEqual({ h: 120, s: 78, l: 50 });
  });
});
