/**
 * PicksTab tests.
 *
 * Tests: group header renders, items render when picks are in backendState.
 * Note: empty state (groups.length === 0) is unreachable in jsdom test env
 * because visibleGroups() always returns the "(all)" group.
 */
const send = vi.hoisted(() => vi.fn());
vi.mock('../../../bridge/bridge.svelte', () => ({ bridge: { send } }));

import { describe, expect, test, afterEach, beforeEach } from 'vitest';
import { render, cleanup } from '@testing-library/svelte';
import PicksTab from './PicksTab.svelte';
import { backendState } from '../../../backend-state/backend-state.svelte';
import { overlayContext } from '../../../services/context/overlay-context.svelte';

afterEach(() => {
  cleanup();
  send.mockClear();
  backendState.inspector.picks = [];
  overlayContext.resetForTests();
});

beforeEach(() => {
  backendState.inspector.picks = [];
});

const PICK_A = {
  pick_id: 'pick-pt-001',
  session_id: null, // owned pick (currentSessionId=null in tests → all are "own" from (all) group)
  timestamp_ms: 1700000000000,
  url: 'https://example.com',
  element: {
    selector: '#test-button',
    tag: 'button',
    text_snippet: null,
    fingerprint: { tag: 'button', attributes: {}, path: [], siblings_count: 0 },
  },
} as any;

const PICK_B = {
  pick_id: 'pick-pt-002',
  session_id: null,
  timestamp_ms: 1700000001000,
  url: 'https://example.com',
  element: {
    selector: '.nav-link',
    tag: 'a',
    text_snippet: 'Home',
    fingerprint: { tag: 'a', attributes: {}, path: [], siblings_count: 0 },
  },
} as any;

describe('PicksTab — group header', () => {
  test('renders group header "(all)" when picks exist', () => {
    backendState.inspector.picks = [PICK_A];
    const { getByText } = render(PicksTab);
    expect(getByText('(all)')).toBeTruthy();
  });

  test('renders group header even with no picks (visibleGroups always returns the (all) group)', () => {
    backendState.inspector.picks = [];
    const { getByText } = render(PicksTab);
    expect(getByText('(all)')).toBeTruthy();
  });

  test('renders .picks-tab container', () => {
    const { container } = render(PicksTab);
    expect(container.querySelector('.picks-tab')).not.toBeNull();
  });
});

describe('PicksTab — overlay context branches', () => {
  test('hostname() non-null covers ?? left branch (line 20: overlayContext.hostname() ?? "")', () => {
    // When URL is set, hostname() returns a string (non-null) → ?? '' left side taken.
    // currentSessionId=null so visibleGroups returns "(all)" group as usual.
    overlayContext.setForTests({ url: new URL('https://example.com'), currentSessionId: null });
    const { container } = render(PicksTab);
    expect(container.querySelector('.picks-tab')).not.toBeNull();
  });

  test('empty state renders when sessionId is set but no picks exist (line 27: groups.length===0 TRUE)', () => {
    // With currentSessionId non-null and no picks, visibleGroups returns [] → empty div.
    overlayContext.setForTests({ url: new URL('https://example.com'), currentSessionId: 'test-sess' });
    backendState.inspector.picks = [];
    const { container } = render(PicksTab);
    expect(container.querySelector('.empty')).not.toBeNull();
  });
});

describe('PicksTab — pick items', () => {
  test('renders .row elements for each pick', () => {
    backendState.inspector.picks = [PICK_A, PICK_B];
    const { container } = render(PicksTab);
    const rows = container.querySelectorAll('.row');
    expect(rows.length).toBe(2);
  });

  test('renders PickItem with pick selector text', () => {
    backendState.inspector.picks = [PICK_A];
    const { getByText } = render(PicksTab);
    expect(getByText('#test-button')).toBeTruthy();
  });

  test('renders list container when picks exist', () => {
    backendState.inspector.picks = [PICK_A];
    const { container } = render(PicksTab);
    expect(container.querySelector('.list')).not.toBeNull();
  });
});
