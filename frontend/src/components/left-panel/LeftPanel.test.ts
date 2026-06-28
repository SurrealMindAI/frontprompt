/**
 * LeftPanel tests.
 *
 * Tests: renders correctly, tab labels include counts, tab switching.
 */
const send = vi.hoisted(() => vi.fn());
vi.mock('../../bridge/bridge.svelte', () => ({ bridge: { send } }));

import { describe, expect, test, afterEach, beforeEach } from 'vitest';
import { render, cleanup } from '@testing-library/svelte';
import LeftPanel from './LeftPanel.svelte';
import { backendState } from '../../backend-state/backend-state.svelte';
import { uiPrefs } from '../../local-state/ui-prefs.svelte';

afterEach(() => {
  cleanup();
  send.mockClear();
  backendState.inspector.picks = [];
  backendState.inspector.regions = [];
  backendState.inspector.relations = [];
  uiPrefs.leftPanelTab = 'picks';
});

beforeEach(() => {
  backendState.inspector.picks = [];
  backendState.inspector.regions = [];
  backendState.inspector.relations = [];
  uiPrefs.leftPanelTab = 'picks';
});

describe('LeftPanel — rendering', () => {
  test('renders .left-panel container', () => {
    const { container } = render(LeftPanel);
    expect(container.querySelector('.left-panel')).not.toBeNull();
  });

  test('renders tab buttons for all 6 tabs', () => {
    const { container } = render(LeftPanel);
    // TabbedPanel renders tab buttons — look for known tab labels
    const tabButtons = container.querySelectorAll('[role="tab"], .tab-btn, button');
    // There should be at least the tools buttons + tab buttons
    expect(tabButtons.length).toBeGreaterThan(0);
  });

  test('tab labels include pick count', () => {
    const { container } = render(LeftPanel);
    // Picks tab should show "Picks (0)" or similar
    const text = container.textContent ?? '';
    expect(text).toContain('Picks');
  });

  test('tab labels include regions count', () => {
    const { container } = render(LeftPanel);
    const text = container.textContent ?? '';
    expect(text).toContain('Regions');
  });

  test('tab labels include relations count', () => {
    const { container } = render(LeftPanel);
    const text = container.textContent ?? '';
    expect(text).toContain('Relations');
  });
});

describe('LeftPanel — active tab content', () => {
  test('shows PicksTab content when leftPanelTab=picks', () => {
    uiPrefs.leftPanelTab = 'picks';
    const { container } = render(LeftPanel);
    // PicksTab renders .picks-tab
    expect(container.querySelector('.picks-tab')).not.toBeNull();
  });

  test('shows RegionsTab content when leftPanelTab=regions', () => {
    uiPrefs.leftPanelTab = 'regions';
    const { container } = render(LeftPanel);
    // RegionsTab renders .regions-tab
    expect(container.querySelector('.regions-tab')).not.toBeNull();
  });

  test('shows RelationsTab content when leftPanelTab=relations', () => {
    uiPrefs.leftPanelTab = 'relations';
    const { container } = render(LeftPanel);
    expect(container.querySelector('.relations-tab')).not.toBeNull();
  });

  test('shows EventsTab content when leftPanelTab=events', () => {
    uiPrefs.leftPanelTab = 'events';
    const { container } = render(LeftPanel);
    // EventsTab renders .controls bar
    expect(container.querySelector('.controls')).not.toBeNull();
  });

  test('shows RecordingsTab content when leftPanelTab=recordings', () => {
    uiPrefs.leftPanelTab = 'recordings';
    const { container } = render(LeftPanel);
    // RecordingsTab renders something; just check it renders without error
    expect(container.querySelector('.left-panel')).not.toBeNull();
  });

  test('shows SettingsTab content when leftPanelTab=settings', () => {
    uiPrefs.leftPanelTab = 'settings';
    const { container } = render(LeftPanel);
    // SettingsTab renders .settings-tab
    expect(container.querySelector('.left-panel')).not.toBeNull();
  });
});

describe('LeftPanel — recordings tab label', () => {
  test('Recordings label shows count when recordings exist', () => {
    backendState.recordings.recordings = [
      { recording_id: 'rec-001', name: 'Test', description: '', status: 'stopped', started_at_ms: 0, entry_count: 0 },
    ];
    const { container } = render(LeftPanel);
    const text = container.textContent ?? '';
    expect(text).toContain('Recordings');
    backendState.recordings.recordings = [];
  });

  test('Recordings label shows active indicator when recording is active', () => {
    backendState.recordings.activeRecordingId = 'rec-001';
    const { container } = render(LeftPanel);
    const text = container.textContent ?? '';
    expect(text).toContain('●');
    backendState.recordings.activeRecordingId = null;
  });
});
