<!--
  StatMetric — eine einzelne Number + Label, optional mit ratio-divider.

  Reusable building block für StatPill-content (Toolbar) und ggf. andere
  count-anzeigen. Macht das was inline-spans in Toolbar.svelte vorher
  vervielfacht haben.

  Beispiele:
    <StatMetric num={42} label="picks" />                    → "42 picks"
    <StatMetric num={7} secondaryNum={14} divider="/" label="el" />  → "7 / 14 el"
-->
<script lang="ts">
  import { formatCount } from '../../lib/utils/format';

  let {
    num,
    label,
    divider,
    secondaryNum,
  }: {
    /** Primary count to display. */
    num: number;
    /** Label-text after the number(s). */
    label: string;
    /**
     * Optional divider zwischen primary + secondary number (z.B. "/"). Beide
     * ``divider`` und ``secondaryNum`` müssen gesetzt sein um den ratio-mode
     * zu aktivieren.
     */
    divider?: string;
    secondaryNum?: number;
  } = $props();

  const hasRatio = $derived(divider !== undefined && secondaryNum !== undefined);
</script>

<span class="metric">
  <span class="metric__num">{formatCount(num)}</span>
  {#if hasRatio}
    <span class="metric__divider">{divider}</span>
    <span class="metric__num">{formatCount(secondaryNum ?? 0)}</span>
  {/if}
  <span class="metric__label">{label}</span>
</span>

<style>
  .metric {
    display: inline-flex;
    align-items: baseline;
    gap: 3px;
  }

  .metric__num {
    font-family: 'SF Mono', 'JetBrains Mono', Menlo, Consolas, monospace;
    font-size: 11px;
    color: var(--fp-color-text-primary);
    font-weight: 500;
  }

  .metric__label {
    color: var(--fp-color-text-muted);
    font-size: 9px;
    text-transform: lowercase;
  }

  .metric__divider {
    color: var(--fp-color-text-muted);
    font-size: 10px;
  }
</style>
