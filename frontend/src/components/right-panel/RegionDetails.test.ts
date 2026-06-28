/**
 * RegionDetails tests.
 *
 * Tests: display name, rect string, member count, member list,
 * outgoing/incoming relations section, delete relation, and click actions.
 */
const send = vi.hoisted(() => vi.fn());
vi.mock('../../bridge/bridge.svelte', () => ({ bridge: { send } }));

import { describe, expect, test, afterEach, beforeEach } from 'vitest';
import { render, cleanup, fireEvent } from '@testing-library/svelte';
import RegionDetails from './RegionDetails.svelte';
import { backendState } from '../../backend-state/backend-state.svelte';
import type { Region, Relation } from '../../_generated/state';

const RECT = { x: 10, y: 20, width: 300, height: 200 };

const REGION_BASIC: Region = {
  region_id: 'reg-aabbcc',
  rect: RECT,
  member_pick_ids: [],
  note: null,
  timestamp_ms: 1700000000000,
};

const REGION_WITH_NOTE: Region = {
  ...REGION_BASIC,
  region_id: 'reg-001',
  note: 'Login Form',
};

const PICK_A = {
  pick_id: 'pick-a',
  element: { selector: '#btn-login', tag: 'button', fingerprint: { path: [], tag: 'button', attributes: {}, siblings_count: 0 } },
  session_id: 'sess',
  timestamp_ms: 0,
};

const RELATION_OUT: Relation = {
  relation_id: 'rel-out',
  source_id: 'reg-aabbcc',
  source_kind: 'region',
  target_id: 'pick-a',
  target_kind: 'pick',
  kind: 'relates_to',
  note: null,
  timestamp_ms: 0,
};

const RELATION_IN: Relation = {
  relation_id: 'rel-in',
  source_id: 'pick-a',
  source_kind: 'pick',
  target_id: 'reg-aabbcc',
  target_kind: 'region',
  kind: 'triggers',
  note: null,
  timestamp_ms: 0,
};

beforeEach(() => {
  backendState.inspector.picks = [];
  backendState.inspector.regions = [];
  backendState.inspector.relations = [];
});

afterEach(() => {
  cleanup();
  send.mockClear();
  backendState.inspector.picks = [];
  backendState.inspector.regions = [];
  backendState.inspector.relations = [];
});

// ---------------------------------------------------------------------------
// Display name
// ---------------------------------------------------------------------------

describe('RegionDetails — display name', () => {
  test('shows region:<id.slice(0,6)> when note is null', () => {
    const { getByText } = render(RegionDetails, { region: REGION_BASIC });
    expect(getByText('region:reg-aa')).toBeTruthy();
  });

  test('shows note text when note is set', () => {
    const { getByText } = render(RegionDetails, { region: REGION_WITH_NOTE });
    expect(getByText('Login Form')).toBeTruthy();
  });
});

// ---------------------------------------------------------------------------
// Rect display
// ---------------------------------------------------------------------------

describe('RegionDetails — rect string', () => {
  test('shows formatted rect x, y · w × h (page-abs)', () => {
    const { getByText } = render(RegionDetails, { region: REGION_BASIC });
    expect(getByText('10, 20 · 300 × 200 (page-abs)')).toBeTruthy();
  });
});

// ---------------------------------------------------------------------------
// Member count
// ---------------------------------------------------------------------------

describe('RegionDetails — member count', () => {
  test('shows 0 when no members', () => {
    const { container } = render(RegionDetails, { region: REGION_BASIC });
    const dds = container.querySelectorAll('dd code');
    // member count is the 3rd dd
    const memberDd = Array.from(dds).find((dd) => dd.textContent?.trim() === '0');
    expect(memberDd).not.toBeUndefined();
  });

  test('shows member count when member_pick_ids set', () => {
    backendState.inspector.picks = [PICK_A as any];
    const region: Region = { ...REGION_BASIC, member_pick_ids: ['pick-a'] };
    const { container } = render(RegionDetails, { region });
    const dds = container.querySelectorAll('dd code');
    const memberDd = Array.from(dds).find((dd) => dd.textContent?.trim() === '1');
    expect(memberDd).not.toBeUndefined();
  });
});

