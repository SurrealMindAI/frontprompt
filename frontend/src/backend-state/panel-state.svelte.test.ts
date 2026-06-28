/**
 * PanelState — comprehensive tests covering hydrate + all intent methods.
 *
 * Covers: hydrate, effectiveSize, effectiveSizeWith, gridTemplateColumns/Rows,
 * gridTemplateColumnsWith/RowsWith, effectiveOpenWith, togglePanel,
 * resizePanel, commitResize, toggleHideAll, allHidden derived.
 */
const send = vi.hoisted(() => vi.fn());
vi.mock('../bridge/bridge.svelte', () => ({ bridge: { send } }));

import { describe, expect, test, vi, beforeEach } from 'vitest';
import { PanelState, PANEL_CONFIGS } from './panel-state.svelte';

beforeEach(() => send.mockClear());

// ---------------------------------------------------------------------------
// hydrate
// ---------------------------------------------------------------------------

describe('PanelState.hydrate', () => {
  test('hydrate updates open state for all panels', () => {
    const ps = new PanelState();
    ps.hydrate({
      top: { open: false, size: 28 },
      bottom: { open: false, size: 28 },
      left: { open: false, size: 50 },
      right: { open: false, size: 50 },
    });
    expect(ps.panels.top.open).toBe(false);
    expect(ps.panels.bottom.open).toBe(false);
    expect(ps.panels.left.open).toBe(false);
    expect(ps.panels.right.open).toBe(false);
  });

  test('hydrate updates size for panels', () => {
    const ps = new PanelState();
    ps.hydrate({
      top: { open: true, size: 120 },
      bottom: { open: true, size: 250 },
      left: { open: true, size: 350 },
      right: { open: true, size: 400 },
    });
    expect(ps.panels.top.size).toBe(120);
    expect(ps.panels.left.size).toBe(350);
  });

  test('hydrate with partial view only updates present fields', () => {
    const ps = new PanelState();
    const defaultTopSize = ps.panels.top.size;
    ps.hydrate({ top: { open: false, size: undefined as unknown as number } } as never);
    // size should stay at the default when omitted/undefined
    expect(ps.panels.top.size).toBe(defaultTopSize);
    expect(ps.panels.top.open).toBe(false);
  });

  test('hydrate with empty view is tolerant', () => {
    const ps = new PanelState();
    ps.hydrate({} as never);
    expect(ps.panels.top.open).toBe(true);
  });
});

// ---------------------------------------------------------------------------
// effectiveSize / effectiveSizeWith
// ---------------------------------------------------------------------------

describe('PanelState.effectiveSize', () => {
  test('returns size when panel is open', () => {
    const ps = new PanelState();
    ps.panels.left.open = true;
    ps.panels.left.size = 300;
    expect(ps.effectiveSize('left')).toBe(300);
  });

  test('returns tabThickness when panel is closed', () => {
    const ps = new PanelState();
    ps.panels.left.open = false;
    expect(ps.effectiveSize('left')).toBe(PANEL_CONFIGS.left.tabThickness);
  });
});

describe('PanelState.effectiveSizeWith', () => {
  test('returns tabThickness when forceClosed=true regardless of panel state', () => {
    const ps = new PanelState();
    ps.panels.top.open = true;
    ps.panels.top.size = 300;
    expect(ps.effectiveSizeWith('top', true)).toBe(PANEL_CONFIGS.top.tabThickness);
  });

  test('returns effectiveSize when forceClosed=false', () => {
    const ps = new PanelState();
    ps.panels.top.open = true;
    ps.panels.top.size = 100;
    expect(ps.effectiveSizeWith('top', false)).toBe(100);
  });
});

// ---------------------------------------------------------------------------
// gridTemplate derived + methods
// ---------------------------------------------------------------------------

describe('PanelState.gridTemplateColumns', () => {
  test('derived includes left and right sizes', () => {
    const ps = new PanelState();
    ps.panels.left.open = true;
    ps.panels.left.size = 300;
    ps.panels.right.open = true;
    ps.panels.right.size = 340;
    const cols = ps.gridTemplateColumns;
    expect(cols).toContain('300px');
    expect(cols).toContain('340px');
    expect(cols).toContain('1fr');
  });
});

describe('PanelState.gridTemplateColumnsWith', () => {
  test('uses tabThickness for all horizontal panels when forceClosed=true', () => {
    const ps = new PanelState();
    ps.panels.left.open = true;
    ps.panels.left.size = 300;
    ps.panels.right.open = true;
    ps.panels.right.size = 340;
    const cols = ps.gridTemplateColumnsWith(true);
    expect(cols).toContain(`${PANEL_CONFIGS.left.tabThickness}px`);
    expect(cols).toContain(`${PANEL_CONFIGS.right.tabThickness}px`);
  });

  test('uses full panel sizes when forceClosed=false', () => {
    const ps = new PanelState();
    ps.panels.left.open = true;
    ps.panels.left.size = 300;
    const cols = ps.gridTemplateColumnsWith(false);
    expect(cols).toContain('300px');
  });
});

describe('PanelState.gridTemplateRowsWith', () => {
  test('uses tabThickness for vertical panels when forceClosed=true', () => {
    const ps = new PanelState();
    ps.panels.top.open = true;
    ps.panels.top.size = 100;
    const rows = ps.gridTemplateRowsWith(true);
    expect(rows).toContain(`${PANEL_CONFIGS.top.tabThickness}px`);
  });

  test('uses full panel sizes when forceClosed=false', () => {
    const ps = new PanelState();
    ps.panels.top.open = true;
    ps.panels.top.size = 100;
    const rows = ps.gridTemplateRowsWith(false);
    expect(rows).toContain('100px');
  });
});

