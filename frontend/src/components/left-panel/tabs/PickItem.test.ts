/**
 * PickItem component tests.
 *
 * Covers:
 * - Renders tag, selector
 * - Active state: pick--active class when pick_id matches activePickId
 * - Inactive state: no pick--active class
 * - text_snippet preview shown when present, hidden when absent
 * - comment preview shown when present
 * - Click → selectPick (via bridge send)
 * - Delete button → deletePick (via bridge send)
 */
const send = vi.hoisted(() => vi.fn());
vi.mock('../../../bridge/bridge.svelte', () => ({ bridge: { send } }));

import { describe, expect, test, vi, afterEach, beforeEach } from 'vitest';
import { render, cleanup, fireEvent } from '@testing-library/svelte';
import PickItem from './PickItem.svelte';
import { backendState } from '../../../backend-state/backend-state.svelte';
import type { Pick } from '../../../_generated/state';

afterEach(() => {
  cleanup();
  send.mockClear();
  backendState.inspector.activePickId = null;
});

beforeEach(() => {
  backendState.inspector.activePickId = null;
});

function makePick(overrides: Partial<Pick> = {}): Pick {
  return {
    pick_id: 'pick-001',
    url: 'https://example.com',
    timestamp_ms: 0,
    color_index: 0,
    element: {
      selector: 'div.main',
      fingerprint: {
        tag: 'div',
        attributes: {},
        text: '',
        path: [],
        parent_name: '',
        parent_attribs: {},
        siblings: [],
      },
      text_snippet: null,
      rect: { x: 0, y: 0, width: 100, height: 100 },
    },
    comment: null,
    ...overrides,
  } as unknown as Pick;
}

describe('PickItem — basic rendering', () => {
  test('renders the tag', () => {
    const { getByText } = render(PickItem, { pick: makePick() });
    expect(getByText('div')).toBeTruthy();
  });

  test('renders the selector', () => {
    const { getByText } = render(PickItem, { pick: makePick({ element: { selector: '#my-btn', fingerprint: { tag: 'button', attributes: {}, text: '', path: [], parent_name: '', parent_attribs: {}, siblings: [] }, text_snippet: null, rect: { x: 0, y: 0, width: 50, height: 30 } } as any }) });
    expect(getByText('#my-btn')).toBeTruthy();
  });

  test('delete button is rendered', () => {
    const { getByTitle } = render(PickItem, { pick: makePick() });
    expect(getByTitle('Pick löschen')).toBeTruthy();
  });
});

describe('PickItem — active state', () => {
  test('adds pick--active class when activePickId matches', () => {
    const pick = makePick({ pick_id: 'pick-active' });
    backendState.inspector.activePickId = 'pick-active';
    const { container } = render(PickItem, { pick });
    expect(container.querySelector('.pick--active')).not.toBeNull();
  });

  test('no pick--active class when activePickId is null', () => {
    const pick = makePick({ pick_id: 'pick-001' });
    backendState.inspector.activePickId = null;
    const { container } = render(PickItem, { pick });
    expect(container.querySelector('.pick--active')).toBeNull();
  });

  test('no pick--active class when activePickId is different', () => {
    const pick = makePick({ pick_id: 'pick-001' });
    backendState.inspector.activePickId = 'pick-other';
    const { container } = render(PickItem, { pick });
    expect(container.querySelector('.pick--active')).toBeNull();
  });
});

describe('PickItem — preview text', () => {
  test('shows text_snippet when present', () => {
    const pick = makePick();
    (pick.element as any).text_snippet = 'Submit form';
    const { getByText } = render(PickItem, { pick });
    expect(getByText('Submit form')).toBeTruthy();
  });

  test('no preview when text_snippet is null', () => {
    const pick = makePick();
    (pick.element as any).text_snippet = null;
    const { container } = render(PickItem, { pick });
    expect(container.querySelector('.pick__preview')).toBeNull();
  });

  test('shows comment preview when present', () => {
    const pick = makePick({ comment: 'My annotation' });
    const { getByText } = render(PickItem, { pick });
    expect(getByText(/My annotation/)).toBeTruthy();
  });

  test('no comment when comment is null', () => {
    const pick = makePick({ comment: undefined });
    const { container } = render(PickItem, { pick });
    expect(container.querySelector('.pick__comment')).toBeNull();
  });

  test('no comment when comment is empty string', () => {
    const pick = makePick({ comment: '' });
    const { container } = render(PickItem, { pick });
    expect(container.querySelector('.pick__comment')).toBeNull();
  });
});

describe('PickItem — interactions', () => {
  test('click on pick row sends pick_selected_requested', () => {
    const pick = makePick({ pick_id: 'pick-click' });
    const { container } = render(PickItem, { pick });
    const row = container.querySelector('.pick') as HTMLElement;
    fireEvent.click(row);
    expect(send).toHaveBeenCalledWith(
      expect.objectContaining({ kind: 'pick_selected_requested', pick_id: 'pick-click' })
    );
  });

  test('click on delete button sends pick_deleted_requested', () => {
    const pick = makePick({ pick_id: 'pick-del' });
    const { getByTitle } = render(PickItem, { pick });
    const deleteBtn = getByTitle('Pick löschen');
    fireEvent.click(deleteBtn);
    expect(send).toHaveBeenCalledWith(
      expect.objectContaining({ kind: 'pick_deleted_requested', pick_id: 'pick-del' })
    );
  });
});
