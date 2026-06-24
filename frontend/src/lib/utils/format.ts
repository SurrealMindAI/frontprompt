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