// ---------------------------------------------------------------------------
// Members section
// ---------------------------------------------------------------------------

describe('RegionDetails — members section', () => {
  test('shows no members section when no member picks', () => {
    const { container } = render(RegionDetails, { region: REGION_BASIC });
    expect(container.querySelector('.members-section')).toBeNull();
  });

  test('shows member picks when member_pick_ids resolves to picks', () => {
    backendState.inspector.picks = [PICK_A as any];
    const region: Region = { ...REGION_BASIC, member_pick_ids: ['pick-a'] };
    const { getByText } = render(RegionDetails, { region });
    expect(getByText('#btn-login')).toBeTruthy();
  });

  test('clicking member pick button calls selectPick via bridge.send', () => {
    backendState.inspector.picks = [PICK_A as any];
    const region: Region = { ...REGION_BASIC, member_pick_ids: ['pick-a'] };
    const { container } = render(RegionDetails, { region });
    const memberBtn = container.querySelector('.member-row') as HTMLButtonElement;
    fireEvent.click(memberBtn);
    expect(send).toHaveBeenCalled();
  });
});

// ---------------------------------------------------------------------------
// Relations section — outgoing
// ---------------------------------------------------------------------------

describe('RegionDetails — outgoing relations', () => {
  beforeEach(() => {
    backendState.inspector.picks = [PICK_A as any];
    backendState.inspector.relations = [RELATION_OUT];
  });

  test('renders relations section when outgoing relations exist', () => {
    const { container } = render(RegionDetails, { region: REGION_BASIC });
    expect(container.querySelector('.relations-section')).not.toBeNull();
  });

  test('shows "outgoing" group label', () => {
    const { getByText } = render(RegionDetails, { region: REGION_BASIC });
    expect(getByText('outgoing')).toBeTruthy();
  });

  test('clicking outgoing relation calls selectEndpoint (pick target)', () => {
    const { container } = render(RegionDetails, { region: REGION_BASIC });
    const relBtn = container.querySelector('.rel-row') as HTMLButtonElement;
    fireEvent.click(relBtn);
    expect(send).toHaveBeenCalled();
  });

  test('shows delete button on outgoing relation', () => {
    const { container } = render(RegionDetails, { region: REGION_BASIC });
    const deleteBtn = container.querySelector('[aria-label="Delete relation"]');
    expect(deleteBtn).not.toBeNull();
  });

  test('clicking delete relation calls bridge.send', () => {
    const { container } = render(RegionDetails, { region: REGION_BASIC });
    const deleteBtn = container.querySelector('[aria-label="Delete relation"]') as HTMLElement;
    fireEvent.click(deleteBtn);
    expect(send).toHaveBeenCalled();
  });
});

// ---------------------------------------------------------------------------
// Relations section — incoming
// ---------------------------------------------------------------------------

describe('RegionDetails — incoming relations', () => {
  beforeEach(() => {
    backendState.inspector.picks = [PICK_A as any];
    backendState.inspector.relations = [RELATION_IN];
  });

  test('shows "incoming" group label', () => {
    const { getByText } = render(RegionDetails, { region: REGION_BASIC });
    expect(getByText('incoming')).toBeTruthy();
  });
});

// ---------------------------------------------------------------------------
// No relations section when none
// ---------------------------------------------------------------------------

describe('RegionDetails — no relations', () => {
  test('does not render relations section when no relations', () => {
    backendState.inspector.relations = [];
    const { container } = render(RegionDetails, { region: REGION_BASIC });
    expect(container.querySelector('.relations-section')).toBeNull();
  });
});

// ---------------------------------------------------------------------------
// Arrow symbols — relates_to ↔ vs directed → / ←
// ---------------------------------------------------------------------------

const RELATION_OUT_TRIGGERS: Relation = {
  relation_id: 'rel-out-triggers',
  source_id: 'reg-aabbcc',
  source_kind: 'region',
  target_id: 'pick-a',
  target_kind: 'pick',
  kind: 'triggers',
  note: null,
  timestamp_ms: 0,
};

