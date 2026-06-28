/**
 * RegionItem interaction tests — select, edit (start/commit/cancel), delete, keyboard.
 *
 * Separate file from RegionItem.test.ts (drift-indicator tests) to avoid
 * disturbing the mock-free drift test setup.
 */
const send = vi.hoisted(() => vi.fn());
vi.mock('../../../bridge/bridge.svelte', () => ({ bridge: { send } }));

import { describe, expect, test, afterEach } from 'vitest';
import { render, cleanup, fireEvent } from '@testing-library/svelte';
import RegionItem from './RegionItem.svelte';
import { backendState } from '../../../backend-state/backend-state.svelte';
import type { Region } from '../../../_generated/state';

afterEach(() => {
  cleanup();
  send.mockClear();
  backendState.inspector.regions = [];
});

function makeRegion(overrides: Partial<Region> = {}): Region {
  return {
    region_id: 'r-interact-001',
    rect: { x: 0, y: 0, width: 200, height: 100 },
    member_pick_ids: [],
    timestamp_ms: 0,
    color_index: 0,
    viewport_snapshot: null,
    note: null,
    ...overrides,
  };
}

describe('RegionItem — display name', () => {
  test('shows region:<id.slice(0,6)> when note is null', () => {
    const region = makeRegion({ region_id: 'r-abcdef', note: null });
    const { getByText } = render(RegionItem, { props: { region } });
    expect(getByText('region:r-abcd')).toBeTruthy();
  });

  test('shows note text when note is set', () => {
    const region = makeRegion({ note: 'Login Form' });
    const { getByText } = render(RegionItem, { props: { region } });
    expect(getByText('Login Form')).toBeTruthy();
  });

  test('shows member count badge', () => {
    const region = makeRegion({ member_pick_ids: ['pick-a', 'pick-b'] });
    const { container } = render(RegionItem, { props: { region } });
    const countBadge = container.querySelector('.region-item__count');
    expect(countBadge?.textContent?.trim()).toBe('2');
  });
});

describe('RegionItem — select interaction', () => {
  test('clicking the item calls backendState.inspector.selectRegion', async () => {
    const region = makeRegion();
    const { container } = render(RegionItem, { props: { region } });
    const item = container.querySelector('.region-item') as HTMLElement;
    await fireEvent.click(item);
    expect(send).toHaveBeenCalled();
  });

  test('pressing Enter on the item calls selectRegion', async () => {
    const region = makeRegion();
    const { container } = render(RegionItem, { props: { region } });
    const item = container.querySelector('.region-item') as HTMLElement;
    await fireEvent.keyDown(item, { key: 'Enter' });
    expect(send).toHaveBeenCalled();
  });

  test('pressing other key on item does NOT call selectRegion', async () => {
    const region = makeRegion();
    const { container } = render(RegionItem, { props: { region } });
    const item = container.querySelector('.region-item') as HTMLElement;
    await fireEvent.keyDown(item, { key: 'Space' });
    expect(send).not.toHaveBeenCalled();
  });
});

describe('RegionItem — active state', () => {
  test('has region-item--active class when it is the active region', () => {
    const region = makeRegion();
    backendState.inspector.activeRegionId = region.region_id;
    const { container } = render(RegionItem, { props: { region } });
    expect(container.querySelector('.region-item--active')).not.toBeNull();
    backendState.inspector.activeRegionId = null;
  });

  test('does not have region-item--active class when not active', () => {
    const region = makeRegion();
    backendState.inspector.activeRegionId = 'some-other-region';
    const { container } = render(RegionItem, { props: { region } });
    expect(container.querySelector('.region-item--active')).toBeNull();
    backendState.inspector.activeRegionId = null;
  });
});

