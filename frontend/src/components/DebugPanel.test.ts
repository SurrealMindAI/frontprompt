/**
 * DebugPanel tests.
 *
 * Tests: renders correctly, shows empty log, shows events,
 * formatTime/formatPayload coverage via event row rendering,
 * clear button, versionInfo branches.
 */
const send = vi.hoisted(() => vi.fn());
vi.mock('../bridge/bridge.svelte', () => ({ bridge: { send, addInterceptor: vi.fn(() => () => {}) } }));

import { describe, expect, test, afterEach, beforeEach } from 'vitest';
import { render, cleanup, fireEvent } from '@testing-library/svelte';
import DebugPanel from './DebugPanel.svelte';
import { localState } from '../local-state/local-state.svelte';

afterEach(() => {
  cleanup();
  send.mockClear();
  localState.bridgeLog.events = [];
});

beforeEach(() => {
  localState.bridgeLog.events = [];
});

describe('DebugPanel — empty state', () => {
  test('renders .debug container', () => {
    const { container } = render(DebugPanel);
    expect(container.querySelector('.debug')).not.toBeNull();
  });

  test('shows "no bridge events yet" message when log is empty', () => {
    const { getByText } = render(DebugPanel);
    expect(getByText(/no bridge events yet/)).toBeTruthy();
  });

  test('renders clear button with aria-label', () => {
    const { container } = render(DebugPanel);
    expect(container.querySelector('[aria-label="clear log"]')).not.toBeNull();
  });

  test('renders autoscroll checkbox', () => {
    const { container } = render(DebugPanel);
    const checkbox = container.querySelector('input[type="checkbox"]');
    expect(checkbox).not.toBeNull();
  });

  test('renders versions sidebar', () => {
    const { container } = render(DebugPanel);
    expect(container.querySelector('.versions')).not.toBeNull();
  });

  test('shows "(pending)" version info when window.__fp.version is not set', () => {
    const { container } = render(DebugPanel);
    // versionInfo is null when window.__fp.version is not available
    expect(container.querySelector('.versions-pending')).not.toBeNull();
  });

  test('renders role="log" aria-live="polite" on log area', () => {
    const { container } = render(DebugPanel);
    const logEl = container.querySelector('[role="log"]');
    expect(logEl).not.toBeNull();
    expect(logEl?.getAttribute('aria-live')).toBe('polite');
  });
});

describe('DebugPanel — event log rendering', () => {
  test('shows event rows when bridge events exist', () => {
    // Add a synthetic outbound event to the log
    localState.bridgeLog.events = [
      {
        seq: 1,
        timestamp_ms: Date.now(),
        direction: 'outbound',
        kind: 'overlay_ready',
        payload: { schema_version: '0.6.0' },
      },
    ];
    const { container } = render(DebugPanel);
    expect(container.querySelector('.row')).not.toBeNull();
    expect(container.querySelector('.empty')).toBeNull();
  });

  test('renders direction indicator ↑ for outbound events', () => {
    localState.bridgeLog.events = [
      {
        seq: 1,
        timestamp_ms: Date.now(),
        direction: 'outbound',
        kind: 'overlay_ready',
        payload: {},
      },
    ];
    const { container } = render(DebugPanel);
    const rows = container.querySelectorAll('.row');
    expect(rows.length).toBeGreaterThan(0);
    // outbound row shows ↑ indicator
    expect(rows[0]?.textContent).toContain('↑');
  });

  test('renders direction indicator ↓ for inbound events', () => {
    localState.bridgeLog.events = [
      {
        seq: 2,
        timestamp_ms: Date.now(),
        direction: 'inbound',
        kind: 'heartbeat',
        payload: { seq: 1 },
      },
    ];
    const { container } = render(DebugPanel);
    expect(container.querySelector('.row')?.textContent).toContain('↓');
  });

  test('renders ⚠ direction indicator for error events', () => {
    localState.bridgeLog.events = [
      {
        seq: 3,
        timestamp_ms: Date.now(),
        direction: 'error',
        kind: 'inbound_malformed',
        payload: {},
      },
    ];
    const { container } = render(DebugPanel);
    expect(container.querySelector('.row')?.textContent).toContain('⚠');
  });

  test('renders kind label in event row', () => {
    localState.bridgeLog.events = [
      {
        seq: 4,
        timestamp_ms: Date.now(),
        direction: 'outbound',
        kind: 'pick_selected_requested',
        payload: {},
      },
    ];
    const { container } = render(DebugPanel);
    expect(container.querySelector('.kind')?.textContent).toBe('pick_selected_requested');
  });

  test('shows error count in header when error events exist', () => {
    localState.bridgeLog.events = [
      {
        seq: 5,
        timestamp_ms: Date.now(),
        direction: 'error',
        kind: 'test_error',
        payload: {},
      },
    ];
    const { container } = render(DebugPanel);
    // Error count shows in header
    expect(container.querySelector('.err')).not.toBeNull();
  });
});

describe('DebugPanel — clear button', () => {
  test('clicking clear button empties the log', () => {
    localState.bridgeLog.events = [
      {
        seq: 1,
        timestamp_ms: Date.now(),
        direction: 'outbound',
        kind: 'overlay_ready',
        payload: {},
      },
    ];
    const { container } = render(DebugPanel);
    const clearBtn = container.querySelector('[aria-label="clear log"]') as HTMLButtonElement;
    fireEvent.click(clearBtn);
    expect(localState.bridgeLog.events).toHaveLength(0);
  });
});

describe('DebugPanel — version info rendering', () => {
  test('shows dl.kv with version details when window.__fp.version is set', () => {
    // Set up window.__fp.version
    const mockFp = ((_msg: unknown) => Promise.resolve(null)) as any;
    mockFp.version = {
      schema_version: '0.6.0',
      bundle_build_session: 'test-session-id-12345678',
      bundle_build_version: '2024-01-01T00:00:00.000Z',
      bundle_build_git_sha: 'abc123def456',
    };
    mockFp.dispatch = () => {};
    (window as any).__fp = mockFp;

    const { container } = render(DebugPanel);
    expect(container.querySelector('dl.kv')).not.toBeNull();

    delete (window as any).__fp;
  });
});
