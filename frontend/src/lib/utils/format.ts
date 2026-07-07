/**
 * formatCount — short human-friendly Zahl-suffix-formatter.
 *
 * < 1_000           → as-is              (z.B. ``42``)
 * < 1_000_000       → ``X.XXk``           (z.B. ``1.23k``, ``999.99k``)
 * < 1_000_000_000   → ``X.XXM``           (z.B. ``1.23M``)
 * sonst             → ``X.XXG``           (z.B. ``1.23G``)
 *
 * 2 decimals exakt — kein trailing-trim für stabile column-width im UI.
 */
export function formatCount(n: number): string {
  if (n < 1_000) return String(n);
  if (n < 1_000_000) return `${(n / 1_000).toFixed(2)}k`;
  if (n < 1_000_000_000) return `${(n / 1_000_000).toFixed(2)}M`;
  return `${(n / 1_000_000_000).toFixed(2)}G`;
}

/**
 * formatTimestamp — human-readable wall-clock label for an epoch-ms timestamp.
 *
 * Renders ``"Jun 30, 21:47"``-style strings via the host locale/timezone
 * (``toLocaleString`` with ``undefined`` locale). Used to disambiguate
 * recordings that all share the default ``"New Recording"`` name — the start
 * time is the one stable distinguishing handle.
 *
 * Deterministic for a given input + environment; locale/TZ-dependent in shape
 * but never in stability.
 */
export function formatTimestamp(ms: number): string {
  return new Date(ms).toLocaleString(undefined, {
    month: 'short',
    day: 'numeric',
    hour: '2-digit',
    minute: '2-digit',
  });
}
