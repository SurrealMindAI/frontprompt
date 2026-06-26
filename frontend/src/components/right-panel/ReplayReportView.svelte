<!--
  ReplayReportView — renders a ReplayReport with per-step pass/fail.

  Props:
    report — the ReplayReport to display (typed from generated TS types)

  Collapsed by default; expandable via toggle (localState — ADR-018: ephemeral UI preference).
  When collapsed only the status badge + step count summary is shown.
  When expanded each ReplayStepResult renders as a row.

  Assertion steps:
  - assertion_passed=true → green badge (.assertion-pass)
  - assertion_passed=false → red badge + assertion_actual value inline (.assertion-actual)
-->

<script lang="ts">
  import type { ReplayReport, ReplayStepResult } from '../../_generated/state';

  let { report }: { report: ReplayReport } = $props();

  // localState: collapsed/expanded (ADR-018: ephemeral UI preference)
  let collapsed = $state(true);

  const stepResults = $derived<ReplayStepResult[]>(report.step_results ?? []);

  const passCount = $derived(stepResults.filter((s) => s.ok && !s.skipped).length);
  const failCount = $derived(stepResults.filter((s) => !s.ok && !s.skipped).length);
  const skippedCount = $derived(stepResults.filter((s) => s.skipped).length);
  const assertionPassCount = $derived(stepResults.filter((s) => s.assertion_passed === true).length);
  const assertionFailCount = $derived(stepResults.filter((s) => s.assertion_passed === false).length);

  function toggle(): void {
    collapsed = !collapsed;
  }
</script>

<div class="replay-report-view">
  <div class="replay-report-header">
    <span class="replay-status-badge replay-status-badge--{report.status}">
      {report.status}
    </span>

    <span class="replay-report-summary">
      {stepResults.length} steps · {passCount} ok · {failCount} fail · {skippedCount} skipped
      {#if assertionPassCount + assertionFailCount > 0}
        · {assertionPassCount}✓ {assertionFailCount}✗ assertions
      {/if}
    </span>

    <button
      type="button"
      class="replay-report-toggle"
      onclick={toggle}
      title={collapsed ? 'Show steps' : 'Hide steps'}
    >
      {collapsed ? '▶' : '▼'}
    </button>
  </div>

  {#if !collapsed}
    <div class="replay-step-list">
      {#each stepResults as step (step.seq)}
        <div class="replay-step-row">
          <span class="replay-step-seq">{step.seq}</span>
          <span class="replay-step-kind">{step.kind}</span>

          {#if step.skipped}
            <span class="replay-step-skipped" title={step.skipped_reason ?? 'skipped'}>skip</span>
          {:else if step.ok}
            <span class="replay-step-ok">✓</span>
          {:else}
            <span class="replay-step-fail" title={step.error ?? 'failed'}>✗</span>
          {/if}

          {#if step.assertion_passed === true}
            <span class="assertion-pass">assert ✓</span>
          {:else if step.assertion_passed === false}
            <span class="assertion-fail">assert ✗</span>
            {#if step.assertion_actual != null}
              <span class="assertion-actual">{step.assertion_actual}</span>
            {/if}
          {/if}

          {#if !step.ok && step.error}
            <span class="replay-step-error" title={step.error}>{step.error}</span>
          {/if}
        </div>
      {/each}
    </div>
  {/if}
</div>

<style>
  .replay-report-view {
    display: flex;
    flex-direction: column;
    font-size: 11px;
  }

  .replay-report-header {
    display: flex;
    align-items: center;
    gap: 8px;
    padding: 5px 14px;
    border-top: 1px solid var(--fp-color-border-subtle);
    flex-wrap: wrap;
  }

  .replay-status-badge {
    font-size: 9px;
    padding: 1px 6px;
    border-radius: 7px;
    text-transform: lowercase;
    flex-shrink: 0;
  }

  .replay-status-badge--completed {
    background: rgba(100, 200, 100, 0.18);
    color: rgba(120, 220, 120, 0.9);
  }

  .replay-status-badge--failed {
    background: rgba(255, 80, 80, 0.15);
    color: rgba(255, 120, 120, 0.9);
  }

  .replay-status-badge--aborted {
    background: rgba(255, 180, 50, 0.15);
    color: rgba(255, 200, 80, 0.9);
  }

  .replay-report-summary {
    flex: 1 1 auto;
    font-size: 10px;
    color: var(--fp-color-text-muted);
    font-family: 'SF Mono', 'JetBrains Mono', Menlo, Consolas, monospace;
  }

  .replay-report-toggle {
    background: transparent;
    border: none;
    color: var(--fp-color-text-muted);
    font: inherit;
    font-size: 10px;
    cursor: pointer;
    padding: 2px 4px;
    flex-shrink: 0;
    transition: color 120ms ease;
  }

  .replay-report-toggle:hover {
    color: var(--fp-color-text-primary);
  }

  /* ---- Step list ---- */

  .replay-step-list {
    display: flex;
    flex-direction: column;
    padding: 0 14px 6px;
  }

  .replay-step-row {
    display: flex;
    align-items: baseline;
    gap: 6px;
    padding: 2px 0;
    font-size: 10px;
    border-bottom: 1px solid var(--fp-color-border-subtle);
  }

  .replay-step-seq {
    font-family: 'SF Mono', 'JetBrains Mono', Menlo, Consolas, monospace;
    color: var(--fp-color-text-muted);
    min-width: 18px;
    flex-shrink: 0;
  }

  .replay-step-kind {
    font-family: 'SF Mono', 'JetBrains Mono', Menlo, Consolas, monospace;
    color: var(--fp-color-text-secondary);
    flex-shrink: 0;
  }

  .replay-step-ok {
    color: rgba(100, 200, 100, 0.9);
    flex-shrink: 0;
  }

  .replay-step-fail {
    color: rgba(255, 100, 100, 0.9);
    flex-shrink: 0;
    cursor: help;
  }

  .replay-step-skipped {
    font-size: 9px;
    padding: 0 4px;
    border-radius: 4px;
    background: rgba(180, 180, 180, 0.12);
    color: var(--fp-color-text-muted);
    flex-shrink: 0;
    cursor: help;
  }

  .replay-step-error {
    font-size: 10px;
    color: rgba(255, 120, 120, 0.8);
    font-family: 'SF Mono', 'JetBrains Mono', Menlo, Consolas, monospace;
    overflow: hidden;
    text-overflow: ellipsis;
    white-space: nowrap;
    flex: 1 1 auto;
    cursor: help;
  }

  .assertion-pass {
    font-size: 9px;
    color: rgba(100, 200, 100, 0.9);
    flex-shrink: 0;
  }

  .assertion-fail {
    font-size: 9px;
    color: rgba(255, 100, 100, 0.9);
    flex-shrink: 0;
  }

  .assertion-actual {
    font-size: 9px;
    font-family: 'SF Mono', 'JetBrains Mono', Menlo, Consolas, monospace;
    color: var(--fp-color-text-muted);
    background: rgba(255, 100, 100, 0.1);
    padding: 0 4px;
    border-radius: 3px;
    overflow: hidden;
    text-overflow: ellipsis;
    white-space: nowrap;
  }
</style>
