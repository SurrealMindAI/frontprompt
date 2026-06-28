/**
 * RelationsTab smoke tests.
 *
 * Tests the idle state (no drafting, no relations) and the drafting UI entry.
 */
const send = vi.hoisted(() => vi.fn());
vi.mock('../../../bridge/bridge.svelte', () => ({ bridge: { send } }));

import { describe, expect, test, afterEach, beforeEach } from 'vitest';
import { render, cleanup, fireEvent } from '@testing-library/svelte';
import RelationsTab from './RelationsTab.svelte';
import { backendState } from '../../../backend-state/backend-state.svelte';
import { relationDraft } from '../../../services/relations';
import { overlayContext } from '../../../services/context/overlay-context.svelte';

afterEach(() => {
  cleanup();
  send.mockClear();
  backendState.inspector.relations = [];
  backendState.inspector.picks = [];
  backendState.inspector.regions = [];
  relationDraft.cancel();
  overlayContext.resetForTests();
});

beforeEach(() => {
  relationDraft.cancel();
});

describe('RelationsTab — empty state (idle)', () => {
  test('renders + Create relation button', () => {
    const { getByText } = render(RelationsTab);
    expect(getByText('+ Create relation')).toBeTruthy();
  });

  test('shows group header with "(all)" in null-session mode', () => {
    // overlayContext.currentSessionId is null in test environment →
    // visibleGroups returns a single "(all)" bucket (even when empty).
    backendState.inspector.relations = [];
    const { getByText } = render(RelationsTab);
    expect(getByText('(all)')).toBeTruthy();
  });

  test('shows 0 relations count', () => {
    backendState.inspector.relations = [];
    const { container } = render(RelationsTab);
    const count = container.querySelector('.list-header__count');
    expect(count?.textContent).toContain('0 relation');
  });

  test('shows plural "relations" for zero count', () => {
    backendState.inspector.relations = [];
    const { container } = render(RelationsTab);
    const count = container.querySelector('.list-header__count');
    expect(count?.textContent).toBe('0 relations');
  });
});

describe('RelationsTab — entering draft mode', () => {
  test('clicking + Create relation enters draft mode', () => {
    const { getByText } = render(RelationsTab);
    const btn = getByText('+ Create relation');
    fireEvent.click(btn);
    expect(relationDraft.drafting).toBe(true);
  });

  test('draft mode shows cancel button', () => {
    relationDraft.start();
    const { getByText } = render(RelationsTab);
    expect(getByText('cancel')).toBeTruthy();
  });

  test('draft mode shows create button (disabled when no endpoints)', () => {
    relationDraft.start();
    const { getByText } = render(RelationsTab);
    const createBtn = getByText('create') as HTMLButtonElement;
    expect(createBtn).toBeTruthy();
    expect(createBtn.disabled).toBe(true);
  });

  test('cancel button exits draft mode', () => {
    const { getByText } = render(RelationsTab);
    fireEvent.click(getByText('+ Create relation'));
    fireEvent.click(getByText('cancel'));
    expect(relationDraft.drafting).toBe(false);
  });
});

// ---------------------------------------------------------------------------
// isSelfLoopAttempt warning — source === target (same id and kind)
// ---------------------------------------------------------------------------

describe('RelationsTab — isSelfLoopAttempt warning', () => {
  test('shows warning when source and target are the same element', () => {
    relationDraft.start();
    // Set same id and kind for both source and target — triggers isSelfLoopAttempt
    relationDraft.setSource({ id: 'pick-same', kind: 'pick' });
    relationDraft.setTarget({ id: 'pick-same', kind: 'pick' });
    const { container } = render(RelationsTab);
    const warning = container.querySelector('.warning');
    expect(warning).not.toBeNull();
    expect(warning?.textContent).toContain('Source and target must differ');
  });

  test('no warning when source and target differ', () => {
    relationDraft.start();
    relationDraft.setSource({ id: 'pick-a', kind: 'pick' });
    relationDraft.setTarget({ id: 'pick-b', kind: 'pick' });
    const { container } = render(RelationsTab);
    expect(container.querySelector('.warning')).toBeNull();
  });

  test('no warning when source and target have same id but different kind', () => {
    relationDraft.start();
    // Same id but different kind (pick vs region) → NOT a self-loop
    relationDraft.setSource({ id: 'node-x', kind: 'pick' });
    relationDraft.setTarget({ id: 'node-x', kind: 'region' });
    const { container } = render(RelationsTab);
    expect(container.querySelector('.warning')).toBeNull();
  });
});

// ---------------------------------------------------------------------------
// Note textarea oninput — covers setNote call
// ---------------------------------------------------------------------------

describe('RelationsTab — note textarea oninput', () => {
  test('typing in note textarea calls relationDraft.setNote', () => {
    const setNoteSpy = vi.spyOn(relationDraft, 'setNote');
    relationDraft.start();
    const { container } = render(RelationsTab);
    const textarea = container.querySelector('.note-input') as HTMLTextAreaElement;
    expect(textarea).not.toBeNull();
    fireEvent.input(textarea, { target: { value: 'some note text' } });
    expect(setNoteSpy).toHaveBeenCalledWith('some note text');
    setNoteSpy.mockRestore();
  });
});

// ---------------------------------------------------------------------------
// overlayContext — empty groups branch (line 131)
// ---------------------------------------------------------------------------

describe('RelationsTab — overlayContext-driven branches', () => {
  test('empty groups TRUE branch: sessionId set + no relations → .empty div (line 131)', () => {
    // With a non-null sessionId and no relations, visibleGroups returns [] → groups.length === 0 TRUE
    overlayContext.setForTests({ url: new URL('https://example.com'), currentSessionId: 'sess-rel-y' });
    backendState.inspector.relations = [];
    const { container } = render(RelationsTab);
    expect(container.querySelector('.empty')).not.toBeNull();
  });
});

// ---------------------------------------------------------------------------
// List header — singular vs plural "relations"
// ---------------------------------------------------------------------------

describe('RelationsTab — list header count grammar', () => {
  test('shows "1 relation" (singular) when exactly 1 relation exists', () => {
    backendState.inspector.relations = [
      {
        relation_id: 'rel-1',
        source_id: 'p1',
        source_kind: 'pick',
        target_id: 'p2',
        target_kind: 'pick',
        kind: 'relates_to',
        note: null,
        timestamp_ms: 0,
        origin_session: null,
      } as any,
    ];
    const { container } = render(RelationsTab);
    const count = container.querySelector('.list-header__count');
    expect(count?.textContent?.trim()).toBe('1 relation');
    backendState.inspector.relations = [];
  });
});