// ---------------------------------------------------------------------------
// effectiveOpenWith
// ---------------------------------------------------------------------------

describe('PanelState.effectiveOpenWith', () => {
  test('returns false when forceClosed=true regardless of panel state', () => {
    const ps = new PanelState();
    ps.panels.left.open = true;
    expect(ps.effectiveOpenWith('left', true)).toBe(false);
  });

  test('returns true when panel is open and forceClosed=false', () => {
    const ps = new PanelState();
    ps.panels.left.open = true;
    expect(ps.effectiveOpenWith('left', false)).toBe(true);
  });

  test('returns false when panel is closed and forceClosed=false', () => {
    const ps = new PanelState();
    ps.panels.left.open = false;
    expect(ps.effectiveOpenWith('left', false)).toBe(false);
  });
});

// ---------------------------------------------------------------------------
// togglePanel
// ---------------------------------------------------------------------------

describe('PanelState.togglePanel', () => {
  test('toggles panel open state and sends panel_toggle_requested', () => {
    const ps = new PanelState();
    const wasOpen = ps.panels.left.open;
    ps.togglePanel('left');
    expect(ps.panels.left.open).toBe(!wasOpen);
    expect(send).toHaveBeenCalledWith(
      expect.objectContaining({ kind: 'panel_toggle_requested', panel_id: 'left' })
    );
  });

  test('togglePanel twice returns to original state', () => {
    const ps = new PanelState();
    const original = ps.panels.right.open;
    ps.togglePanel('right');
    ps.togglePanel('right');
    expect(ps.panels.right.open).toBe(original);
  });
});

// ---------------------------------------------------------------------------
// resizePanel
// ---------------------------------------------------------------------------

describe('PanelState.resizePanel', () => {
  test('updates panel size within bounds', () => {
    const ps = new PanelState();
    ps.resizePanel('left', 400);
    expect(ps.panels.left.size).toBe(400);
  });

  test('clamps to minSize when below minimum', () => {
    const ps = new PanelState();
    ps.resizePanel('left', 10); // min is 200
    expect(ps.panels.left.size).toBe(PANEL_CONFIGS.left.minSize);
  });

  test('clamps to maxSize when above maximum', () => {
    const ps = new PanelState();
    ps.resizePanel('left', 9999); // max is 600
    expect(ps.panels.left.size).toBe(PANEL_CONFIGS.left.maxSize);
  });

  test('does NOT send wire message (resize-drag buffering)', () => {
    const ps = new PanelState();
    ps.resizePanel('left', 300);
    expect(send).not.toHaveBeenCalled();
  });
});

// ---------------------------------------------------------------------------
// commitResize
// ---------------------------------------------------------------------------

describe('PanelState.commitResize', () => {
  test('sends panel_resize_requested with current size', () => {
    const ps = new PanelState();
    ps.panels.bottom.size = 180;
    ps.commitResize('bottom');
    expect(send).toHaveBeenCalledWith(
      expect.objectContaining({ kind: 'panel_resize_requested', panel_id: 'bottom', new_size: 180 })
    );
  });
});

// ---------------------------------------------------------------------------
// toggleHideAll / allHidden derived
// ---------------------------------------------------------------------------

describe('PanelState.allHidden', () => {
  test('allHidden is false when any panel is open', () => {
    const ps = new PanelState();
    // All panels open by default
    expect(ps.allHidden).toBe(false);
  });

  test('allHidden is true when all panels are closed', () => {
    const ps = new PanelState();
    ps.panels.top.open = false;
    ps.panels.bottom.open = false;
    ps.panels.left.open = false;
    ps.panels.right.open = false;
    expect(ps.allHidden).toBe(true);
  });
});

describe('PanelState.toggleHideAll', () => {
  test('closes all panels when at least one is open and sends hide_all_panels_requested', () => {
    const ps = new PanelState();
    // All open by default, so toggleHideAll should close all (target=false → open=false)
    // Actually: target = this.allHidden before toggle. If NOT all hidden, allHidden=false.
    // After toggle: panels.open = allHidden = false → closes all.
    // Wait, looking at the code: target = this.allHidden (false when not all hidden)
    // Then panels[id].open = target (= false) → closes all panels
    // The intent is "when not all hidden, hide all"
    ps.toggleHideAll();
    expect(ps.panels.top.open).toBe(false);
    expect(ps.panels.bottom.open).toBe(false);
    expect(ps.panels.left.open).toBe(false);
    expect(ps.panels.right.open).toBe(false);
    expect(send).toHaveBeenCalledWith(
      expect.objectContaining({ kind: 'hide_all_panels_requested', target_open: false })
    );
  });

  test('re-opens all panels when all were hidden and sends hide_all_panels_requested', () => {
    const ps = new PanelState();
    // Close all first
    ps.panels.top.open = false;
    ps.panels.bottom.open = false;
    ps.panels.left.open = false;
    ps.panels.right.open = false;
    // allHidden is now true → target = true → panels open = true
    ps.toggleHideAll();
    expect(ps.panels.top.open).toBe(true);
    expect(ps.panels.left.open).toBe(true);
    expect(send).toHaveBeenCalledWith(
      expect.objectContaining({ kind: 'hide_all_panels_requested', target_open: true })
    );
  });
});
