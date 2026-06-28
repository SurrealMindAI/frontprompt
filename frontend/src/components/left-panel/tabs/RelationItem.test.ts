/**
 * RelationItem smoke tests.
 *
 * Tests rendering of pick↔pick relations (labels, kind badge, arrow),
 * the hover state, edit popover, and delete action.
 */
const send = vi.hoisted(() => vi.fn());
vi.mock('../../../bridge/bridge.svelte', () => ({ bridge: { send } }));

import { describe, expect, test, afterEach, beforeEach } from 'vitest';
import { render, cleanup, fireEvent } from '@testing-library/svelte';
import RelationItem from './RelationItem.svelte';
import { backendState } from '../../../backend-state/backend-state.svelte';
import type { Relation } from '../../../_generated/state';

const PICK_A = {
  pick_id: 'pick-a',
  element: {
    selector: '#btn-save',
    tag: 'button',
    fingerprint: { path: [], tag: 'button', attributes: {}, siblings_count: 0 },
  },
  session_id: 'sess-1',
  timestamp_ms: 0,
};

const PICK_B = {
  pick_id: 'pick-b',
  element: {
    selector: '#btn-cancel',
    tag: 'button',
    fingerprint: { path: [], tag: 'button', attributes: {}, siblings_count: 0 },
  },
  session_id: 'sess-1',
  timestamp_ms: 0,
};

const RELATION_RELATES_TO: Relation = {
  relation_id: 'rel-001',
  source_id: 'pick-a',
  source_kind: 'pick',
  target_id: 'pick-b',
  target_kind: 'pick',
  kind: 'relates_to',
  note: null,
  timestamp_ms: 0,
};

const RELATION_TRIGGERS: Relation = {
  relation_id: 'rel-002',
  source_id: 'pick-a',
  source_kind: 'pick',
  target_id: 'pick-b',
  target_kind: 'pick',
  kind: 'triggers',
  note: 'opens modal',
  timestamp_ms: 0,
};

beforeEach(() => {
  backendState.inspector.picks = [PICK_A as any, PICK_B as any];
  backendState.inspector.regions = [];
});

afterEach(() => {
  cleanup();
  send.mockClear();
  backendState.inspector.picks = [];
  backendState.inspector.relations = [];
});

describe('RelationItem — rendering', () => {
  test('renders source selector label', () => {
    const { getByText } = render(RelationItem, { relation: RELATION_RELATES_TO });
    expect(getByText('#btn-save')).toBeTruthy();
  });

  test('renders target selector label', () => {
    const { getByText } = render(RelationItem, { relation: RELATION_RELATES_TO });
    expect(getByText('#btn-cancel')).toBeTruthy();
  });

  test('renders kind badge with "relates_to"', () => {
    const { getByText } = render(RelationItem, { relation: RELATION_RELATES_TO });
    expect(getByText('relates_to')).toBeTruthy();
  });

  test('renders kind badge with "triggers"', () => {
    const { getByText } = render(RelationItem, { relation: RELATION_TRIGGERS });
    expect(getByText('triggers')).toBeTruthy();
  });

  test('renders bidirectional arrow ↔ for relates_to', () => {
    const { container } = render(RelationItem, { relation: RELATION_RELATES_TO });
    const arrows = container.querySelectorAll('.rel-item__arrow');
    expect(arrows.length).toBeGreaterThan(0);
    expect(arrows[0]!.textContent).toBe('↔');
  });

  test('renders directed arrow → for triggers', () => {
    const { container } = render(RelationItem, { relation: RELATION_TRIGGERS });
    const arrows = container.querySelectorAll('.rel-item__arrow');
    expect(arrows[0]!.textContent).toBe('→');
  });

  test('renders note when relation has note', () => {
    const { getByText } = render(RelationItem, { relation: RELATION_TRIGGERS });
    expect(getByText('opens modal')).toBeTruthy();
  });

  test('does not render note div when note is null', () => {
    const { container } = render(RelationItem, { relation: RELATION_RELATES_TO });
    expect(container.querySelector('.rel-item__note')).toBeNull();
  });

  test('renders Edit relation button', () => {
    const { container } = render(RelationItem, { relation: RELATION_RELATES_TO });
    const editBtn = container.querySelector('[aria-label="Edit relation"]');
    expect(editBtn).not.toBeNull();
  });

  test('renders Delete relation button', () => {
    const { container } = render(RelationItem, { relation: RELATION_RELATES_TO });
    const deleteBtn = container.querySelector('[aria-label="Delete relation"]');
    expect(deleteBtn).not.toBeNull();
  });

  test('renders listitem role', () => {
    const { container } = render(RelationItem, { relation: RELATION_RELATES_TO });
    expect(container.querySelector('[role="listitem"]')).not.toBeNull();
  });

  test('shows "(missing)" for unknown pick id', () => {
    const unknownPick: Relation = {
      ...RELATION_RELATES_TO,
      source_id: 'unknown-pick',
    };
    const { getByText } = render(RelationItem, { relation: unknownPick });
    expect(getByText('(missing)')).toBeTruthy();
  });
});

