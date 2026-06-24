/**
 * Animation tokens — single source für dash-flow, pulse, glow + color-per-kind.
 *
 * Werden als CSS-vars im svg-renderer-block gesetzt; CSS-rules referenzieren sie
 * via ``var(--rel-…)``. So bleibt das Tempo zentral änderbar, ohne dass eine
 * mögliche Phase-3-Canvas-Impl ihre eigenen magic-numbers hätte: sie würde
 * dieselben tokens als JS-Konstanten lesen.
 */
import type { RelationKind } from '../../_generated/state';

/** CSS-var-Namen — single source der referenz-strings (z.B. für tests). */
export const TOKEN = {
  dashPeriod: '--rel-dash-period',
  pulsePeriod: '--rel-pulse-period',
  glowBlur: '--rel-glow-blur',
  glowOpacity: '--rel-glow-opacity',
  glowWidth: '--rel-glow-width',
  strokeWidth: '--rel-stroke-width',
  colorRelatesTo: '--rel-color-relates-to',
  colorTriggers: '--rel-color-triggers',
  colorPartOf: '--rel-color-part-of',
  colorHover: '--rel-color-hover',
} as const;

/** Default-Werte für die CSS-vars. Werden auf dem RelationsLayer-host gesetzt. */
export const DEFAULTS: Record<string, string> = {
  [TOKEN.dashPeriod]: '1s',
  [TOKEN.pulsePeriod]: '2s',
  [TOKEN.glowBlur]: '3px',
  [TOKEN.glowOpacity]: '0.3',
  [TOKEN.glowWidth]: '6px',
  [TOKEN.strokeWidth]: '2px',
  // SurrealMind-cyberpunk palette — cyan/magenta/teal accents
  [TOKEN.colorRelatesTo]: '#78dcff', // soft cyan (symmetric, neutral)
  [TOKEN.colorTriggers]: '#ff6dd1', // magenta (action, directed)
  [TOKEN.colorPartOf]: '#9dffb1', // mint green (containment, directed)
  [TOKEN.colorHover]: '#ffffff', // white glow on hover
};

/** Map RelationKind → CSS-var-name für color-lookup. */
export function colorVarFor(kind: RelationKind): string {
  switch (kind) {
    case 'relates_to':
      return `var(${TOKEN.colorRelatesTo})`;
    case 'triggers':
      return `var(${TOKEN.colorTriggers})`;
    case 'part_of':
      return `var(${TOKEN.colorPartOf})`;
    default: {
      // Exhaustiveness check — falls Phase 2 einen neuen kind hinzufügt ohne case.
      const _exhaustive: never = kind;
      void _exhaustive;
      return `var(${TOKEN.colorRelatesTo})`;
    }
  }
}

/** Set defaults inline-style auf einem host-element. */
export function applyTokenDefaults(el: HTMLElement | SVGElement): void {
  for (const [name, value] of Object.entries(DEFAULTS)) {
    el.style.setProperty(name, value);
  }
}
