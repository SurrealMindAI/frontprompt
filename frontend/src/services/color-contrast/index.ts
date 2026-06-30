/**
 * color-contrast — dynamic, background-aware marker colouring.
 *
 * The overlay must always stand out from the page behind it. Markers keep their
 * palette HUE (color_index identity) but have their LIGHTNESS flipped toward
 * white/black until they reach a WCAG contrast ratio against the sampled
 * background. See contrast.ts (pure math) + background.ts (DOM sampling).
 */

export { contrastingColor } from './background';
