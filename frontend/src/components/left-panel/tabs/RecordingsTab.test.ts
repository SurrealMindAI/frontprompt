/**
 * RecordingsTab component tests (vitest + jsdom + @testing-library/svelte).
 *
 * Test surface:
 *   - Empty state: "No recordings yet" message
 *   - List view: name, active indicator (red dot), entry_count
 *   - Click row → bridge sends recording_selected_requested
 *   - Active indicator absent for stopped recordings
 *   - Timeline view shown when activeDetailRecordingId is set
 *   - Timeline: PageEventEntry (event_type + target), PickRefEntry (inline pick lookup),
 *     NavigationEntry (from_url → to_url)
 *   - Back button sends recording_selected_requested with null
 *   - Replay progress bar shown when activeReplayProgress is non-null
 *   - Progress bar shows current_seq/total_steps + passed/failed assertion counts
 *   - No progress bar when activeReplayProgress is null
 */

// Bridge mock — hoisted before module imports
const send = vi.hoisted(() => vi.fn());
vi.mock('../../../bridge/bridge.svelte', () => ({ bridge: { send } }));

import { describe, expect, test, vi, afterEach } from 'vitest';
import { render, cleanup, fireEvent } from '@testing-library/svelte';
import RecordingsTab from './RecordingsTab.svelte';
import { backendState } from '../../../backend-state/backend-state.svelte';
import type { RecordingMeta, Recording, ReplayProgress } from '../../../_generated/state';
import type { Pick as PickType } from '../../../_generated/state';

afterEach(() => {
  cleanup();
  send.mockClear();
  // Reset all relevant backend state between tests
  backendState.recordings.recordings = [];
  backendState.recordings.activeDetailRecordingId = null;
  backendState.recordings.detailRecording = null;
  backendState.recordings.activeRecordingId = null;
  backendState.recordings.activeReplayProgress = null;
  backendState.inspector.picks = [];
});

// --- Fixtures ---------------------------------------------------------------

function makeRecordingMeta(overrides: Partial<RecordingMeta> = {}): RecordingMeta {
  return {
    recording_id: 'rec-0001',
    name: 'Test Recording',
    description: '',
    status: 'stopped',
    started_at_ms: 1700000000000,
    ended_at_ms: 1700000010000,
    entry_count: 3,
    ...overrides,
  };
}

function makeDetailRecording(overrides: Partial<Recording> = {}): Recording {
  return {
    recording_id: 'rec-0001',
    name: 'Test Recording',
    description: '',
    status: 'stopped',
    started_at_ms: 1700000000000,
    ended_at_ms: 1700000010000,
    entries: [],
    ...overrides,
  } as unknown as Recording;
}

function makePick(pickId: string, selector: string): PickType {
  return {
    pick_id: pickId,
    url: 'https://example.com',
    timestamp_ms: 0,
    element: {
      selector,
      fingerprint: {
        tag: 'div',
        attributes: {},
        text: '',
        path: [],
        parent_name: null,
        parent_attribs: {},
        parent_text: '',
        siblings: [],
        children: [],
      },
      text_snippet: '',
      rect: { x: 0, y: 0, width: 10, height: 10 },
    },
    comment: '',
    color_index: 0,
    origin_session: null,
  } as unknown as PickType;
}

// --- Tests: list view (empty) -----------------------------------------------

describe('RecordingsTab — empty state', () => {
  test('renders "No recordings yet" when recordings list is empty', () => {
    backendState.recordings.recordings = [];
    backendState.recordings.activeDetailRecordingId = null;
    const { container } = render(RecordingsTab, {});
    expect(container.textContent).toContain('No recordings yet');
  });
});

// --- Tests: list view (with recordings) ------------------------------------

describe('RecordingsTab — list view', () => {
  test('renders recording name', () => {
    backendState.recordings.recordings = [makeRecordingMeta({ name: 'My Test Recording' })];
    backendState.recordings.activeDetailRecordingId = null;
    const { container } = render(RecordingsTab, {});
    expect(container.textContent).toContain('My Test Recording');
  });

  test('renders red recording indicator for active recording', () => {
    backendState.recordings.recordings = [makeRecordingMeta({ status: 'active' })];
    backendState.recordings.activeDetailRecordingId = null;
    const { container } = render(RecordingsTab, {});
    const indicator = container.querySelector('.recording-indicator');
    expect(indicator).not.toBeNull();
  });

  test('active recording indicator absent for stopped recording', () => {
    backendState.recordings.recordings = [makeRecordingMeta({ status: 'stopped' })];
    backendState.recordings.activeDetailRecordingId = null;
    const { container } = render(RecordingsTab, {});
    const indicator = container.querySelector('.recording-indicator');
    expect(indicator).toBeNull();
  });

  test('renders entry_count for stopped recording', () => {
    backendState.recordings.recordings = [makeRecordingMeta({ status: 'stopped', entry_count: 7 })];
    backendState.recordings.activeDetailRecordingId = null;
    const { container } = render(RecordingsTab, {});
    expect(container.textContent).toContain('7');
  });

  test('clicking a recording row sends recording_selected_requested via bridge', async () => {
    backendState.recordings.recordings = [makeRecordingMeta({ recording_id: 'rec-abc', name: 'Click Me' })];
    backendState.recordings.activeDetailRecordingId = null;
    const { container } = render(RecordingsTab, {});
    const row = container.querySelector('.recording-row');
    expect(row).not.toBeNull();
    await fireEvent.click(row!);
    expect(send).toHaveBeenCalledWith(
      expect.objectContaining({
        kind: 'recording_selected_requested',
        recording_id: 'rec-abc',
      })
    );
  });
});

