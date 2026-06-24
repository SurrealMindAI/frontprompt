/**
 * Pure color-contrast math — no DOM. HSL parsing, WCAG relative luminance,
 * contrast ratio, and lightness-adaptation that preserves hue + saturation.
 *
 * The overlay must always stand out from whatever page content sits behind a
 * marker (task: "dynamisch färben"). We keep a marker's HUE stable (so the
 * 32-colour palette identity per color_index is recognisable across the
 * session) and only push its LIGHTNESS toward white or black until a minimum
 * contrast ratio against the sampled background is reached.
 */

export interface Rgb {
  r: number;
  g: number;
  b: number;
}

export interface Hsl {
  h: number;
  s: number;
  l: number;
}

/** WCAG AA contrast for graphical/UI objects (non-text) — the marker-border target. */
export const DEFAULT_TARGET_RATIO = 3;

const _clamp = (v: number, lo: number, hi: number): number => Math.min(hi, Math.max(lo, v));

/** Parse ``hsl(45.0, 78%, 62%)`` / ``hsla(…)`` → {h,s,l}. Returns null on no-match. */
export function parseHsl(value: string): Hsl | null {
  const m = value.match(/hsla?\(\s*([\d.]+)\s*,\s*([\d.]+)%\s*,\s*([\d.]+)%/i);
  if (!m) return null;
  return { h: parseFloat(m[1]!), s: parseFloat(m[2]!), l: parseFloat(m[3]!) };
}

/** Format {h,s,l} back to a palette-style HSL string. */
export function formatHsl(hsl: Hsl): string {
  return `hsl(${hsl.h.toFixed(1)}, ${Math.round(hsl.s)}%, ${Math.round(hsl.l)}%)`;
}

/**
 * Parse a computed CSS colour to RGB + alpha. Handles ``rgb()``/``rgba()``
 * (comma OR space/slash syntax), ``hsl()``/``hsla()``, ``#hex`` (3/6/8), and
 * the keywords ``transparent`` / ``none``. Returns null if unparseable.
 */
export function parseCssColorToRgb(value: string): { rgb: Rgb; alpha: number } | null {
  const v = value.trim().toLowerCase();
  if (v === '' || v === 'transparent' || v === 'none')
    return { rgb: { r: 0, g: 0, b: 0 }, alpha: 0 };

  const rgbMatch = v.match(/rgba?\(([^)]+)\)/);
  if (rgbMatch) {
    const parts = rgbMatch[1]!.split(/[\s,/]+/).filter(Boolean);
    if (parts.length >= 3) {
      const r = parseFloat(parts[0]!);
      const g = parseFloat(parts[1]!);
      const b = parseFloat(parts[2]!);
      const alpha = parts.length >= 4 ? parseFloat(parts[3]!) : 1;
      if ([r, g, b].every((n) => Number.isFinite(n))) {
        return { rgb: { r, g, b }, alpha: Number.isFinite(alpha) ? alpha : 1 };
      }
    }
    return null;
  }

  const hsl = parseHsl(v);
  if (hsl) {
    const alphaMatch = v.match(/hsla?\([^)]*[,/]\s*([\d.]+)\s*\)/);
    return { rgb: hslToRgb(hsl), alpha: alphaMatch ? parseFloat(alphaMatch[1]!) : 1 };
  }

  if (v.startsWith('#')) {
    const hex = v.slice(1);
    const expand = (h: string): number => parseInt(h.length === 1 ? h + h : h, 16);
    if (hex.length === 3 || hex.length === 4) {
      return {
        rgb: { r: expand(hex[0]!), g: expand(hex[1]!), b: expand(hex[2]!) },
        alpha: hex.length === 4 ? expand(hex[3]!) / 255 : 1,
      };
    }
    if (hex.length === 6 || hex.length === 8) {
      return {
        rgb: { r: expand(hex.slice(0, 2)), g: expand(hex.slice(2, 4)), b: expand(hex.slice(4, 6)) },
        alpha: hex.length === 8 ? expand(hex.slice(6, 8)) / 255 : 1,
      };
    }
  }
  return null;
}

/** HSL (h 0–360, s/l 0–100) → RGB (0–255). */
export function hslToRgb({ h, s, l }: Hsl): Rgb {
  const sN = s / 100;
  const lN = l / 100;
  const c = (1 - Math.abs(2 * lN - 1)) * sN;
  const hP = (((h % 360) + 360) % 360) / 60;
  const x = c * (1 - Math.abs((hP % 2) - 1));
  let r1 = 0;
  let g1 = 0;
  let b1 = 0;
  if (hP < 1) [r1, g1, b1] = [c, x, 0];
  else if (hP < 2) [r1, g1, b1] = [x, c, 0];
  else if (hP < 3) [r1, g1, b1] = [0, c, x];
  else if (hP < 4) [r1, g1, b1] = [0, x, c];
  else if (hP < 5) [r1, g1, b1] = [x, 0, c];
  else [r1, g1, b1] = [c, 0, x];
  const m = lN - c / 2;
  return { r: (r1 + m) * 255, g: (g1 + m) * 255, b: (b1 + m) * 255 };
}

/** WCAG relative luminance of an sRGB colour (0 = black, 1 = white). */
export function relativeLuminance({ r, g, b }: Rgb): number {
  const lin = (c: number): number => {
    const cs = c / 255;
    return cs <= 0.03928 ? cs / 12.92 : ((cs + 0.055) / 1.055) ** 2.4;
  };
  return 0.2126 * lin(r) + 0.7152 * lin(g) + 0.0722 * lin(b);
}

/** WCAG contrast ratio between two relative luminances (1–21). */
export function contrastRatio(lumA: number, lumB: number): number {
  const lighter = Math.max(lumA, lumB);
  const darker = Math.min(lumA, lumB);
  return (lighter + 0.05) / (darker + 0.05);
}

/**
 * Push a colour's lightness toward white (on dark backgrounds) or black (on
 * light backgrounds) until it reaches ``target`` contrast against ``bgLum``,
 * preserving hue + saturation. If the target is unreachable (extreme bg) the
 * maximally-contrasting lightness in that direction is returned.
 */
export function adaptHslForContrast(
  hsl: Hsl,
  bgLum: number,
  target: number = DEFAULT_TARGET_RATIO
): Hsl {
  if (contrastRatio(relativeLuminance(hslToRgb(hsl)), bgLum) >= target) return hsl;

  const step = bgLum < 0.5 ? 2 : -2; // dark bg → lighten; light bg → darken
  let l = hsl.l;
  let candidate = hsl;
  for (let i = 0; i < 60; i++) {
    l = _clamp(l + step, 0, 100);
    candidate = { ...hsl, l };
    if (contrastRatio(relativeLuminance(hslToRgb(candidate)), bgLum) >= target) return candidate;
    if (l <= 0 || l >= 100) break;
  }
  return candidate;
}
