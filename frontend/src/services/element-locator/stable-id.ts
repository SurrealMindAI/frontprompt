/**
 * isStableId — true wenn die id stabile-genug ist um in Selektoren zu landen.
 *
 * Frameworks generieren oft volatile IDs (React Server Components `_R_N1_`,
 * Vue's `v-XXX`, Svelte's `svelte-XXX`, Aria's `aria-radio-XX`). Diese als
 * Selector-Anker zu nutzen wäre brittle — die ID ändert sich on re-render.
 *
 * Policy: alles unter 40 chars, nicht numerisch-only, nicht von bekannten
 * Framework-prefixes. Pattern wird in Tests gepflegt — bei neuen Frameworks
 * Pattern hier erweitern.
 *
 * @example
 *   isStableId('hero-cta') === true
 *   isStableId('react-_R_1_') === false
 *   isStableId('123') === false
 *   isStableId('aria-radio-7') === false
 */
const VOLATILE_PREFIXES = /^(react-|v-|__|svelte-|ember\d+|aria-|tippy-|popper-|_R_|_S_)/;
const NUMERIC_ONLY = /^\d+$/;
const MAX_LENGTH = 40;

export function isStableId(id: string | null | undefined): boolean {
  if (!id) return false;
  if (id.length > MAX_LENGTH) return false;
  if (NUMERIC_ONLY.test(id)) return false;
  if (VOLATILE_PREFIXES.test(id)) return false;
  return true;
}
