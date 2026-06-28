/**
 * PickDetails tests.
 *
 * Tests: tag display, selector, url, text snippet, id/class attributes,
 * fingerprint section, relations section (outgoing/incoming), delete relation.
 */
const send = vi.hoisted(() => vi.fn());
vi.mock('../../bridge/bridge.svelte', () => ({ bridge: { send } }));

import { describe, expect, test, afterEach, beforeEach } from 'vitest';
import { render, cleanup, fireEvent } from '@testing-library/svelte';
import PickDetails from './PickDetails.svelte';
import { backendState } from '../../backend-state/backend-state.svelte';
import type { Relation } from '../../_generated/state';

afterEach(() => {
  cleanup();
  send.mockClear();
  backendState.inspector.relations = [];
  backendState.inspector.picks = [];
  backendState.inspector.regions = [];
});

// Minimal pick with only required fields
const BASIC_PICK = {
  pick_id: 'pick-aa1122',
  session_id: 'sess-001',
  timestamp_ms: 1700000000000,
  url: 'https://example.com/page',
  element: {
    selector: '#submit-btn',
    tag: 'button',
    text_snippet: null,
    fingerprint: {
      tag: 'button',
      attributes: {},
      path: [],
      siblings_count: 2,
    },
  },
} as any;

// Pick with id + class attributes
const RICH_PICK = {
  pick_id: 'pick-bb2233',
  session_id: 'sess-001',
  timestamp_ms: 1700000001000,
  url: 'https://example.com/login',
  element: {
    selector: 'form#login .submit-btn',
    tag: 'button',
    text_snippet: 'Submit',
    fingerprint: {
      tag: 'button',
      attributes: { id: 'submit', class: 'btn btn-primary', 'data-testid': 'submit-btn' },
      path: ['html', 'body', 'form', 'button'],
      siblings_count: 1,
      parent_name: 'form',
      parent_attribs: { id: 'login', class: 'auth-form' },
      parent_text: 'Please login',
      siblings: ['label', 'input'],
      children: ['span'],
      text: 'Submit Form',
    },
  },
} as any;

const REL_OUT: Relation = {
  relation_id: 'rel-001',
  source_id: 'pick-aa1122',
  source_kind: 'pick',
  target_id: 'pick-bb2233',
  target_kind: 'pick',
  kind: 'relates_to',
  note: null,
  timestamp_ms: 0,
};

const REL_IN: Relation = {
  relation_id: 'rel-002',
  source_id: 'pick-bb2233',
  source_kind: 'pick',
  target_id: 'pick-aa1122',
  target_kind: 'pick',
  kind: 'triggers',
  note: 'click triggers submit',
  timestamp_ms: 0,
};

describe('PickDetails — basic fields', () => {
  test('renders tag in a <code> element', () => {
    const { getAllByText } = render(PickDetails, { pick: BASIC_PICK });
    // tag is shown as "button"
    const codeTags = getAllByText('button');
    expect(codeTags.length).toBeGreaterThan(0);
  });

  test('renders selector', () => {
    const { getByText } = render(PickDetails, { pick: BASIC_PICK });
    expect(getByText('#submit-btn')).toBeTruthy();
  });

  test('renders url', () => {
    const { getByText } = render(PickDetails, { pick: BASIC_PICK });
    expect(getByText('https://example.com/page')).toBeTruthy();
  });

  test('renders timestamp', () => {
    const { container } = render(PickDetails, { pick: BASIC_PICK });
    // at row should exist in dl
    const dts = container.querySelectorAll('dt');
    const atDt = Array.from(dts).find((dt) => dt.textContent?.trim() === 'at');
    expect(atDt).not.toBeUndefined();
  });

  test('renders dl.details element', () => {
    const { container } = render(PickDetails, { pick: BASIC_PICK });
    expect(container.querySelector('dl.details')).not.toBeNull();
  });
});

