/**
 * ColorPalette — 32-color rainbow palette, index → CSS color string.
 *
 * Designziel: jede Pick + Region kriegt eine eindeutige Farbe damit man auf
 * der Page mehrere markierte Elements / Regions visuell auseinanderhalten kann.
 * 32 Farben sind genug für realistische Annotation-Sessions (>32 picks bedeutet
 * eh dass die UI nicht mehr per-color-coding scaliert; dann wrappt der index
 * modulo 32 — Kollision akzeptiert, no warning-fanfare).
 *
 * Palette-Konstruktion: 32 distinct HSL-tuples mit
 *   - **Hue via 5-bit bit-reversal**: adjacente indices kriegen maximal weit
 *     entfernte hues (van-der-Corput-Reihe). idx 0 → hue 0°, idx 1 → hue 180°,
 *     idx 2 → hue 90°, etc. So sehen die ersten paar picks definitiv distinct
 *     aus statt langsam durchs Spektrum zu wandern.
 *   - **Lightness-Gruppen**: pro 8er-block ein anderer L-Wert (62 / 50 / 70 / 42).
 *     Bewusst kontrastreich gegen den dark-HUD-Background, alle gut lesbar.
 *   - **Konstante Saturation** 78% — kräftig genug für "Farbe ist Identität"-
 *     signaling, nicht so neon dass es ablenkt.
 *
 * Output-Format: ``hsl(...)`` CSS-string. SVG, CSS-vars, fill, stroke — alles
 * konsumiert das gleiche. Wer rgb-Tupel braucht kann später ``rgbForIndex``
 * ergänzen; aktuell ist kein consumer auf das angewiesen.
 *
 * Index-Semantik: ``int >= 0``. Wir modulo automatisch auf [0, 32) damit
 * Caller nicht selber wrappen müssen. Negative indices clampen auf 0.
 */

/** Anzahl distinkter Farben in der Palette. */
export const PALETTE_SIZE = 32;

/** Reverse the low 5 bits of `n` — produces van-der-Corput-like distribution. */
function bitReverse5(n: number): number {
  let r = 0;
  let x = n;
  for (let i = 0; i < 5; i++) {
    r = (r << 1) | (x & 1);
    x >>= 1;
  }
  return r;
}

/** L-Werte pro 8er-Gruppe — kontrastreich, hell-bis-dunkel cycling. */
const L_BY_GROUP: readonly number[] = [62, 50, 70, 42];

/**
 * Returns the CSS color string for the given index.
 *
 * Negative input → clamped to 0. Out-of-range positive → modulo PALETTE_SIZE.
 */
export function colorForIndex(idx: number): string {
  const normalized = ((Math.max(0, Math.trunc(idx)) % PALETTE_SIZE) + PALETTE_SIZE) % PALETTE_SIZE;
  const hueStep = bitReverse5(normalized);
  const hue = (hueStep * 360) / PALETTE_SIZE;
  const group = Math.floor(normalized / 8);
  /* v8 ignore next */
  const l = L_BY_GROUP[group] ?? 60;
  return `hsl(${hue.toFixed(1)}, 78%, ${l}%)`;
}

/** Eager array — useful für swatch-rendering im Debug-Panel. */
export const PALETTE: readonly string[] = Array.from({ length: PALETTE_SIZE }, (_, i) =>
  colorForIndex(i)
);

/**
 * Pick next color-index for a new entity, given its type's current list length.
 * Wraps modulo PALETTE_SIZE — 33rd pick re-uses index 0's color.
 */
export function nextColorIndex(currentCount: number): number {
  return ((currentCount % PALETTE_SIZE) + PALETTE_SIZE) % PALETTE_SIZE;
}
