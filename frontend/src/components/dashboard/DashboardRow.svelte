<!--
  DashboardRow — a key-value row for text/string values.

  Props:
    label: string — row label (left)
    value: string | number | null — display value (right, monospace)

  Use for: session ID, schema version, build SHA, build timestamp.
  Numeric *counts* use StatMetric instead — DashboardRow is for text-valued info rows.

  No interactivity. No clickable elements.
  Dashboard-scoped: not added to any global component index.

  All styles live in the <style> block (shadow DOM).
-->
<script lang="ts">
  let { label, value }: { label: string; value: string | number | null } = $props();

  const displayValue = $derived(value === null ? '—' : String(value));
</script>

<div class="row">
  <span class="row__label">{label}</span>
  <span class="row__value">{displayValue}</span>
</div>

<style>
  .row {
    display: flex;
    justify-content: space-between;
    align-items: baseline;
    gap: 16px;
    min-height: 30px;
    padding: 6px 0;
    border-top: 1px solid var(--fp-color-border-subtle);
  }

  .row:first-child {
    border-top: none;
  }

  .row__label {
    font-family: -apple-system, system-ui, sans-serif;
    font-size: 13px;
    color: var(--fp-color-text-secondary);
    flex-shrink: 0;
  }

  .row__value {
    font-family: 'SF Mono', 'JetBrains Mono', Menlo, Consolas, monospace;
    font-size: 13px;
    color: var(--fp-color-text-primary);
    text-align: right;
    word-break: break-all;
    font-variant-numeric: tabular-nums;
  }
</style>