describe('PickDetails — text snippet', () => {
  test('does not show text row when text_snippet is null', () => {
    const { container } = render(PickDetails, { pick: BASIC_PICK });
    const dts = container.querySelectorAll('dt');
    const textDt = Array.from(dts).find((dt) => dt.textContent?.trim() === 'text');
    expect(textDt).toBeUndefined();
  });

  test('shows text row when text_snippet is set', () => {
    const { container } = render(PickDetails, { pick: RICH_PICK });
    const dts = container.querySelectorAll('dt');
    const textDt = Array.from(dts).find((dt) => dt.textContent?.trim() === 'text');
    expect(textDt).not.toBeUndefined();
  });

  test('displays text_snippet content', () => {
    const { getByText } = render(PickDetails, { pick: RICH_PICK });
    expect(getByText('Submit')).toBeTruthy();
  });
});

describe('PickDetails — id and class attributes', () => {
  test('shows id row when element has id attribute', () => {
    const { container } = render(PickDetails, { pick: RICH_PICK });
    const dts = container.querySelectorAll('dt');
    const idDt = Array.from(dts).find((dt) => dt.textContent?.trim() === 'id');
    expect(idDt).not.toBeUndefined();
  });

  test('displays id value with # prefix', () => {
    const { getByText } = render(PickDetails, { pick: RICH_PICK });
    expect(getByText('#submit')).toBeTruthy();
  });

  test('shows classes row when element has class attribute', () => {
    const { container } = render(PickDetails, { pick: RICH_PICK });
    const dts = container.querySelectorAll('dt');
    const classDt = Array.from(dts).find((dt) => dt.textContent?.trim() === 'classes');
    expect(classDt).not.toBeUndefined();
  });

  test('displays class with . prefix', () => {
    const { container } = render(PickDetails, { pick: RICH_PICK });
    const dts = container.querySelectorAll('dt');
    const classDt = Array.from(dts).find((dt) => dt.textContent?.trim() === 'classes');
    const dd = classDt?.nextElementSibling;
    expect(dd?.textContent).toContain('.btn');
  });

  test('does not show id row when no id attribute', () => {
    const { container } = render(PickDetails, { pick: BASIC_PICK });
    const dts = container.querySelectorAll('dt');
    const idDt = Array.from(dts).find((dt) => dt.textContent?.trim() === 'id');
    expect(idDt).toBeUndefined();
  });
});

describe('PickDetails — fingerprint section', () => {
  test('renders fingerprint details element', () => {
    const { container } = render(PickDetails, { pick: BASIC_PICK });
    expect(container.querySelector('details.fingerprint')).not.toBeNull();
  });

  test('fingerprint summary shows "fingerprint"', () => {
    const { container } = render(PickDetails, { pick: BASIC_PICK });
    const summary = container.querySelector('details.fingerprint > summary');
    expect(summary?.textContent).toContain('fingerprint');
  });

  test('shows path when fingerprint.path is non-empty', () => {
    const { container } = render(PickDetails, { pick: RICH_PICK });
    // path = ['html', 'body', 'form', 'button'] → joined by ' › '
    const fingerprintSection = container.querySelector('details.fingerprint');
    expect(fingerprintSection?.textContent).toContain('html');
  });

  test('shows "—" when path is empty', () => {
    const { container } = render(PickDetails, { pick: BASIC_PICK });
    const fingerprintSection = container.querySelector('details.fingerprint');
    expect(fingerprintSection?.textContent).toContain('—');
  });

  test('shows parent name when parent_name is set', () => {
    const { container } = render(PickDetails, { pick: RICH_PICK });
    const fingerprintSection = container.querySelector('details.fingerprint');
    expect(fingerprintSection?.textContent).toContain('form');
  });

  test('shows parent id when parent_attribs.id is set', () => {
    const { container } = render(PickDetails, { pick: RICH_PICK });
    const fingerprintSection = container.querySelector('details.fingerprint');
    expect(fingerprintSection?.textContent).toContain('#login');
  });

  test('shows "(orphan)" when parent_name is not set', () => {
    const { container } = render(PickDetails, { pick: BASIC_PICK });
    const fingerprintSection = container.querySelector('details.fingerprint');
    expect(fingerprintSection?.textContent).toContain('orphan');
  });

  test('shows siblings when siblings array is non-empty', () => {
    const { container } = render(PickDetails, { pick: RICH_PICK });
    const fingerprintSection = container.querySelector('details.fingerprint');
    expect(fingerprintSection?.textContent).toContain('label');
  });

  test('shows children when children array is non-empty', () => {
    const { container } = render(PickDetails, { pick: RICH_PICK });
    const fingerprintSection = container.querySelector('details.fingerprint');
    expect(fingerprintSection?.textContent).toContain('span');
  });

  test('shows other attributes (data-testid)', () => {
    const { container } = render(PickDetails, { pick: RICH_PICK });
    const fingerprintSection = container.querySelector('details.fingerprint');
    expect(fingerprintSection?.textContent).toContain('data-testid');
  });

  test('shows parent text when set', () => {
    const { container } = render(PickDetails, { pick: RICH_PICK });
    const fingerprintSection = container.querySelector('details.fingerprint');
    expect(fingerprintSection?.textContent).toContain('Please login');
  });
});