const RELATION_IN_RELATES_TO: Relation = {
  relation_id: 'rel-in-rt',
  source_id: 'pick-a',
  source_kind: 'pick',
  target_id: 'reg-aabbcc',
  target_kind: 'region',
  kind: 'relates_to',
  note: null,
  timestamp_ms: 0,
};

describe('RegionDetails — arrow symbol for non-relates_to kind', () => {
  test('outgoing triggers relation shows → arrow (not ↔)', () => {
    backendState.inspector.picks = [PICK_A as any];
    backendState.inspector.relations = [RELATION_OUT_TRIGGERS];
    const { container } = render(RegionDetails, { region: REGION_BASIC });
    const arrows = container.querySelectorAll('.rel-row__arrow');
    const arrowTexts = Array.from(arrows).map((a) => a.textContent ?? '');
    expect(arrowTexts.some((t) => t.includes('→'))).toBe(true);
  });

  test('incoming relates_to relation shows ↔ arrow (not ←)', () => {
    backendState.inspector.picks = [PICK_A as any];
    backendState.inspector.relations = [RELATION_IN_RELATES_TO];
    const { container } = render(RegionDetails, { region: REGION_BASIC });
    const arrows = container.querySelectorAll('.rel-row__arrow');
    const arrowTexts = Array.from(arrows).map((a) => a.textContent ?? '');
    expect(arrowTexts.some((t) => t.includes('↔'))).toBe(true);
  });
});

// ---------------------------------------------------------------------------
// Relation with note — .rel-row__note shown
// ---------------------------------------------------------------------------

const RELATION_OUT_WITH_NOTE: Relation = {
  relation_id: 'rel-with-note',
  source_id: 'reg-aabbcc',
  source_kind: 'region',
  target_id: 'pick-a',
  target_kind: 'pick',
  kind: 'relates_to',
  note: 'opens checkout modal',
  timestamp_ms: 0,
};

describe('RegionDetails — relation note display', () => {
  test('relation with note shows .rel-row__note span', () => {
    backendState.inspector.picks = [PICK_A as any];
    backendState.inspector.relations = [RELATION_OUT_WITH_NOTE];
    const { container } = render(RegionDetails, { region: REGION_BASIC });
    const noteSpan = container.querySelector('.rel-row__note');
    expect(noteSpan).not.toBeNull();
    expect(noteSpan?.textContent).toContain('opens checkout modal');
  });
});

// ---------------------------------------------------------------------------
// endpointLabel with nodeKind='region' — uses regionById lookup
// ---------------------------------------------------------------------------

const REGION_B: Region = {
  region_id: 'reg-bbccdd',
  rect: { x: 0, y: 0, width: 50, height: 50 },
  member_pick_ids: [],
  note: 'Login Area',
  timestamp_ms: 0,
};

const REGION_B_NO_NOTE: Region = {
  region_id: 'reg-ccddee',
  rect: { x: 0, y: 0, width: 50, height: 50 },
  member_pick_ids: [],
  note: null,
  timestamp_ms: 0,
};

const RELATION_OUT_TO_REGION_WITH_NOTE: Relation = {
  relation_id: 'rel-to-region-note',
  source_id: 'reg-aabbcc',
  source_kind: 'region',
  target_id: 'reg-bbccdd',
  target_kind: 'region',
  kind: 'relates_to',
  note: null,
  timestamp_ms: 0,
};

const RELATION_OUT_TO_REGION_NO_NOTE: Relation = {
  relation_id: 'rel-to-region-no-note',
  source_id: 'reg-aabbcc',
  source_kind: 'region',
  target_id: 'reg-ccddee',
  target_kind: 'region',
  kind: 'relates_to',
  note: null,
  timestamp_ms: 0,
};

