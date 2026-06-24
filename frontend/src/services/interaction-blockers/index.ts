/**
 * interaction-blockers — overlay-reachability diagnostics.
 *
 * Detects page-mechanisms blocking interaction with our overlay (inert
 * ancestors, aria-hidden, focus-theft). Opt-in via DEV-flag.
 *
 * See README.md im service-dir für detailed semantics + jeden signal's
 * background + UX-effekt.
 */
export { isDevModeEnabled } from './dev-flag';
export { startInteractionBlockersMonitor } from './monitor';