describe('PickDetails — relations section', () => {
  beforeEach(() => {
    backendState.inspector.picks = [BASIC_PICK, RICH_PICK];
  });

  test('no relations section when no relations exist', () => {
    backendState.inspector.relations = [];
    const { container } = render(PickDetails, { pick: BASIC_PICK });
    expect(container.querySelector('.relations-section')).toBeNull();
  });

  test('shows relations section when outgoing relation exists', () => {
    backendState.inspector.relations = [REL_OUT];
    const { container } = render(PickDetails, { pick: BASIC_PICK });
    expect(container.querySelector('.relations-section')).not.toBeNull();
  });

  test('shows "outgoing" label for outgoing relation', () => {
    backendState.inspector.relations = [REL_OUT];
    const { getByText } = render(PickDetails, { pick: BASIC_PICK });
    expect(getByText('outgoing')).toBeTruthy();
  });

  test('shows target selector in outgoing relation row', () => {
    backendState.inspector.relations = [REL_OUT];
    const { getByText } = render(PickDetails, { pick: BASIC_PICK });
    // target is RICH_PICK with selector 'form#login .submit-btn'
    expect(getByText('form#login .submit-btn')).toBeTruthy();
  });

  test('shows "incoming" label for incoming relation', () => {
    backendState.inspector.relations = [REL_IN];
    const { getByText } = render(PickDetails, { pick: BASIC_PICK });
    expect(getByText('incoming')).toBeTruthy();
  });

  test('shows relation note in relation row', () => {
    backendState.inspector.relations = [REL_IN];
    const { container } = render(PickDetails, { pick: BASIC_PICK });
    expect(container.textContent).toContain('click triggers submit');
  });

  test('clicking outgoing relation row calls bridge.send (selectPick)', () => {
    backendState.inspector.relations = [REL_OUT];
    const { container } = render(PickDetails, { pick: BASIC_PICK });
    const relRow = container.querySelector('.rel-row') as HTMLButtonElement;
    fireEvent.click(relRow);
    expect(send).toHaveBeenCalled();
  });

  test('clicking delete relation calls bridge.send (deleteRelation)', () => {
    backendState.inspector.relations = [REL_OUT];
    const { container } = render(PickDetails, { pick: BASIC_PICK });
    const deleteBtn = container.querySelector('[aria-label="Delete relation"]') as HTMLElement;
    expect(deleteBtn).not.toBeNull();
    fireEvent.click(deleteBtn);
    expect(send).toHaveBeenCalled();
  });

  test('shows "(missing)" when target pick_id not found', () => {
    const relWithMissingTarget: Relation = {
      ...REL_OUT,
      target_id: 'unknown-pick-id',
    };
    backendState.inspector.relations = [relWithMissingTarget];
    const { container } = render(PickDetails, { pick: BASIC_PICK });
    expect(container.textContent).toContain('(missing)');
  });
});
