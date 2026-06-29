/**
 * Icon registry — static, trusted inner-SVG markup for the {@link Icon} primitive.
 *
 * 24×24 viewBox, stroke-based (lucide-style) so icons stay crisp at any size and
 * inherit colour via `currentColor`. This replaces the Unicode glyph "icons"
 * (◉ ○ ✕ ▾ …) scattered through the controls, which render inconsistently across
 * operating systems and fonts and carry no semantic meaning.
 *
 * Add a new icon by appending a key here — the {@link IconName} union is derived
 * from the keys, so every call site stays type-checked. Keep entries to plain
 * `<path>`/`<circle>`/… markup with no `stroke`/`fill` attributes (the Icon
 * component supplies those), and no scripting or external refs.
 */
export const ICONS = {
  /** Visibility on — a clear "shown" affordance (replaces ◉). */
  eye: '<path d="M2 12s3.5-7 10-7 10 7 10 7-3.5 7-10 7-10-7-10-7Z"/><circle cx="12" cy="12" r="3"/>',
  /** Visibility off — crossed eye (replaces ○). */
  'eye-off':
    '<path d="M10.7 5.1A10.7 10.7 0 0 1 21.9 11.7a1 1 0 0 1 0 .7 10.7 10.7 0 0 1-1.4 2.5"/><path d="M14.1 14.2a3 3 0 0 1-4.2-4.3"/><path d="M17.5 17.5A10.8 10.8 0 0 1 2 12.3a1 1 0 0 1 0-.7 10.8 10.8 0 0 1 4.4-5.1"/><path d="m2 2 20 20"/>',
} as const;

export type IconName = keyof typeof ICONS;
