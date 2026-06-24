/**
 * color-palette barrel — 32 distinkte Farben, index → CSS-string.
 * Konsumiert von svg-renderer (rect-borders), PickItem/RegionItem (color-dots).
 */
export { PALETTE, PALETTE_SIZE, colorForIndex, nextColorIndex } from './color-palette';
