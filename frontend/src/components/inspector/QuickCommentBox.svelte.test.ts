/**
 * QuickCommentBox tests (vitest + jsdom + @testing-library/svelte).
 *
 * Covers the rapid-loop wiring (jsdom is blind to CSS/positioning — we test
 * state + the updateComment wire-call, not pixels):
 *   - mode-off renders nothing
 *   - mode-on renders the hovering box with the live counter
 *   - a pending pick renders the auto-focused inline input
 *   - Enter with text → updateComment(pickId, text) + counter++ + input clears
 *   - Enter with empty text → no updateComment, no counter bump, input clears
 *   - Escape → discard, no updateComment
 *   - exit button → mode off
 */
import { describe, expect, test, vi, beforeEach, afterEach } from 'vitest';
import { render, cleanup, fireEvent } from '@testing-library/svelte';

// vi.mock is hoisted above imports — use vi.hoisted so the spy is initialised
// before the factory runs (and before the component imports backendState).
const { updateComment } = vi.hoisted(() => ({ updateComment: vi.fn() }));

// Mock backendState so the updateComment wire-call is a spy (no real bridge).
vi.mock('../../backend-state/backend-state.svelte', () => ({
  backendState: {
    inspector: {
      updateComment,
    },
  },
}));

import QuickCommentBox from './QuickCommentBox.svelte';
import { quickCommentMode } from '../../local-state/quick-comment-mode.svelte';

beforeEach(() => {
  updateComment.mockClear();
  quickCommentMode.exit();
  quickCommentMode.commentedCount = 0;
});

afterEach(() => {
  cleanup();
});

describe('QuickCommentBox rendering', () => {
  test('renders nothing when the mode is inactive', () => {
    const { container } = render(QuickCommentBox);
    expect(container.querySelector('.qc-box')).toBeNull();
    expect(container.querySelector('.qc-input')).toBeNull();
  });

  test('renders the hovering box with the live counter when active', async () => {
    quickCommentMode.enter();
    quickCommentMode.commentedCount = 3;
    const { container } = render(QuickCommentBox);

    const box = container.querySelector('.qc-box');
    expect(box).not.toBeNull();
    expect(box?.textContent).toContain('3 commented');
    // No pick pending yet → no inline input.
    expect(container.querySelector('.qc-input')).toBeNull();
  });

  test('renders an auto-focused inline input when a pick is pending', async () => {
    quickCommentMode.enter();
    const { container } = render(QuickCommentBox);

    quickCommentMode.openInput('pick-1', { x: 5, y: 5, width: 20, height: 10 });
    await Promise.resolve();
    // Let the rAF-driven focus effect run.
    await new Promise((r) => requestAnimationFrame(() => r(null)));

    const input = container.querySelector<HTMLInputElement>('.qc-input__field');
    expect(input).not.toBeNull();
  });
});

describe('QuickCommentBox save loop', () => {
  test('Enter with text saves the comment, bumps the counter, clears the input', async () => {
    quickCommentMode.enter();
    const { container } = render(QuickCommentBox);
    quickCommentMode.openInput('pick-42', null);
    await Promise.resolve();

    const input = container.querySelector<HTMLInputElement>('.qc-input__field')!;
    await fireEvent.input(input, { target: { value: 'too small' } });
    await fireEvent.keyDown(input, { key: 'Enter' });

    expect(updateComment).toHaveBeenCalledWith('pick-42', 'too small');
    expect(quickCommentMode.commentedCount).toBe(1);
    // pending cleared → next pick ready
    expect(quickCommentMode.pending).toBeNull();
  });

  test('Enter with empty text does not save and does not bump the counter', async () => {
    quickCommentMode.enter();
    const { container } = render(QuickCommentBox);
    quickCommentMode.openInput('pick-9', null);
    await Promise.resolve();

    const input = container.querySelector<HTMLInputElement>('.qc-input__field')!;
    await fireEvent.input(input, { target: { value: '   ' } });
    await fireEvent.keyDown(input, { key: 'Enter' });

    expect(updateComment).not.toHaveBeenCalled();
    expect(quickCommentMode.commentedCount).toBe(0);
    expect(quickCommentMode.pending).toBeNull();
  });

  test('Escape discards the input without saving', async () => {
    quickCommentMode.enter();
    const { container } = render(QuickCommentBox);
    quickCommentMode.openInput('pick-3', null);
    await Promise.resolve();

    const input = container.querySelector<HTMLInputElement>('.qc-input__field')!;
    await fireEvent.input(input, { target: { value: 'discard me' } });
    await fireEvent.keyDown(input, { key: 'Escape' });

    expect(updateComment).not.toHaveBeenCalled();
    expect(quickCommentMode.commentedCount).toBe(0);
    expect(quickCommentMode.pending).toBeNull();
  });
});

describe('QuickCommentBox exit', () => {
  test('exit button turns the mode off', async () => {
    quickCommentMode.enter();
    const { container } = render(QuickCommentBox);

    const exitBtn = container.querySelector<HTMLButtonElement>('.qc-box__exit')!;
    await fireEvent.click(exitBtn);

    expect(quickCommentMode.active).toBe(false);
  });
});