// --- Tests: timeline view ---------------------------------------------------

describe('RecordingsTab — timeline view', () => {
  test('shows timeline view when activeDetailRecordingId is set', () => {
    backendState.recordings.activeDetailRecordingId = 'rec-0001';
    backendState.recordings.detailRecording = makeDetailRecording({ entries: [] });
    const { container } = render(RecordingsTab, {});
    expect(container.querySelector('.timeline-view')).not.toBeNull();
  });

  test('renders PageEventEntry with event_type and target', () => {
    backendState.recordings.activeDetailRecordingId = 'rec-0001';
    backendState.recordings.detailRecording = makeDetailRecording({
      entries: [
        {
          kind: 'page_event' as const,
          seq: 1,
          timestamp_ms: 1700000005000,
          event_type: 'click',
          target: 'button#submit',
          default_prevented: false,
        },
      ],
    });
    const { container } = render(RecordingsTab, {});
    expect(container.textContent).toContain('click');
    expect(container.textContent).toContain('button#submit');
  });

  test('renders PickRefEntry with pick selector looked up inline from backendState.inspector.picks', () => {
    backendState.inspector.picks = [makePick('pick-xyz', 'div.hero-section')];
    backendState.recordings.activeDetailRecordingId = 'rec-0001';
    backendState.recordings.detailRecording = makeDetailRecording({
      entries: [
        {
          kind: 'pick_ref' as const,
          seq: 2,
          timestamp_ms: 1700000006000,
          pick_id: 'pick-xyz',
        },
      ],
    });
    const { container } = render(RecordingsTab, {});
    expect(container.textContent).toContain('div.hero-section');
  });

  test('renders NavigationEntry with from_url hostname and to_url hostname', () => {
    backendState.recordings.activeDetailRecordingId = 'rec-0001';
    backendState.recordings.detailRecording = makeDetailRecording({
      entries: [
        {
          kind: 'navigation' as const,
          seq: 3,
          timestamp_ms: 1700000007000,
          from_url: 'https://example.com/page1',
          to_url: 'https://example.com/page2',
        },
      ],
    });
    const { container } = render(RecordingsTab, {});
    expect(container.textContent).toContain('example.com');
  });

  test('Back button sends recording_selected_requested with null via bridge', async () => {
    backendState.recordings.activeDetailRecordingId = 'rec-0001';
    backendState.recordings.detailRecording = makeDetailRecording({ entries: [] });
    const { container } = render(RecordingsTab, {});
    const backButton = container.querySelector('.timeline-back-btn');
    expect(backButton).not.toBeNull();
    await fireEvent.click(backButton!);
    expect(send).toHaveBeenCalledWith(
      expect.objectContaining({
        kind: 'recording_selected_requested',
        recording_id: null,
      })
    );
  });
});

// --- Tests: replay progress bar -----------------------------------------

function makeReplayProgress(overrides: Partial<ReplayProgress> = {}): ReplayProgress {
  return {
    replay_id: 'replay-001',
    recording_id: 'rec-0001',
    current_seq: 3,
    total_steps: 10,
    passed_assertions: 1,
    failed_assertions: 0,
    ...overrides,
  } as ReplayProgress;
}

describe('RecordingsTab — replay progress bar', () => {
  test('renders progress bar when activeReplayProgress is non-null', () => {
    backendState.recordings.activeReplayProgress = makeReplayProgress();
    const { container } = render(RecordingsTab, {});
    expect(container.querySelector('.replay-progress-bar')).not.toBeNull();
  });

  test('does not render progress bar when activeReplayProgress is null', () => {
    backendState.recordings.activeReplayProgress = null;
    const { container } = render(RecordingsTab, {});
    expect(container.querySelector('.replay-progress-bar')).toBeNull();
  });

  test('progress bar shows current_seq / total_steps', () => {
    backendState.recordings.activeReplayProgress = makeReplayProgress({ current_seq: 5, total_steps: 12 });
    const { container } = render(RecordingsTab, {});
    const bar = container.querySelector('.replay-progress-bar');
    expect(bar).not.toBeNull();
    expect(bar!.textContent).toContain('5');
    expect(bar!.textContent).toContain('12');
  });

  test('progress bar shows passed_assertions count', () => {
    backendState.recordings.activeReplayProgress = makeReplayProgress({ passed_assertions: 3, failed_assertions: 1 });
    const { container } = render(RecordingsTab, {});
    const bar = container.querySelector('.replay-progress-bar');
    expect(bar).not.toBeNull();
    expect(bar!.textContent).toContain('3');
    expect(bar!.textContent).toContain('1');
  });
});