describe('RelationItem — edit popover', () => {
  test('clicking edit button opens edit panel', () => {
    const { container } = render(RelationItem, { relation: RELATION_RELATES_TO });
    const editBtn = container.querySelector('[aria-label="Edit relation"]') as HTMLButtonElement;
    fireEvent.click(editBtn);
    expect(container.querySelector('.rel-item__edit')).not.toBeNull();
  });

  test('edit panel has cancel and save buttons', () => {
    const { container, getByText } = render(RelationItem, { relation: RELATION_RELATES_TO });
    const editBtn = container.querySelector('[aria-label="Edit relation"]') as HTMLButtonElement;
    fireEvent.click(editBtn);
    expect(getByText('cancel')).toBeTruthy();
    expect(getByText('save')).toBeTruthy();
  });

  test('clicking cancel in edit panel closes the popover', () => {
    const { container, getByText } = render(RelationItem, { relation: RELATION_RELATES_TO });
    const editBtn = container.querySelector('[aria-label="Edit relation"]') as HTMLButtonElement;
    fireEvent.click(editBtn);
    fireEvent.click(getByText('cancel'));
    expect(container.querySelector('.rel-item__edit')).toBeNull();
  });

  test('clicking save calls bridge.send (updateRelation)', () => {
    const { container, getByText } = render(RelationItem, { relation: RELATION_RELATES_TO });
    const editBtn = container.querySelector('[aria-label="Edit relation"]') as HTMLButtonElement;
    fireEvent.click(editBtn);
    fireEvent.click(getByText('save'));
    expect(send).toHaveBeenCalled();
  });
});

describe('RelationItem — delete', () => {
  test('clicking delete calls bridge.send (deleteRelation)', () => {
    const { container } = render(RelationItem, { relation: RELATION_RELATES_TO });
    const deleteBtn = container.querySelector('[aria-label="Delete relation"]') as HTMLButtonElement;
    fireEvent.click(deleteBtn);
    expect(send).toHaveBeenCalled();
  });
});

describe('RelationItem — source/target click', () => {
  test('clicking source button calls bridge.send (selectPick)', () => {
    const { container } = render(RelationItem, { relation: RELATION_RELATES_TO });
    const sourceBtns = container.querySelectorAll('.rel-item__node');
    fireEvent.click(sourceBtns[0]!);
    expect(send).toHaveBeenCalled();
  });

  test('clicking target button calls bridge.send (selectPick)', () => {
    const { container } = render(RelationItem, { relation: RELATION_RELATES_TO });
    const targetBtns = container.querySelectorAll('.rel-item__node');
    fireEvent.click(targetBtns[targetBtns.length - 1]!);
    expect(send).toHaveBeenCalled();
  });
});

describe('RelationItem — hover state', () => {
  test('mouseenter on rel-item sets hoveredRelationId (covers onmouseenter handler)', () => {
    const { container } = render(RelationItem, { relation: RELATION_RELATES_TO });
    const item = container.querySelector('.rel-item') as HTMLElement;
    expect(() => fireEvent.mouseEnter(item)).not.toThrow();
    // Item gets hovered class after mouseenter
    expect(item.classList.contains('rel-item--hovered')).toBe(true);
  });

  test('mouseleave on rel-item clears hoveredRelationId (covers onmouseleave handler)', () => {
    const { container } = render(RelationItem, { relation: RELATION_RELATES_TO });
    const item = container.querySelector('.rel-item') as HTMLElement;
    fireEvent.mouseEnter(item);
    expect(item.classList.contains('rel-item--hovered')).toBe(true);
    fireEvent.mouseLeave(item);
    expect(item.classList.contains('rel-item--hovered')).toBe(false);
  });
});

describe('RelationItem — region endpoint click (selectEndpoint else branch)', () => {
  test('clicking target button when target_kind=region calls bridge.send (selectRegion) — covers line 46 else branch', () => {
    const REGION_CLICK = {
      region_id: 'reg-click',
      note: 'Clickable Region',
      member_pick_ids: [],
      rect: { x: 0, y: 0, width: 100, height: 50 },
      color_index: 0,
      viewport_snapshot: null,
      origin_session: null,
    };
    backendState.inspector.regions = [REGION_CLICK as any];
    const RELATION_PICK_TO_REGION: Relation = {
      relation_id: 'rel-click-region',
      source_id: 'pick-a',
      source_kind: 'pick',
      target_id: 'reg-click',
      target_kind: 'region',
      kind: 'relates_to',
      note: null,
      timestamp_ms: 0,
    };
    const { container } = render(RelationItem, { relation: RELATION_PICK_TO_REGION });
    const targetBtns = container.querySelectorAll('.rel-item__node');
    // Target button is the last rel-item__node
    fireEvent.click(targetBtns[targetBtns.length - 1]!);
    // selectRegion triggers a bridge send (region_selected_requested)
    expect(send).toHaveBeenCalled();
  });
});

