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
  /** Tools — left panel (replaces ⚒). */
  wrench:
    '<path d="M14.7 6.3a1 1 0 0 0 0 1.4l1.6 1.6a1 1 0 0 0 1.4 0l3.77-3.77a6 6 0 0 1-7.94 7.94l-6.91 6.91a2.12 2.12 0 0 1-3-3l6.91-6.91a6 6 0 0 1 7.94-7.94l-3.76 3.76z"/>',
  /** Details — right panel (replaces ⓘ). */
  info: '<circle cx="12" cy="12" r="10"/><path d="M12 16v-4"/><path d="M12 8h.01"/>',
  /** Statistics — top panel (replaces ▤). */
  'bar-chart':
    '<line x1="12" x2="12" y1="20" y2="10"/><line x1="18" x2="18" y1="20" y2="4"/><line x1="6" x2="6" y1="20" y2="16"/>',
  /** Debug — bottom panel (replaces the "Debug" text label). */
  terminal: '<polyline points="4 17 10 11 4 5"/><line x1="12" x2="20" y1="19" y2="19"/>',
  /** Collapse/expand direction chevrons (replace ◀ ▶ ▲ ▼). */
  'chevron-left': '<path d="m15 18-6-6 6-6"/>',
  'chevron-right': '<path d="m9 18 6-6-6-6"/>',
  'chevron-up': '<path d="m18 15-6-6-6 6"/>',
  'chevron-down': '<path d="m6 9 6 6 6-6"/>',
} as const;

export type IconName = keyof typeof ICONS;
