/**
 * LeftPanelTools tests (vitest + jsdom + @testing-library/svelte).
 *
 * The left tools strip is the single home for all action tools: pick · region ·
 * quick · hide-all. These tests cover the quick-comment toggle (moved here from
 * the top Toolbar) — a thin delegate to the exhaustively-tested quickCommentMode
 * store — plus its tooltip and active-state wiring.
 */
import { describe, expect, test, beforeEach, afterEach } from 'vitest';
import { render, cleanup, fireEvent } from '@testing-library/svelte';
import LeftPanelTools from './LeftPanelTools.svelte';
import { quickCommentMode } from '../../local-state/quick-comment-mode.svelte';

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

describe('LeftPanelTools quick-comment toggle', () => {
  test('renders a quick-comment toggle button (inactive by default)', () => {
    const { container } = render(LeftPanelTools);
    const btn = quickButton(container);
    expect(btn.textContent).toContain('quick');
    expect(btn.getAttribute('aria-pressed')).toBe('false');
  });

  test('quick button carries the "quick pick and comment" tooltip', () => {
    const { container } = render(LeftPanelTools);
    expect(quickButton(container).getAttribute('title')).toBe('quick pick and comment');
  });

  test('clicking enters quick-comment mode', async () => {
    const { container } = render(LeftPanelTools);
    await fireEvent.click(quickButton(container));
    expect(quickCommentMode.active).toBe(true);
  });

  test('clicking again exits quick-comment mode', async () => {
    const { container } = render(LeftPanelTools);
    await fireEvent.click(quickButton(container));
    await fireEvent.click(quickButton(container));
    expect(quickCommentMode.active).toBe(false);
  });

  test('reflects active state via aria-pressed', async () => {
    const { container } = render(LeftPanelTools);
    await fireEvent.click(quickButton(container));
    expect(quickButton(container).getAttribute('aria-pressed')).toBe('true');
  });
});
