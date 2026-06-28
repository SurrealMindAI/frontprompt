/**
 * PanelResizer tests.
 *
 * Tests: renders separator with correct aria attributes, applies correct CSS classes,
 * onpointerdown triggers resize.startDrag.
 */
const send = vi.hoisted(() => vi.fn());
vi.mock('../bridge/bridge.svelte', () => ({ bridge: { send } }));

// Mock the resize manager to avoid complex drag logic in tests
const startDrag = vi.hoisted(() => vi.fn());
vi.mock('../managers/resize-manager.svelte', () => ({
  resize: { startDrag },
}));

import { describe, expect, test, afterEach } from 'vitest';
import { render, cleanup, fireEvent } from '@testing-library/svelte';
import PanelResizer from './PanelResizer.svelte';

afterEach(() => {
  cleanup();
  send.mockClear();
  startDrag.mockClear();
});

describe('PanelResizer — rendering', () => {
  test('renders a div.resizer element', () => {
    const { container } = render(PanelResizer, { id: 'left' });
    expect(container.querySelector('.resizer')).not.toBeNull();
  });

  test('has role="separator"', () => {
    const { container } = render(PanelResizer, { id: 'left' });
    const el = container.querySelector('.resizer');
    expect(el?.getAttribute('role')).toBe('separator');
  });

  test('has aria-label "resize left panel"', () => {
    const { container } = render(PanelResizer, { id: 'left' });
    const el = container.querySelector('.resizer');
    expect(el?.getAttribute('aria-label')).toBe('resize left panel');
  });

  test('has aria-label "resize right panel" for right id', () => {
    const { container } = render(PanelResizer, { id: 'right' });
    const el = container.querySelector('.resizer');
    expect(el?.getAttribute('aria-label')).toBe('resize right panel');
  });

  test('left panel resizer has resizer--horizontal class (horizontal axis)', () => {
    const { container } = render(PanelResizer, { id: 'left' });
    const el = container.querySelector('.resizer');
    expect(el?.classList.contains('resizer--horizontal')).toBe(true);
  });

  test('right panel resizer has resizer--horizontal class', () => {
    const { container } = render(PanelResizer, { id: 'right' });
    const el = container.querySelector('.resizer');
    expect(el?.classList.contains('resizer--horizontal')).toBe(true);
  });

  test('top panel resizer has resizer--vertical class (vertical axis)', () => {
    const { container } = render(PanelResizer, { id: 'top' });
    const el = container.querySelector('.resizer');
    expect(el?.classList.contains('resizer--vertical')).toBe(true);
  });

  test('bottom panel resizer has resizer--vertical class', () => {
    const { container } = render(PanelResizer, { id: 'bottom' });
    const el = container.querySelector('.resizer');
    expect(el?.classList.contains('resizer--vertical')).toBe(true);
  });

  test('left resizer has aria-orientation="vertical" (horizontal axis → vertical separator)', () => {
    const { container } = render(PanelResizer, { id: 'left' });
    const el = container.querySelector('.resizer');
    expect(el?.getAttribute('aria-orientation')).toBe('vertical');
  });

  test('top resizer has aria-orientation="horizontal"', () => {
    const { container } = render(PanelResizer, { id: 'top' });
    const el = container.querySelector('.resizer');
    expect(el?.getAttribute('aria-orientation')).toBe('horizontal');
  });
});

describe('PanelResizer — pointer interaction', () => {
  test('pointerdown calls resize.startDrag', async () => {
    const { container } = render(PanelResizer, { id: 'left' });
    const el = container.querySelector('.resizer') as HTMLElement;
    await fireEvent.pointerDown(el, { pointerId: 1, clientX: 100, clientY: 200 });
    expect(startDrag).toHaveBeenCalledOnce();
  });

  test('pointerdown passes correct id to startDrag', async () => {
    const { container } = render(PanelResizer, { id: 'right' });
    const el = container.querySelector('.resizer') as HTMLElement;
    await fireEvent.pointerDown(el, { pointerId: 1, clientX: 50, clientY: 100 });
    const [id] = startDrag.mock.calls[0]!;
    expect(id).toBe('right');
  });

  test('pointerdown for left panel passes direction=1 (grow right)', async () => {
    const { container } = render(PanelResizer, { id: 'left' });
    const el = container.querySelector('.resizer') as HTMLElement;
    await fireEvent.pointerDown(el, { pointerId: 1 });
    const [, , direction] = startDrag.mock.calls[0]!;
    expect(direction).toBe(1);
  });

  test('pointerdown for right panel passes direction=-1 (grow left)', async () => {
    const { container } = render(PanelResizer, { id: 'right' });
    const el = container.querySelector('.resizer') as HTMLElement;
    await fireEvent.pointerDown(el, { pointerId: 1 });
    const [, , direction] = startDrag.mock.calls[0]!;
    expect(direction).toBe(-1);
  });
});
