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
import type { RecordingMeta, Recording, ReplayProgress, Region, Relation } from '../../../_generated/state';
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
  backendState.inspector.regions = [];
  backendState.inspector.relations = [];
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

function makePick(pickId: string, selector: string, overrides: Partial<PickType> = {}): PickType {
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
    ...overrides,
  } as unknown as PickType;
}

function makeRegion(regionId: string, overrides: Partial<Region> = {}): Region {
  return {
    region_id: regionId,
    rect: { x: 10, y: 20, width: 100, height: 50 },
    member_pick_ids: [],
    note: null,
    timestamp_ms: 1700000000000,
    color_index: 0,
    viewport_snapshot: null,
    origin_session: null,
    ...overrides,
  } as unknown as Region;
}

function makeRelation(relationId: string, overrides: Partial<Relation> = {}): Relation {
  return {
    relation_id: relationId,
    source_id: 'src-pick-001',
    source_kind: 'pick',
    target_id: 'tgt-region-001',
    target_kind: 'region',
    kind: 'relates_to',
    note: null,
    timestamp_ms: 1700000000000,
    origin_session: null,
    ...overrides,
  } as unknown as Relation;
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

  test('timeline header exposes an edit affordance (BUG 4: discoverable name/desc edit)', () => {
    backendState.recordings.activeDetailRecordingId = 'rec-0001';
    backendState.recordings.detailRecording = makeDetailRecording({ entries: [] });
    const { container } = render(RecordingsTab, {});
    const editBtn = container.querySelector('.timeline-edit-btn');
    expect(editBtn).not.toBeNull();
  });

  test('clicking the edit affordance opens the right panel (where RecordingDetails lives)', async () => {
    backendState.recordings.activeDetailRecordingId = 'rec-0001';
    backendState.recordings.detailRecording = makeDetailRecording({ entries: [] });
    // Right panel starts closed → clicking ✎ must open it so the editor is visible.
    backendState.panel.panels.right.open = false;
    const { container } = render(RecordingsTab, {});
    const editBtn = container.querySelector('.timeline-edit-btn');
    expect(editBtn).not.toBeNull();
    await fireEvent.click(editBtn!);
    expect(backendState.panel.panels.right.open).toBe(true);
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

// --- Tests: transcript segments (voice-over) --------------------------------

describe('RecordingsTab — transcript segment timeline rendering', () => {
  test('renders a transcript_segment entry with its text', () => {
    backendState.recordings.activeDetailRecordingId = 'rec-0001';
    backendState.recordings.detailRecording = makeDetailRecording({
      entries: [
        {
          kind: 'transcript_segment' as const,
          seq: 5,
          timestamp_ms: 1700000003000,
          start_ms: 3000,
          end_ms: 6000,
          text: 'now I click the submit button',
          backend_id: 'mlx_whisper',
        },
      ],
    });
    const { container } = render(RecordingsTab, {});
    expect(container.querySelector('.transcript-segment')).not.toBeNull();
    expect(container.textContent).toContain('now I click the submit button');
  });

  test('transcript segments interleave chronologically by timestamp, not by seq', () => {
    // Voice segments are appended at stop (highest seq) but span the whole
    // recording. They must sort by timestamp_ms so narration interleaves with
    // the actions it describes.
    backendState.recordings.activeDetailRecordingId = 'rec-0001';
    backendState.recordings.detailRecording = makeDetailRecording({
      started_at_ms: 1700000000000,
      entries: [
        {
          kind: 'page_event' as const,
          seq: 0,
          timestamp_ms: 1700000002000,
          event_type: 'click',
          target: 'button#first',
          default_prevented: false,
        },
        {
          kind: 'page_event' as const,
          seq: 1,
          timestamp_ms: 1700000008000,
          event_type: 'click',
          target: 'button#second',
          default_prevented: false,
        },
        // Transcript appended later (higher seq) but spoken BEFORE the second click.
        {
          kind: 'transcript_segment' as const,
          seq: 2,
          timestamp_ms: 1700000004000,
          start_ms: 4000,
          end_ms: 6000,
          text: 'spoken between the two clicks',
          backend_id: 'mlx_whisper',
        },
      ],
    });
    const { container } = render(RecordingsTab, {});
    const rows = Array.from(container.querySelectorAll('.timeline-entry'));
    const order = rows.map((r) => r.textContent ?? '');
    const idxFirst = order.findIndex((t) => t.includes('button#first'));
    const idxSpoken = order.findIndex((t) => t.includes('spoken between the two clicks'));
    const idxSecond = order.findIndex((t) => t.includes('button#second'));
    expect(idxFirst).toBeGreaterThanOrEqual(0);
    expect(idxSpoken).toBeGreaterThan(idxFirst);
    expect(idxSecond).toBeGreaterThan(idxSpoken);
  });

  test('entries with equal timestamp fall back to seq order', () => {
    backendState.recordings.activeDetailRecordingId = 'rec-0001';
    backendState.recordings.detailRecording = makeDetailRecording({
      entries: [
        {
          kind: 'page_event' as const,
          seq: 1,
          timestamp_ms: 1700000005000,
          event_type: 'keydown',
          target: 'input#a',
          default_prevented: false,
        },
        {
          kind: 'page_event' as const,
          seq: 0,
          timestamp_ms: 1700000005000,
          event_type: 'click',
          target: 'button#b',
          default_prevented: false,
        },
      ],
    });
    const { container } = render(RecordingsTab, {});
    const rows = Array.from(container.querySelectorAll('.timeline-entry'));
    const order = rows.map((r) => r.textContent ?? '');
    const idxB = order.findIndex((t) => t.includes('button#b')); // seq 0
    const idxA = order.findIndex((t) => t.includes('input#a')); // seq 1
    expect(idxB).toBeLessThan(idxA);
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

// --- Tests: timeline expand/collapse (accordion) ----------------------------

describe('RecordingsTab — timeline entry expand/collapse', () => {
  test('detail panel is hidden by default (collapsed)', () => {
    backendState.recordings.activeDetailRecordingId = 'rec-0001';
    backendState.recordings.detailRecording = makeDetailRecording({
      entries: [
        {
          kind: 'page_event' as const,
          seq: 1,
          timestamp_ms: 1700000005000,
          event_type: 'click',
          target: 'button#test',
          default_prevented: false,
        },
      ],
    });
    const { container } = render(RecordingsTab, {});
    expect(container.querySelector('.timeline-entry__detail')).toBeNull();
  });

  test('clicking a timeline row reveals the detail panel', async () => {
    backendState.recordings.activeDetailRecordingId = 'rec-0001';
    backendState.recordings.detailRecording = makeDetailRecording({
      entries: [
        {
          kind: 'page_event' as const,
          seq: 1,
          timestamp_ms: 1700000005000,
          event_type: 'click',
          target: 'button#test',
          default_prevented: false,
        },
      ],
    });
    const { container } = render(RecordingsTab, {});
    const rowBtn = container.querySelector('.timeline-entry__row');
    expect(rowBtn).not.toBeNull();
    await fireEvent.click(rowBtn!);
    expect(container.querySelector('.timeline-entry__detail')).not.toBeNull();
  });

  test('clicking the row again collapses the detail panel', async () => {
    backendState.recordings.activeDetailRecordingId = 'rec-0001';
    backendState.recordings.detailRecording = makeDetailRecording({
      entries: [
        {
          kind: 'page_event' as const,
          seq: 1,
          timestamp_ms: 1700000005000,
          event_type: 'click',
          target: 'button#test',
          default_prevented: false,
        },
      ],
    });
    const { container } = render(RecordingsTab, {});
    const rowBtn = container.querySelector('.timeline-entry__row');
    await fireEvent.click(rowBtn!);
    expect(container.querySelector('.timeline-entry__detail')).not.toBeNull();
    await fireEvent.click(rowBtn!);
    expect(container.querySelector('.timeline-entry__detail')).toBeNull();
  });

  test('expand icon shows ▸ when collapsed and ▾ when expanded', async () => {
    backendState.recordings.activeDetailRecordingId = 'rec-0001';
    backendState.recordings.detailRecording = makeDetailRecording({
      entries: [
        {
          kind: 'page_event' as const,
          seq: 1,
          timestamp_ms: 1700000005000,
          event_type: 'click',
          target: 'button#test',
          default_prevented: false,
        },
      ],
    });
    const { container } = render(RecordingsTab, {});
    const rowBtn = container.querySelector('.timeline-entry__row');
    expect(rowBtn!.textContent).toContain('▸');
    await fireEvent.click(rowBtn!);
    expect(rowBtn!.textContent).toContain('▾');
  });

  test('row has aria-expanded reflecting expand state', async () => {
    backendState.recordings.activeDetailRecordingId = 'rec-0001';
    backendState.recordings.detailRecording = makeDetailRecording({
      entries: [
        {
          kind: 'page_event' as const,
          seq: 1,
          timestamp_ms: 1700000005000,
          event_type: 'click',
          target: 'button#test',
          default_prevented: false,
        },
      ],
    });
    const { container } = render(RecordingsTab, {});
    const rowBtn = container.querySelector('.timeline-entry__row');
    expect(rowBtn!.getAttribute('aria-expanded')).toBe('false');
    await fireEvent.click(rowBtn!);
    expect(rowBtn!.getAttribute('aria-expanded')).toBe('true');
  });

  test('expanding one entry does not expand others', async () => {
    backendState.recordings.activeDetailRecordingId = 'rec-0001';
    backendState.recordings.detailRecording = makeDetailRecording({
      entries: [
        {
          kind: 'page_event' as const,
          seq: 1,
          timestamp_ms: 1700000005000,
          event_type: 'click',
          target: 'button#first',
          default_prevented: false,
        },
        {
          kind: 'page_event' as const,
          seq: 2,
          timestamp_ms: 1700000006000,
          event_type: 'click',
          target: 'button#second',
          default_prevented: false,
        },
      ],
    });
    const { container } = render(RecordingsTab, {});
    const rows = container.querySelectorAll('.timeline-entry__row');
    await fireEvent.click(rows[0]!);
    const details = container.querySelectorAll('.timeline-entry__detail');
    expect(details).toHaveLength(1);
  });
});

// --- Tests: timeline detail: page_event ------------------------------------

describe('RecordingsTab — timeline detail: page_event', () => {
  test('expanded detail shows full target_path chain', async () => {
    backendState.recordings.activeDetailRecordingId = 'rec-0001';
    backendState.recordings.detailRecording = makeDetailRecording({
      entries: [
        {
          kind: 'page_event' as const,
          seq: 1,
          timestamp_ms: 1700000005000,
          event_type: 'click',
          target: 'button#submit',
          target_path: ['html', 'body', 'main', 'form', 'button#submit'],
          default_prevented: false,
        },
      ],
    });
    const { container } = render(RecordingsTab, {});
    await fireEvent.click(container.querySelector('.timeline-entry__row')!);
    const detail = container.querySelector('.timeline-entry__detail');
    expect(detail).not.toBeNull();
    expect(detail!.textContent).toContain('html');
    expect(detail!.textContent).toContain('body › main');
  });

  test('expanded detail shows key for keydown events', async () => {
    backendState.recordings.activeDetailRecordingId = 'rec-0001';
    backendState.recordings.detailRecording = makeDetailRecording({
      entries: [
        {
          kind: 'page_event' as const,
          seq: 1,
          timestamp_ms: 1700000005000,
          event_type: 'keydown',
          target: 'input#search',
          default_prevented: false,
          key: 'Enter',
        },
      ],
    });
    const { container } = render(RecordingsTab, {});
    await fireEvent.click(container.querySelector('.timeline-entry__row')!);
    const detail = container.querySelector('.timeline-entry__detail');
    expect(detail!.textContent).toContain('Enter');
  });

  test('expanded detail shows seq and default_prevented', async () => {
    backendState.recordings.activeDetailRecordingId = 'rec-0001';
    backendState.recordings.detailRecording = makeDetailRecording({
      entries: [
        {
          kind: 'page_event' as const,
          seq: 42,
          timestamp_ms: 1700000005000,
          event_type: 'click',
          target: 'button#x',
          default_prevented: true,
        },
      ],
    });
    const { container } = render(RecordingsTab, {});
    await fireEvent.click(container.querySelector('.timeline-entry__row')!);
    const detail = container.querySelector('.timeline-entry__detail');
    expect(detail!.textContent).toContain('42');
    expect(detail!.textContent).toContain('yes');
  });
});

// --- Tests: timeline detail: pick_ref ---------------------------------------

describe('RecordingsTab — timeline detail: pick_ref', () => {
  test('resolved pick shows selector and comment in detail', async () => {
    backendState.inspector.picks = [
      makePick('pick-001', 'div.hero-section', { comment: 'Important hero element' }),
    ];
    backendState.recordings.activeDetailRecordingId = 'rec-0001';
    backendState.recordings.detailRecording = makeDetailRecording({
      entries: [
        {
          kind: 'pick_ref' as const,
          seq: 1,
          timestamp_ms: 1700000005000,
          pick_id: 'pick-001',
        },
      ],
    });
    const { container } = render(RecordingsTab, {});
    await fireEvent.click(container.querySelector('.timeline-entry__row')!);
    const detail = container.querySelector('.timeline-entry__detail');
    expect(detail).not.toBeNull();
    expect(detail!.textContent).toContain('div.hero-section');
    expect(detail!.textContent).toContain('Important hero element');
  });

  test('resolved pick shows color_index and pick_id in detail', async () => {
    backendState.inspector.picks = [
      makePick('pick-abc-123', 'span.nav-link', { color_index: 7 }),
    ];
    backendState.recordings.activeDetailRecordingId = 'rec-0001';
    backendState.recordings.detailRecording = makeDetailRecording({
      entries: [
        {
          kind: 'pick_ref' as const,
          seq: 1,
          timestamp_ms: 1700000005000,
          pick_id: 'pick-abc-123',
        },
      ],
    });
    const { container } = render(RecordingsTab, {});
    await fireEvent.click(container.querySelector('.timeline-entry__row')!);
    const detail = container.querySelector('.timeline-entry__detail');
    expect(detail!.textContent).toContain('7');
    expect(detail!.textContent).toContain('pick-abc-123');
  });

  test('missing pick shows graceful fallback with id prefix', async () => {
    backendState.inspector.picks = [];
    backendState.recordings.activeDetailRecordingId = 'rec-0001';
    backendState.recordings.detailRecording = makeDetailRecording({
      entries: [
        {
          kind: 'pick_ref' as const,
          seq: 1,
          timestamp_ms: 1700000005000,
          pick_id: 'missing-pick-deadbeef',
        },
      ],
    });
    const { container } = render(RecordingsTab, {});
    await fireEvent.click(container.querySelector('.timeline-entry__row')!);
    const detail = container.querySelector('.timeline-entry__detail');
    expect(detail).not.toBeNull();
    expect(detail!.textContent).toContain('not found');
    expect(detail!.textContent).toContain('missing');
  });
});

// --- Tests: timeline detail: region_ref -------------------------------------

describe('RecordingsTab — timeline detail: region_ref', () => {
  test('resolved region shows rect and member count (not just id stub)', async () => {
    backendState.inspector.regions = [
      makeRegion('region-001', {
        rect: { x: 10, y: 20, width: 100, height: 50 },
        member_pick_ids: ['p1', 'p2', 'p3'],
        note: 'my test region',
      }),
    ];
    backendState.recordings.activeDetailRecordingId = 'rec-0001';
    backendState.recordings.detailRecording = makeDetailRecording({
      entries: [
        {
          kind: 'region_ref' as const,
          seq: 1,
          timestamp_ms: 1700000005000,
          region_id: 'region-001',
        },
      ],
    });
    const { container } = render(RecordingsTab, {});
    await fireEvent.click(container.querySelector('.timeline-entry__row')!);
    const detail = container.querySelector('.timeline-entry__detail');
    expect(detail).not.toBeNull();
    // Shows rect (not just id stub)
    expect(detail!.textContent).toContain('10');  // rect.x
    expect(detail!.textContent).toContain('100'); // rect.width
    // Shows member count
    expect(detail!.textContent).toContain('3');
    // Shows note
    expect(detail!.textContent).toContain('my test region');
  });

  test('resolved region shows region_id in detail', async () => {
    backendState.inspector.regions = [
      makeRegion('region-xyzabc', {
        rect: { x: 0, y: 0, width: 50, height: 50 },
        member_pick_ids: [],
      }),
    ];
    backendState.recordings.activeDetailRecordingId = 'rec-0001';
    backendState.recordings.detailRecording = makeDetailRecording({
      entries: [
        {
          kind: 'region_ref' as const,
          seq: 1,
          timestamp_ms: 1700000005000,
          region_id: 'region-xyzabc',
        },
      ],
    });
    const { container } = render(RecordingsTab, {});
    await fireEvent.click(container.querySelector('.timeline-entry__row')!);
    const detail = container.querySelector('.timeline-entry__detail');
    expect(detail!.textContent).toContain('region-xyzabc');
  });

  test('missing region shows graceful fallback', async () => {
    backendState.inspector.regions = [];
    backendState.recordings.activeDetailRecordingId = 'rec-0001';
    backendState.recordings.detailRecording = makeDetailRecording({
      entries: [
        {
          kind: 'region_ref' as const,
          seq: 1,
          timestamp_ms: 1700000005000,
          region_id: 'gone-region-abc',
        },
      ],
    });
    const { container } = render(RecordingsTab, {});
    await fireEvent.click(container.querySelector('.timeline-entry__row')!);
    const detail = container.querySelector('.timeline-entry__detail');
    expect(detail).not.toBeNull();
    expect(detail!.textContent).toContain('not found');
  });
});

// --- Tests: timeline detail: relation_ref -----------------------------------

describe('RecordingsTab — timeline detail: relation_ref', () => {
  test('resolved relation shows kind and source/target endpoints', async () => {
    backendState.inspector.relations = [
      makeRelation('rel-001', {
        source_id: 'src-pick-xyz',
        source_kind: 'pick',
        target_id: 'tgt-region-abc',
        target_kind: 'region',
        kind: 'triggers',
        note: 'trigger note',
      }),
    ];
    backendState.recordings.activeDetailRecordingId = 'rec-0001';
    backendState.recordings.detailRecording = makeDetailRecording({
      entries: [
        {
          kind: 'relation_ref' as const,
          seq: 1,
          timestamp_ms: 1700000005000,
          relation_id: 'rel-001',
        },
      ],
    });
    const { container } = render(RecordingsTab, {});
    await fireEvent.click(container.querySelector('.timeline-entry__row')!);
    const detail = container.querySelector('.timeline-entry__detail');
    expect(detail).not.toBeNull();
    expect(detail!.textContent).toContain('triggers');
    expect(detail!.textContent).toContain('pick');
    expect(detail!.textContent).toContain('region');
    expect(detail!.textContent).toContain('trigger note');
  });

  test('resolved relation shows relation_id in detail', async () => {
    backendState.inspector.relations = [
      makeRelation('rel-fullid-001', {
        source_id: 'src',
        source_kind: 'pick',
        target_id: 'tgt',
        target_kind: 'pick',
        kind: 'part_of',
      }),
    ];
    backendState.recordings.activeDetailRecordingId = 'rec-0001';
    backendState.recordings.detailRecording = makeDetailRecording({
      entries: [
        {
          kind: 'relation_ref' as const,
          seq: 1,
          timestamp_ms: 1700000005000,
          relation_id: 'rel-fullid-001',
        },
      ],
    });
    const { container } = render(RecordingsTab, {});
    await fireEvent.click(container.querySelector('.timeline-entry__row')!);
    const detail = container.querySelector('.timeline-entry__detail');
    expect(detail!.textContent).toContain('rel-fullid-001');
  });

  test('missing relation shows graceful fallback', async () => {
    backendState.inspector.relations = [];
    backendState.recordings.activeDetailRecordingId = 'rec-0001';
    backendState.recordings.detailRecording = makeDetailRecording({
      entries: [
        {
          kind: 'relation_ref' as const,
          seq: 1,
          timestamp_ms: 1700000005000,
          relation_id: 'gone-relation-xyz',
        },
      ],
    });
    const { container } = render(RecordingsTab, {});
    await fireEvent.click(container.querySelector('.timeline-entry__row')!);
    const detail = container.querySelector('.timeline-entry__detail');
    expect(detail).not.toBeNull();
    expect(detail!.textContent).toContain('not found');
  });
});

// --- Tests: timeline detail: navigation ------------------------------------

describe('RecordingsTab — timeline detail: navigation', () => {
  test('expanded detail shows full from_url and to_url (not just hostnames)', async () => {
    backendState.recordings.activeDetailRecordingId = 'rec-0001';
    backendState.recordings.detailRecording = makeDetailRecording({
      entries: [
        {
          kind: 'navigation' as const,
          seq: 1,
          timestamp_ms: 1700000005000,
          from_url: 'https://example.com/path/to/page?q=test',
          to_url: 'https://other.example.org/new/destination',
        },
      ],
    });
    const { container } = render(RecordingsTab, {});
    await fireEvent.click(container.querySelector('.timeline-entry__row')!);
    const detail = container.querySelector('.timeline-entry__detail');
    expect(detail).not.toBeNull();
    // Full URLs (not just hostnames like compact row shows)
    expect(detail!.textContent).toContain('https://example.com/path/to/page?q=test');
    expect(detail!.textContent).toContain('https://other.example.org/new/destination');
  });
});

// --- Tests: timeline detail: transcript_segment ----------------------------

describe('RecordingsTab — timeline detail: transcript_segment', () => {
  test('expanded detail shows full text and timing range', async () => {
    backendState.recordings.activeDetailRecordingId = 'rec-0001';
    backendState.recordings.detailRecording = makeDetailRecording({
      entries: [
        {
          kind: 'transcript_segment' as const,
          seq: 5,
          timestamp_ms: 1700000003000,
          start_ms: 3000,
          end_ms: 6500,
          text: 'This is the full narration text for the transcript',
          backend_id: 'mlx_whisper',
        },
      ],
    });
    const { container } = render(RecordingsTab, {});
    await fireEvent.click(container.querySelector('.timeline-entry__row')!);
    const detail = container.querySelector('.timeline-entry__detail');
    expect(detail).not.toBeNull();
    expect(detail!.textContent).toContain('This is the full narration text for the transcript');
    // start timing visible in some form (3.0s or 3s or 3000)
    expect(detail!.textContent).toMatch(/3[.,]?0?s|3000/);
    // end timing visible
    expect(detail!.textContent).toMatch(/6[.,]?5s|6500/);
  });
});

// --- Tests: timeline detail: assertion -------------------------------------

describe('RecordingsTab — timeline detail: assertion', () => {
  test('expanded assertion detail shows type, target, expected, comparator', async () => {
    backendState.recordings.activeDetailRecordingId = 'rec-0001';
    backendState.recordings.detailRecording = makeDetailRecording({
      entries: [
        {
          kind: 'assertion' as const,
          seq: 1,
          timestamp_ms: 1700000005000,
          assertion_id: 'assert-001-uuid',
          assertion_type: 'text_contains',
          target: 'h1.title',
          target_kind: 'selector',
          expected: 'Welcome',
          comparator: 'contains',
          description: 'Page has welcome heading',
        },
      ],
    });
    const { container } = render(RecordingsTab, {});
    await fireEvent.click(container.querySelector('.timeline-entry__row')!);
    const detail = container.querySelector('.timeline-entry__detail');
    expect(detail).not.toBeNull();
    expect(detail!.textContent).toContain('text_contains');
    expect(detail!.textContent).toContain('h1.title');
    expect(detail!.textContent).toContain('Welcome');
    expect(detail!.textContent).toContain('contains');
  });
});
