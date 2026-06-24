/**
 * DEV-flag check für developer-side diagnostic-features.
 *
 * Aktivation aus DevTools console (per-origin, persistent):
 *
 *   localStorage.setItem('fp-dev', '1');
 *   location.reload();
 *
 * Deaktivation:
 *
 *   localStorage.removeItem('fp-dev');
 *   location.reload();
 *
 * Default: OFF. Diagnostic-features sind opt-in weil sie console-noise + leichte
 * perf-overhead generieren, ohne dem regulären user etwas zu bringen.
 *
 * Safe-fallback: wenn localStorage nicht verfügbar (cross-origin frames,
 * private-mode hardening), returnt ``false``. Diagnostic-features bleiben dann
 * aus. Catched ``DOMException`` (SecurityError, QuotaExceededError, etc.).
 */
const DEV_FLAG_KEY = 'fp-dev';

export function isDevModeEnabled(): boolean {
  try {
    return localStorage.getItem(DEV_FLAG_KEY) === '1';
  } catch {
    return false;
  }
}
