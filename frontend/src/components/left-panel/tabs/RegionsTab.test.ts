/**
 * RegionsTab smoke tests.
 *
 * Tests the idle state (not drawing, no regions) and the draw mode UI.
 */
const send = vi.hoisted(() => vi.fn());
vi.mock('../../../bridge/bridge.svelte', () => ({ bridge: { send } }));

import { describe, expect, test, afterEach, beforeEach } from 'vitest';
import { render, cleanup, fireEvent } from '@testing-library/svelte';
import RegionsTab from './RegionsTab.svelte';
import { backendState } from '../../../backend-state/backend-state.svelte';
import { regionDraft } from '../../../services/regions';
import { overlayContext } from '../../../services/context/overlay-context.svelte';

afterEach(() => {
  cleanup();
  send.mockClear();
  backendState.inspector.regions = [];
  backendState.inspector.picks = [];
  regionDraft.cancel();
  overlayContext.resetForTests();
});

beforeEach(() => {
  regionDraft.cancel();
});

describe('RegionsTab — empty state (idle)', () => {
  test('renders + Draw region button', () => {
    const { getByText } = render(RegionsTab);
    expect(getByText('+ Draw region')).toBeTruthy();
  });

  test('shows group header "(all)" in null-session mode when regions empty', () => {
    // overlayContext.currentSessionId is null in test environment →
    // visibleGroups returns a single "(all)" bucket (even when empty).
    backendState.inspector.regions = [];
    const { getByText } = render(RegionsTab);
    expect(getByText('(all)')).toBeTruthy();
  });

  test('shows 0 regions count', () => {
    backendState.inspector.regions = [];
    const { container } = render(RegionsTab);
    const count = container.querySelector('.list-header__count');
    expect(count?.textContent).toBe('0 regions');
  });

  test('shows singular "region" when exactly 1 region — covers line 45 TRUE branch (? "" : "s")', () => {
    // regions.length === 1 → ternary TRUE → '' (no 's') → "1 region"
    backendState.inspector.regions = [
      { region_id: 'r-singular', origin_session: null, member_pick_ids: [], label: 'Solo' } as any,
    ];
    const { container } = render(RegionsTab);
    const count = container.querySelector('.list-header__count');
    expect(count?.textContent).toBe('1 region');
  });

  test('shows draw-region hint text', () => {
    const { getByText } = render(RegionsTab);
    expect(getByText(/Draw a rectangle on the page/)).toBeTruthy();
  });
});

describe('RegionsTab — entering draw mode', () => {
  test('clicking + Draw region button activates draft mode', () => {
    const { getByText } = render(RegionsTab);
    const btn = getByText('+ Draw region');
    fireEvent.click(btn);
    expect(regionDraft.drafting).toBe(true);
  });

  test('shows "Cancel region draw" when drafting is active', () => {
    regionDraft.start();
    const { getByText } = render(RegionsTab);
    expect(getByText('Cancel region draw')).toBeTruthy();
  });

  test('clicking Cancel region draw exits draft mode', () => {
    regionDraft.start();
    const { getByText } = render(RegionsTab);
    fireEvent.click(getByText('Cancel region draw'));
    expect(regionDraft.drafting).toBe(false);
  });

  test('shows drag hint when drafting active', () => {
    regionDraft.start();
    const { getByText } = render(RegionsTab);
    expect(getByText(/Drag a rect on the page to mark a region/)).toBeTruthy();
  });
});

// ---------------------------------------------------------------------------
// overlayContext coverage — hostname ?? '', empty groups, foreign class
// ---------------------------------------------------------------------------

describe('RegionsTab — overlayContext-driven branches', () => {
  test('non-null hostname covers ?? operator left branch (line 22)', () => {
    // hostname() returns 'example.com' (non-null) → ?? '' takes left branch (uses the value, not '')
    overlayContext.setForTests({ url: new URL('https://example.com'), currentSessionId: null });
    // With null session, visibleGroups still returns "(all)" group
    const { getByText } = render(RegionsTab);
    expect(getByText('(all)')).toBeTruthy();
  });

  test('empty groups TRUE branch: sessionId set + no regions → .empty div (line 49)', () => {
    // With a non-null sessionId and no regions, visibleGroups returns [] → groups.length === 0 TRUE
    overlayContext.setForTests({ url: new URL('https://example.com'), currentSessionId: 'sess-region-x' });
    backendState.inspector.regions = [];
    const { container } = render(RegionsTab);
    expect(container.querySelector('.empty')).not.toBeNull();
  });

  test('foreign region gets .foreign class when isOwned is false (line 61 TRUE)', () => {
    // region.origin_session !== currentSessionId → isOwned=false → class:foreign=true
    // region.member_pick_ids points to a pick on example.com → domain=currentHostname → included
    overlayContext.setForTests({ url: new URL('https://example.com'), currentSessionId: 'sess-a' });
    backendState.inspector.picks = [
      { pick_id: 'p-1', url: 'https://example.com/page', origin_session: 'sess-a' } as any,
    ];
    backendState.inspector.regions = [
      {
        region_id: 'r-1',
        origin_session: 'sess-b', // different session → isOwned=false
        member_pick_ids: ['p-1'],
        label: 'Foreign Region',
      } as any,
    ];
    const { container } = render(RegionsTab);
    expect(container.querySelector('.row.foreign')).not.toBeNull();
  });
});