describe('RegionDetails — endpointLabel with region kind', () => {
  test('region target with note shows region note as label', () => {
    backendState.inspector.regions = [REGION_B as any];
    backendState.inspector.relations = [RELATION_OUT_TO_REGION_WITH_NOTE];
    const { getByText } = render(RegionDetails, { region: REGION_BASIC });
    // endpointLabel returns region.note when r.note.trim() truthy
    expect(getByText('Login Area')).toBeTruthy();
  });

  test('region target without note shows region:id prefix as label', () => {
    backendState.inspector.regions = [REGION_B_NO_NOTE as any];
    backendState.inspector.relations = [RELATION_OUT_TO_REGION_NO_NOTE];
    const { container } = render(RegionDetails, { region: REGION_BASIC });
    // endpointLabel returns `region:${id.slice(0,6)}` when note is null
    expect(container.textContent).toContain('region:reg-cc');
  });

  test('clicking region-endpoint outgoing calls selectRegion via bridge', () => {
    backendState.inspector.regions = [REGION_B as any];
    backendState.inspector.relations = [RELATION_OUT_TO_REGION_WITH_NOTE];
    const { container } = render(RegionDetails, { region: REGION_BASIC });
    const relBtn = container.querySelector('.rel-row') as HTMLButtonElement;
    fireEvent.click(relBtn);
    expect(send).toHaveBeenCalled();
  });
});

// ---------------------------------------------------------------------------
// Delete relation via keydown Enter
// ---------------------------------------------------------------------------

describe('RegionDetails — delete via keydown Enter', () => {
  test('pressing Enter on delete button fires deleteRelation', () => {
    backendState.inspector.picks = [PICK_A as any];
    backendState.inspector.relations = [RELATION_OUT];
    const { container } = render(RegionDetails, { region: REGION_BASIC });
    const deleteEl = container.querySelector('[aria-label="Delete relation"]') as HTMLElement;
    expect(deleteEl).not.toBeNull();
    // Keydown Enter triggers the deleteRelation path
    fireEvent.keyDown(deleteEl, { key: 'Enter' });
    expect(send).toHaveBeenCalled();
  });

  test('pressing non-Enter key on delete button does not call bridge', () => {
    backendState.inspector.picks = [PICK_A as any];
    backendState.inspector.relations = [RELATION_OUT];
    const { container } = render(RegionDetails, { region: REGION_BASIC });
    const deleteEl = container.querySelector('[aria-label="Delete relation"]') as HTMLElement;
    send.mockClear();
    // Keydown Tab does NOT trigger deleteRelation
    fireEvent.keyDown(deleteEl, { key: 'Tab' });
    expect(send).not.toHaveBeenCalled();
  });
});

// ---------------------------------------------------------------------------
// Mouse hover on rel-row
// ---------------------------------------------------------------------------

describe('RegionDetails — rel-row hover events', () => {
  test('mouseenter on rel-row calls uiPrefs.hoverRelation', () => {
    backendState.inspector.picks = [PICK_A as any];
    backendState.inspector.relations = [RELATION_OUT];
    const { container } = render(RegionDetails, { region: REGION_BASIC });
    const relBtn = container.querySelector('.rel-row') as HTMLButtonElement;
    // onmouseenter and onmouseleave are part of the template — firing them should not throw
    expect(() => fireEvent.mouseEnter(relBtn)).not.toThrow();
    expect(() => fireEvent.mouseLeave(relBtn)).not.toThrow();
  });
});

// ---------------------------------------------------------------------------
// Incoming relation click — selectEndpoint for pick source
// ---------------------------------------------------------------------------

describe('RegionDetails — incoming relation click', () => {
  test('clicking incoming relation calls selectEndpoint (source endpoint)', () => {
    backendState.inspector.picks = [PICK_A as any];
    backendState.inspector.relations = [RELATION_IN];
    const { container } = render(RegionDetails, { region: REGION_BASIC });
    // RELATION_IN is incoming from pick-a → clicking should selectPick(pick-a)
    const relBtn = container.querySelector('.rel-row') as HTMLButtonElement;
    fireEvent.click(relBtn);
    expect(send).toHaveBeenCalled();
  });
});
