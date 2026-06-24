/**
 * Toolbar quick-comment toggle tests (vitest + jsdom + @testing-library/svelte).
 *
 * Scope: only the new ⚡ quick button. It is a thin delegate to the (separately
 * and exhaustively tested) quickCommentMode store — these tests assert the
 * button is wired to enter/exit + reflects the active state via aria-pressed.
 */
import { describe, expect, test, beforeEach, afterEach } from 'vitest';
import { render, cleanup, fireEvent } from '@testing-library/svelte';
import Toolbar from './Toolbar.svelte';
import { quickCommentMode } from '../local-state/quick-comment-mode.svelte';

beforeEach(() => {
  quickCommentMode.exit();
});

afterEach(() => {
  cleanup();
});

function quickButton(container: HTMLElement): HTMLButtonElement {
  const btn = container.querySelector<HTMLButtonElement>(
    'button[aria-label="enter quick-comment mode"], button[aria-label="exit quick-comment mode"]'
  );
  if (!btn) throw new Error('quick-comment toggle button not found');
  return btn;
}

describe('Toolbar quick-comment toggle', () => {
  test('renders a quick-comment toggle button (inactive by default)', () => {
    const { container } = render(Toolbar);
    const btn = quickButton(container);
    expect(btn.textContent).toContain('quick');
    expect(btn.getAttribute('aria-pressed')).toBe('false');
  });

  test('clicking enters quick-comment mode', async () => {
    const { container } = render(Toolbar);
    await fireEvent.click(quickButton(container));
    expect(quickCommentMode.active).toBe(true);
  });

  test('clicking again exits quick-comment mode', async () => {
    const { container } = render(Toolbar);
    await fireEvent.click(quickButton(container));
    await fireEvent.click(quickButton(container));
    expect(quickCommentMode.active).toBe(false);
  });

  test('reflects active state via aria-pressed', async () => {
    const { container } = render(Toolbar);
    await fireEvent.click(quickButton(container));
    expect(quickButton(container).getAttribute('aria-pressed')).toBe('true');
  });
});
