/**
 * ReplayReportView component tests (vitest + jsdom + @testing-library/svelte).
 *
 * Test surface:
 *   - Renders status badge ("completed" / "failed" / "aborted")
 *   - Renders each ReplayStepResult row: seq, kind, ok/fail icon, skipped indicator
 *   - Assertion steps: shows assertion_passed badge + assertion_actual on failure
 *   - Collapsed by default; expandable via toggle button (localState)
 */

import { describe, expect, test, afterEach } from 'vitest';
import { render, cleanup, fireEvent } from '@testing-library/svelte';
import ReplayReportView from './ReplayReportView.svelte';
import type { ReplayReport, ReplayStepResult } from '../../_generated/state';

afterEach(() => {
  cleanup();
});

// --- Fixtures ---------------------------------------------------------------

function makeStepResult(overrides: Partial<ReplayStepResult> = {}): ReplayStepResult {
  return {
    seq: 1,
    kind: 'page_event',
    ok: true,
    skipped: false,
    skipped_reason: null,
    error: null,
    assertion_passed: null,
    assertion_actual: null,
    duration_ms: 50,
    ...overrides,
  } as ReplayStepResult;
}

function makeReport(overrides: Partial<ReplayReport> = {}): ReplayReport {
  return {
    replay_id: 'replay-001',
    recording_id: 'rec-001',
    status: 'completed',
    started_at_ms: 1700000000000,
    ended_at_ms: 1700000010000,
    step_results: [],
    error: null,
    origin_session: null,
    ...overrides,
  } as unknown as ReplayReport;
}

// --- Tests ------------------------------------------------------------------

describe('ReplayReportView', () => {
  test('renders status badge with completed status', () => {
    const report = makeReport({ status: 'completed' });
    const { container } = render(ReplayReportView, { props: { report } });
    const badge = container.querySelector('.replay-status-badge');
    expect(badge).not.toBeNull();
    expect(badge!.textContent).toContain('completed');
  });

  test('renders status badge with failed status', () => {
    const report = makeReport({ status: 'failed' });
    const { container } = render(ReplayReportView, { props: { report } });
    const badge = container.querySelector('.replay-status-badge');
    expect(badge).not.toBeNull();
    expect(badge!.textContent).toContain('failed');
  });

  test('renders status badge with aborted status', () => {
    const report = makeReport({ status: 'aborted' });
    const { container } = render(ReplayReportView, { props: { report } });
    const badge = container.querySelector('.replay-status-badge');
    expect(badge).not.toBeNull();
    expect(badge!.textContent).toContain('aborted');
  });

  test('is collapsed by default — step list not visible', () => {
    const report = makeReport({ step_results: [makeStepResult()] });
    const { container } = render(ReplayReportView, { props: { report } });
    // No step rows rendered when collapsed
    expect(container.querySelector('.replay-step-row')).toBeNull();
  });

  test('expand button shows step list', async () => {
    const step = makeStepResult({ seq: 1, kind: 'page_event', ok: true });
    const report = makeReport({ step_results: [step] });
    const { container } = render(ReplayReportView, { props: { report } });
    const expandBtn = container.querySelector('.replay-report-toggle') as HTMLButtonElement;
    expect(expandBtn).not.toBeNull();
    await fireEvent.click(expandBtn);
    expect(container.querySelector('.replay-step-row')).not.toBeNull();
  });

  test('step row shows seq, kind', async () => {
    const step = makeStepResult({ seq: 3, kind: 'navigation', ok: true });
    const report = makeReport({ step_results: [step] });
    const { container } = render(ReplayReportView, { props: { report } });
    await fireEvent.click(container.querySelector('.replay-report-toggle')!);
    const row = container.querySelector('.replay-step-row');
    expect(row).not.toBeNull();
    expect(row!.textContent).toContain('navigation');
  });

  test('skipped step shows skipped indicator', async () => {
    const step = makeStepResult({ seq: 2, kind: 'pick_ref', ok: true, skipped: true, skipped_reason: 'pick_ref_skipped_mvp' });
    const report = makeReport({ step_results: [step] });
    const { container } = render(ReplayReportView, { props: { report } });
    await fireEvent.click(container.querySelector('.replay-report-toggle')!);
    expect(container.querySelector('.replay-step-skipped')).not.toBeNull();
  });

  test('failed step shows fail icon (.replay-step-fail)', async () => {
    const step = makeStepResult({ seq: 1, kind: 'page_event', ok: false, error: 'Element not found' });
    const report = makeReport({ status: 'failed', step_results: [step] });
    const { container } = render(ReplayReportView, { props: { report } });
    await fireEvent.click(container.querySelector('.replay-report-toggle')!);
    expect(container.querySelector('.replay-step-fail')).not.toBeNull();
  });

  test('assertion step with assertion_passed=false shows assertion_actual', async () => {
    const step = makeStepResult({
      seq: 5,
      kind: 'assertion',
      ok: true,
      assertion_passed: false,
      assertion_actual: 'Goodbye',
    });
    const report = makeReport({ step_results: [step] });
    const { container } = render(ReplayReportView, { props: { report } });
    await fireEvent.click(container.querySelector('.replay-report-toggle')!);
    expect(container.textContent).toContain('Goodbye');
    expect(container.querySelector('.assertion-actual')).not.toBeNull();
  });

  test('assertion step with assertion_passed=true shows pass badge', async () => {
    const step = makeStepResult({
      seq: 5,
      kind: 'assertion',
      ok: true,
      assertion_passed: true,
      assertion_actual: null,
    });
    const report = makeReport({ step_results: [step] });
    const { container } = render(ReplayReportView, { props: { report } });
    await fireEvent.click(container.querySelector('.replay-report-toggle')!);
    expect(container.querySelector('.assertion-pass')).not.toBeNull();
  });
});
