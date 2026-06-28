/**
 * RightPanel tests.
 *
 * Tests: empty state, PickDetails rendering when pick active,
 * RegionDetails rendering when region active, RecordingDetails when recording detail active.
 */
const send = vi.hoisted(() => vi.fn());
vi.mock('../../bridge/bridge.svelte', () => ({ bridge: { send } }));

import { describe, expect, test, afterEach, beforeEach } from 'vitest';
import { render, cleanup } from '@testing-library/svelte';
import RightPanel from './RightPanel.svelte';
import { backendState } from '../../backend-state/backend-state.svelte';

afterEach(() => {
  cleanup();
  send.mockClear();
  backendState.inspector.picks = [];
  backendState.inspector.regions = [];
  backendState.inspector.relations = [];
  backendState.inspector.activePickId = null;
  backendState.inspector.activeRegionId = null;
  backendState.recordings.detailRecording = null;
});

const PICK = {
  pick_id: 'pick-rp-001',
  session_id: 'sess',
  timestamp_ms: 1700000000000,
  url: 'https://example.com',
  comment: '',
  element: {
    selector: '#test-btn',
    tag: 'button',
    text_snippet: null,
    fingerprint: {
      tag: 'button',
      attributes: {},
      path: [],
      siblings_count: 0,
    },
  },
} as any;

const REGION = {
  region_id: 'reg-rp-001',
  rect: { x: 0, y: 0, width: 100, height: 50 },
  member_pick_ids: [],
  timestamp_ms: 0,
  note: null,
  color_index: 0,
  viewport_snapshot: null,
} as any;

describe('RightPanel — empty state', () => {
  test('shows empty state when no pick or region selected', () => {
    const { getByText } = render(RightPanel);
    expect(getByText('Nichts selektiert.')).toBeTruthy();
  });

  test('renders .right-panel container', () => {
    const { container } = render(RightPanel);
    expect(container.querySelector('.right-panel')).not.toBeNull();
  });
});

describe('RightPanel — active pick', () => {
  beforeEach(() => {
    backendState.inspector.picks = [PICK];
    backendState.inspector.activePickId = 'pick-rp-001';
  });

  test('shows PickDetails when a pick is active', () => {
    const { container } = render(RightPanel);
    // PickDetails renders a dl.details element
    expect(container.querySelector('dl.details')).not.toBeNull();
  });

  test('does not show empty state when pick is active', () => {
    const { container } = render(RightPanel);
    expect(container.textContent).not.toContain('Nichts selektiert.');
  });
});

describe('RightPanel — active region', () => {
  beforeEach(() => {
    backendState.inspector.regions = [REGION];
    backendState.inspector.activeRegionId = 'reg-rp-001';
  });

  test('shows RegionDetails when a region is active', () => {
    const { container } = render(RightPanel);
    // RegionDetails renders a dl.details element (same as PickDetails root)
    expect(container.querySelector('dl.details')).not.toBeNull();
  });

  test('does not show empty state when region is active', () => {
    const { container } = render(RightPanel);
    expect(container.textContent).not.toContain('Nichts selektiert.');
  });
});
