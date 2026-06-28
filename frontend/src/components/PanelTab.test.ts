/**
 * PanelTab tests.
 *
 * Tests: toggle button, arrow direction (open/collapsed), icon visibility when collapsed.
 */
const send = vi.hoisted(() => vi.fn());
vi.mock('../bridge/bridge.svelte', () => ({ bridge: { send } }));

import { describe, expect, test, afterEach, beforeEach } from 'vitest';
import { render, cleanup, fireEvent } from '@testing-library/svelte';
import PanelTab from './PanelTab.svelte';
import { backendState } from '../backend-state/backend-state.svelte';

afterEach(() => {
  cleanup();
  send.mockClear();
  // Reset all panels to open (default)
  backendState.panel.panels.left.open = true;
  backendState.panel.panels.right.open = true;
  backendState.panel.panels.top.open = true;
  backendState.panel.panels.bottom.open = true;
});

describe('PanelTab — rendering', () => {
  test('renders a button with aria-label containing panel label', () => {
    const { container } = render(PanelTab, { id: 'left', label: 'Tools' });
    const btn = container.querySelector('button');
    expect(btn?.getAttribute('aria-label')).toBe('toggle Tools panel');
  });

  test('has tab--left class for left panel', () => {
    const { container } = render(PanelTab, { id: 'left', label: 'Tools' });
    const btn = container.querySelector('button');
    expect(btn?.classList.contains('tab--left')).toBe(true);
  });

  test('has tab--horizontal class for left panel (horizontal axis)', () => {
    const { container } = render(PanelTab, { id: 'left', label: 'Tools' });
    const btn = container.querySelector('button');
    expect(btn?.classList.contains('tab--horizontal')).toBe(true);
  });

  test('has tab--vertical class for top panel (vertical axis)', () => {
    const { container } = render(PanelTab, { id: 'top', label: 'Stats' });
    const btn = container.querySelector('button');
    expect(btn?.classList.contains('tab--vertical')).toBe(true);
  });
});

describe('PanelTab — open state (default)', () => {
  test('left panel: shows ◀ arrow when open', () => {
    const { container } = render(PanelTab, { id: 'left', label: 'Tools' });
    const arrowSpan = container.querySelector('.tab__arrow');
    expect(arrowSpan?.textContent).toBe('◀');
  });

  test('right panel: shows ▶ arrow when open', () => {
    const { container } = render(PanelTab, { id: 'right', label: 'Details' });
    const arrowSpan = container.querySelector('.tab__arrow');
    expect(arrowSpan?.textContent).toBe('▶');
  });

  test('top panel: shows ▲ arrow when open', () => {
    const { container } = render(PanelTab, { id: 'top', label: 'Stats' });
    const arrowSpan = container.querySelector('.tab__arrow');
    expect(arrowSpan?.textContent).toBe('▲');
  });

  test('bottom panel: shows ▼ arrow when open', () => {
    const { container } = render(PanelTab, { id: 'bottom', label: 'Debug' });
    const arrowSpan = container.querySelector('.tab__arrow');
    expect(arrowSpan?.textContent).toBe('▼');
  });

  test('icon is NOT visible when panel is open', () => {
    const { container } = render(PanelTab, { id: 'left', label: 'Tools' });
    const iconSpan = container.querySelector('.tab__icon');
    expect(iconSpan).toBeNull();
  });

  test('tab--open class is present when open', () => {
    const { container } = render(PanelTab, { id: 'left', label: 'Tools' });
    const btn = container.querySelector('button');
    expect(btn?.classList.contains('tab--open')).toBe(true);
  });
});

describe('PanelTab — collapsed state', () => {
  beforeEach(() => {
    // Close all panels
    backendState.panel.panels.left.open = false;
    backendState.panel.panels.right.open = false;
    backendState.panel.panels.top.open = false;
    backendState.panel.panels.bottom.open = false;
  });

  test('left panel: shows ▶ arrow when collapsed', () => {
    const { container } = render(PanelTab, { id: 'left', label: 'Tools' });
    const arrowSpan = container.querySelector('.tab__arrow');
    expect(arrowSpan?.textContent).toBe('▶');
  });

  test('right panel: shows ◀ arrow when collapsed', () => {
    const { container } = render(PanelTab, { id: 'right', label: 'Details' });
    const arrowSpan = container.querySelector('.tab__arrow');
    expect(arrowSpan?.textContent).toBe('◀');
  });

  test('top panel: shows ▼ arrow when collapsed', () => {
    const { container } = render(PanelTab, { id: 'top', label: 'Stats' });
    const arrowSpan = container.querySelector('.tab__arrow');
    expect(arrowSpan?.textContent).toBe('▼');
  });

  test('bottom panel: shows ▲ arrow when collapsed', () => {
    const { container } = render(PanelTab, { id: 'bottom', label: 'Debug' });
    const arrowSpan = container.querySelector('.tab__arrow');
    expect(arrowSpan?.textContent).toBe('▲');
  });

  test('icon IS visible when panel is collapsed', () => {
    const { container } = render(PanelTab, { id: 'left', label: 'Tools' });
    const iconSpan = container.querySelector('.tab__icon');
    expect(iconSpan).not.toBeNull();
  });

  test('left panel shows ⚒ icon when collapsed', () => {
    const { container } = render(PanelTab, { id: 'left', label: 'Tools' });
    const iconSpan = container.querySelector('.tab__icon');
    expect(iconSpan?.textContent).toBe('⚒');
  });

  test('right panel shows ⓘ icon when collapsed', () => {
    const { container } = render(PanelTab, { id: 'right', label: 'Details' });
    const iconSpan = container.querySelector('.tab__icon');
    expect(iconSpan?.textContent).toBe('ⓘ');
  });

  test('tab--open class is absent when collapsed', () => {
    const { container } = render(PanelTab, { id: 'left', label: 'Tools' });
    const btn = container.querySelector('button');
    expect(btn?.classList.contains('tab--open')).toBe(false);
  });
});

describe('PanelTab — toggle interaction', () => {
  test('clicking the tab calls bridge.send (togglePanel)', async () => {
    const { container } = render(PanelTab, { id: 'left', label: 'Tools' });
    const btn = container.querySelector('button') as HTMLButtonElement;
    await fireEvent.click(btn);
    // togglePanel sends a message via bridge
    expect(send).toHaveBeenCalled();
  });

  test('clicking the tab toggles the panel state optimistically', async () => {
    expect(backendState.panel.panels.left.open).toBe(true);
    const { container } = render(PanelTab, { id: 'left', label: 'Tools' });
    const btn = container.querySelector('button') as HTMLButtonElement;
    await fireEvent.click(btn);
    expect(backendState.panel.panels.left.open).toBe(false);
  });
});