describe('RegionItem — edit flow', () => {
  test('edit form is NOT shown initially', () => {
    const region = makeRegion();
    const { container } = render(RegionItem, { props: { region } });
    expect(container.querySelector('.region-item__edit')).toBeNull();
  });

  test('clicking edit button reveals edit form', async () => {
    const region = makeRegion({ note: 'original note' });
    const { container } = render(RegionItem, { props: { region } });
    const editBtn = container.querySelector('[aria-label="Edit region note"]') as HTMLElement;
    await fireEvent.click(editBtn);
    expect(container.querySelector('.region-item__edit')).not.toBeNull();
  });

  test('edit form contains textarea with region note', async () => {
    const region = makeRegion({ note: 'My Note' });
    const { container } = render(RegionItem, { props: { region } });
    const editBtn = container.querySelector('[aria-label="Edit region note"]') as HTMLElement;
    await fireEvent.click(editBtn);
    const ta = container.querySelector('.region-item__note-input') as HTMLTextAreaElement;
    expect(ta.value).toBe('My Note');
  });

  test('edit form has cancel and save buttons', async () => {
    const region = makeRegion();
    const { container, getByText } = render(RegionItem, { props: { region } });
    const editBtn = container.querySelector('[aria-label="Edit region note"]') as HTMLElement;
    await fireEvent.click(editBtn);
    expect(getByText('cancel')).toBeTruthy();
    expect(getByText('save')).toBeTruthy();
  });

  test('clicking cancel closes the edit form', async () => {
    const region = makeRegion();
    const { container, getByText } = render(RegionItem, { props: { region } });
    const editBtn = container.querySelector('[aria-label="Edit region note"]') as HTMLElement;
    await fireEvent.click(editBtn);
    const cancelBtn = getByText('cancel');
    await fireEvent.click(cancelBtn);
    expect(container.querySelector('.region-item__edit')).toBeNull();
  });

  test('clicking save calls bridge.send (updateRegion)', async () => {
    const region = makeRegion({ note: 'original' });
    const { container, getByText } = render(RegionItem, { props: { region } });
    const editBtn = container.querySelector('[aria-label="Edit region note"]') as HTMLElement;
    await fireEvent.click(editBtn);
    // Edit the note
    const ta = container.querySelector('.region-item__note-input') as HTMLTextAreaElement;
    ta.value = 'updated note';
    await fireEvent.input(ta);
    const saveBtn = getByText('save');
    await fireEvent.click(saveBtn);
    expect(send).toHaveBeenCalled();
  });

  test('clicking save closes the edit form', async () => {
    const region = makeRegion({ note: 'original' });
    const { container, getByText } = render(RegionItem, { props: { region } });
    const editBtn = container.querySelector('[aria-label="Edit region note"]') as HTMLElement;
    await fireEvent.click(editBtn);
    const saveBtn = getByText('save');
    await fireEvent.click(saveBtn);
    expect(container.querySelector('.region-item__edit')).toBeNull();
  });
});

describe('RegionItem — delete interaction', () => {
  test('clicking delete button calls bridge.send (deleteRegion)', async () => {
    const region = makeRegion();
    const { container } = render(RegionItem, { props: { region } });
    const deleteBtn = container.querySelector('[aria-label="Delete region"]') as HTMLElement;
    await fireEvent.click(deleteBtn);
    expect(send).toHaveBeenCalled();
  });

  test('delete click does NOT propagate to parent (no selectRegion call)', async () => {
    // Delete has e.stopPropagation() so the parent click handler (selectRegion) should not fire
    // We check by resetting send after the click — if only 1 call was made it's deleteRegion
    const region = makeRegion();
    const { container } = render(RegionItem, { props: { region } });
    const deleteBtn = container.querySelector('[aria-label="Delete region"]') as HTMLElement;
    send.mockClear();
    await fireEvent.click(deleteBtn);
    // deleteRegion sends exactly once; selectRegion would add a 2nd call
    // (stopPropagation prevents selectRegion from firing too)
    expect(send).toHaveBeenCalledTimes(1);
  });
});