describe('RelationItem — edit popover interactions (covers lines 147, 152)', () => {
  test('changing dropdown selection fires onChange callback — covers line 147: (v) => (editKind = v)', () => {
    const { container } = render(RelationItem, { relation: RELATION_RELATES_TO });
    const editBtn = container.querySelector('[aria-label="Edit relation"]') as HTMLButtonElement;
    fireEvent.click(editBtn);
    // Dropdown is a CUSTOM component — no native <select>. Interaction:
    // 1. click the trigger button to open the panel
    // 2. click an option button to call onChange
    const dropdownTrigger = container.querySelector('.dropdown__trigger') as HTMLButtonElement;
    expect(dropdownTrigger).not.toBeNull();
    fireEvent.click(dropdownTrigger); // opens panel
    const options = container.querySelectorAll('.dropdown__option');
    const triggersOption = Array.from(options).find((o) =>
      o.textContent?.includes('triggers')
    ) as HTMLButtonElement;
    expect(triggersOption).not.toBeNull();
    fireEvent.click(triggersOption); // calls onChange('triggers') → editKind = 'triggers'
    // Save to confirm editKind was updated (bridge.send will be called)
    const saveBtn = container.querySelector('.btn-mini--primary') as HTMLButtonElement;
    fireEvent.click(saveBtn);
    expect(send).toHaveBeenCalled();
  });

  test('typing in note textarea updates editNote — covers line 152: bind:value={editNote}', () => {
    const { container } = render(RelationItem, { relation: RELATION_RELATES_TO });
    const editBtn = container.querySelector('[aria-label="Edit relation"]') as HTMLButtonElement;
    fireEvent.click(editBtn);
    const textarea = container.querySelector('textarea') as HTMLTextAreaElement;
    expect(textarea).not.toBeNull();
    // Svelte bind:value fires on 'input' event. Set the value then dispatch.
    textarea.value = 'new note text';
    fireEvent.input(textarea);
    // Save: the note should be sent
    const saveBtn = container.querySelector('.btn-mini--primary') as HTMLButtonElement;
    fireEvent.click(saveBtn);
    expect(send).toHaveBeenCalledWith(
      expect.objectContaining({ kind: 'relation_updated_requested', note: 'new note text' })
    );
  });
});

describe('RelationItem — region endpoint label', () => {
  test('region endpoint with note uses note as label', () => {
    // endpointLabel with nodeKind='region' → looks up region by id → uses r.note if present
    const REGION_A = {
      region_id: 'reg-001',
      note: 'Hero Section',
      member_pick_ids: [],
      rect: { x: 0, y: 0, width: 100, height: 50 },
      color_index: 0,
      viewport_snapshot: null,
      origin_session: null,
    };
    backendState.inspector.regions = [REGION_A as any];
    const RELATION_PICK_TO_REGION: import('../../../_generated/state').Relation = {
      relation_id: 'rel-pick-region',
      source_id: 'pick-a',
      source_kind: 'pick',
      target_id: 'reg-001',
      target_kind: 'region',
      kind: 'relates_to',
      note: null,
      timestamp_ms: 0,
    };
    const { getByText } = render(RelationItem, { relation: RELATION_PICK_TO_REGION });
    expect(getByText('Hero Section')).toBeTruthy();
  });

  test('region endpoint without note falls back to region:<id-prefix> label', () => {
    // endpointLabel region path, r.note is null → uses `region:${nodeId.slice(0,6)}`
    const REGION_B = {
      region_id: 'reg-abc-def',
      note: null,
      member_pick_ids: [],
      rect: { x: 0, y: 0, width: 100, height: 50 },
      color_index: 0,
      viewport_snapshot: null,
      origin_session: null,
    };
    backendState.inspector.regions = [REGION_B as any];
    const RELATION_PICK_TO_REGION2: import('../../../_generated/state').Relation = {
      relation_id: 'rel-pick-reg2',
      source_id: 'pick-a',
      source_kind: 'pick',
      target_id: 'reg-abc-def',
      target_kind: 'region',
      kind: 'triggers',
      note: null,
      timestamp_ms: 0,
    };
    const { container } = render(RelationItem, { relation: RELATION_PICK_TO_REGION2 });
    expect(container.textContent).toContain('region:reg-ab');
  });
});
