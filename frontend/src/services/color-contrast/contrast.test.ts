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
  it('covers hue sector 3 (h=150, [0,c,x])', () => {
    // hP = 150/60 = 2.5 → else if (hP < 3) [r1,g1,b1] = [0,c,x]
    const { r, g, b } = hslToRgb({ h: 150, s: 100, l: 50 });
    expect(Math.round(r)).toBe(0);
    expect(Math.round(g)).toBeGreaterThan(0);
    expect(Math.round(b)).toBeGreaterThan(0);
  });
  it('covers hue sector 4 (h=210, [0,x,c])', () => {
    // hP = 210/60 = 3.5 → else if (hP < 4) [r1,g1,b1] = [0,x,c]
    const { r, g, b } = hslToRgb({ h: 210, s: 100, l: 50 });
    expect(Math.round(r)).toBe(0);
    expect(Math.round(b)).toBeGreaterThan(Math.round(g));
  });
  it('covers hue sector 6 (h=330, [c,0,x])', () => {
    // hP = 330/60 = 5.5 → else [r1,g1,b1] = [c,0,x]
    const { r, g, b } = hslToRgb({ h: 330, s: 100, l: 50 });
    expect(Math.round(r)).toBeGreaterThan(0);
    expect(Math.round(g)).toBe(0);
    expect(Math.round(b)).toBeGreaterThan(0);
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
  it('parses #hex (6-char)', () => {
    expect(parseCssColorToRgb('#ff8000')).toEqual({ rgb: { r: 255, g: 128, b: 0 }, alpha: 1 });
  });
  it('parses #hex (3-char shorthand) — covers expand() h.length===1 branch', () => {
    // '#f80' → expand('f')=255, expand('8')=136, expand('0')=0
    const result = parseCssColorToRgb('#f80');
    expect(result).not.toBeNull();
    expect(result!.rgb.r).toBe(255);
    expect(result!.alpha).toBe(1);
  });
  it('parses #hex (4-char with alpha) — covers hex.length===4 ? expand(hex[3]) / 255 branch', () => {
    // '#ffff' → r=255,g=255,b=255, alpha=expand('f')/255=1
    const result = parseCssColorToRgb('#ffff');
    expect(result).not.toBeNull();
    expect(result!.rgb.r).toBe(255);
    expect(result!.alpha).toBeCloseTo(1, 2);
  });
  it('returns null for unrecognised string — covers final return null branch', () => {
    // '#ab' has hex.length=2 → neither 3/4 nor 6/8 → falls through to return null
    expect(parseCssColorToRgb('#ab')).toBeNull();
  });
  it('treats transparent as alpha 0', () => {
    expect(parseCssColorToRgb('transparent')?.alpha).toBe(0);
    expect(parseCssColorToRgb('')?.alpha).toBe(0);
  });
  it('returns null for malformed rgb() with fewer than 3 parts — covers line 63 return null', () => {
    // 'rgb(10, 20)' matches rgbMatch but parts.length=2 < 3 → return null at line 63
    expect(parseCssColorToRgb('rgb(10, 20)')).toBeNull();
  });
  it('parses hsl() string without alpha — covers lines 68-69 hsl path, alphaMatch=null → alpha:1', () => {
    // 'hsl(0, 100%, 50%)' → parseHsl succeeds → hsl path (line 66-70)
    // alphaMatch: regex checks for comma or slash before last number → no match → alpha=1
    const result = parseCssColorToRgb('hsl(0, 100%, 50%)');
    expect(result).not.toBeNull();
    expect(Math.round(result!.rgb.r)).toBe(255);
    expect(Math.round(result!.rgb.g)).toBe(0);
    expect(result!.alpha).toBe(1);
  });
  it('parses hsla() string with alpha — covers line 69 alphaMatch path → alpha parsed', () => {
    // 'hsla(0, 100%, 50%, 0.5)' → alphaMatch captures '0.5'
    const result = parseCssColorToRgb('hsla(0, 100%, 50%, 0.5)');
    expect(result).not.toBeNull();
    expect(result!.alpha).toBeCloseTo(0.5, 2);
  });
  it('rgb() with non-finite r triggers every() false path — covers line 59 FALSE branch', () => {
    // 'rgb(red, 0, 0)' → r=NaN (parseFloat fails), NaN is not finite → every() returns false
    // → falls through if-block → return null at line 63
    expect(parseCssColorToRgb('rgb(red, 0, 0)')).toBeNull();
  });
  it('rgba() with NaN alpha falls back to alpha:1 — covers line 60 false ternary branch', () => {
    // 'rgba(255, 0, 0, abc)' → r/g/b all finite → enters if(every) TRUE
    // alpha = parseFloat('abc') = NaN → Number.isFinite(NaN) FALSE → fallback to 1
    const result = parseCssColorToRgb('rgba(255, 0, 0, abc)');
    expect(result).not.toBeNull();
    expect(result!.rgb.r).toBe(255);
    expect(result!.alpha).toBe(1);
  });
  it('non-rgb non-hsl non-hex string returns null — covers line 72 false branch', () => {
    // 'red' does NOT start with '#', is not rgb/rgba, parseHsl fails → if(v.startsWith('#')) FALSE
    // → falls through to final return null
    expect(parseCssColorToRgb('red')).toBeNull();
  });
  it('8-char hex with alpha channel — covers line 84 TRUE branch (hex.length===8)', () => {
    // '#ff0000ff' → hex='ff0000ff', length=8 → enters if(6||8)
    // alpha = expand('ff') / 255 = 255 / 255 = 1
    const result = parseCssColorToRgb('#ff0000ff');
    expect(result).not.toBeNull();
    expect(result!.rgb.r).toBe(255);
    expect(result!.rgb.g).toBe(0);
    expect(result!.alpha).toBeCloseTo(1, 2);
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

  it('hits the break when target is unreachably high — covers l<=0||l>=100 break branch', () => {
    // grey (s=0) on a light background (bgLum=0.9), impossible target (ratio>21).
    // The loop darkens l toward 0; black on bgLum=0.9 gives at most ~19:1 < 22.
    // → l reaches 0, break is triggered, returns best candidate.
    const hsl = { h: 0, s: 0, l: 99 };
    const bgLum = 0.9;
    const out = adaptHslForContrast(hsl, bgLum, 22);
    // Should not throw, returns some candidate (l clamped at 0)
    expect(out.h).toBe(hsl.h);
    expect(out.s).toBe(hsl.s);
    expect(out.l).toBeLessThanOrEqual(hsl.l);
  });
});

describe('formatHsl', () => {
  it('round-trips through parseHsl', () => {
    expect(parseHsl(formatHsl({ h: 120, s: 78, l: 50 }))).toEqual({ h: 120, s: 78, l: 50 });
  });
});
