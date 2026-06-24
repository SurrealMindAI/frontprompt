/**
 * PanelState — overlay-mirror für backend-authoritative panel-state.
 *
 * backendState category: Python's StateManager ist single-writer.
 * Overlay hält reactive mirror + sendet user-intents als
 * ``*Requested`` wire-messages outbound.
 *
 * Lifecycle:
 *   1. Overlay mountet → bridge sendet OverlayReady
 *   2. Python broadcastet StateSnapshot → sync.svelte.ts ruft hydrate()
 *   3. User klickt panel-toggle → togglePanel() optimistic-updates mirror +
 *      sendet PanelToggleRequested → Python mutiert + broadcastet neuen
 *      StateSnapshot → hydrate() reconciles
 *
 * UI-config (axis/min/max/tabThickness) bleibt lokal — das ist KEIN state,
 * sondern fixed UI-behavior pro panel-id.
 *
 * INSPECTOR-CROSS-DERIVE: wenn ``backendState.inspector.active === true``,
 * werden ALLE Panels temporär als "closed" angezeigt (alle Lasche). Die
 * authoritative ``panels[id].open`` bleibt UNANGETASTET. Der derived
 * effectiveOpen/effectiveSize/gridTemplateRows/Cols lebt in App.svelte
 * (UI-Layer-Concern), um Cross-Store-Import-Zyklen zwischen panel-state
 * und inspector-state zu vermeiden. PanelState selbst ist inspector-unaware.
 * Siehe :file:`./inspector-state.svelte.ts` + :file:`../App.svelte`.
 */

import { bridge } from '../bridge/bridge.svelte';
import type { PanelStateView } from '../_generated/state';

export type PanelId = 'top' | 'bottom' | 'left' | 'right';
export type Axis = 'horizontal' | 'vertical';

export interface PanelConfig {
  axis: Axis;
  minSize: number;
  maxSize: number;
  defaultSize: number;
  tabThickness: number;
}

export const PANEL_IDS: readonly PanelId[] = ['top', 'bottom', 'left', 'right'] as const;

/**
 * tabThickness = grid-cell-Größe wenn Panel collapsed.
 *
 * Per-axis-tuning:
 *   - **top/bottom (vertical axis)**: 28px — horizontale streifen brauchen
 *     weniger Höhe als die seitlichen Laschen. 50px wirkte unnötig breit.
 *   - **left/right (horizontal axis)**: 50px — vertikale Laschen haben mehr
 *     vertical-real-estate, 50×50 button-Größe ist proportional.
 */
export const PANEL_CONFIGS: Record<PanelId, PanelConfig> = {
  top: { axis: 'vertical', minSize: 40, maxSize: 400, defaultSize: 56, tabThickness: 28 },
  bottom: { axis: 'vertical', minSize: 80, maxSize: 500, defaultSize: 220, tabThickness: 28 },
  left: { axis: 'horizontal', minSize: 200, maxSize: 600, defaultSize: 300, tabThickness: 50 },
  right: { axis: 'horizontal', minSize: 200, maxSize: 600, defaultSize: 340, tabThickness: 50 },
};

const SCHEMA_VERSION = '0.1.0';

interface MutablePanelMirror {
  open: boolean;
  size: number;
}

export class PanelState {
  /** Mirror der backend-authoritative state. Updated via hydrate() + optimistic intents. */
  panels = $state<Record<PanelId, MutablePanelMirror>>({
    top: { open: true, size: PANEL_CONFIGS.top.defaultSize },
    bottom: { open: true, size: PANEL_CONFIGS.bottom.defaultSize },
    left: { open: true, size: PANEL_CONFIGS.left.defaultSize },
    right: { open: true, size: PANEL_CONFIGS.right.defaultSize },
  });

  allHidden = $derived(
    !this.panels.top.open &&
      !this.panels.bottom.open &&
      !this.panels.left.open &&
      !this.panels.right.open
  );

  effectiveSize(id: PanelId): number {
    const s = this.panels[id];
    return s.open ? s.size : PANEL_CONFIGS[id].tabThickness;
  }

  /**
   * Effektive size berücksichtigt eine externe "force-closed" Bedingung
   * (z.B. inspectorActive). Wird vom App.svelte / Panel.svelte mit
   * ``backendState.inspector.active`` aufgerufen — derived-reactivity flowt
   * durch ohne dass PanelState selbst von InspectorState weiß.
   */
  effectiveSizeWith(id: PanelId, forceClosed: boolean): number {
    if (forceClosed) return PANEL_CONFIGS[id].tabThickness;
    return this.effectiveSize(id);
  }

  gridTemplateColumns = $derived(
    `${this.effectiveSize('left')}px 1fr ${this.effectiveSize('right')}px`
  );

  gridTemplateRows = $derived(
    `${this.effectiveSize('top')}px 1fr ${this.effectiveSize('bottom')}px`
  );

  /** Cross-derive: wenn forceClosed (= inspectorActive), alle panels rendern als Lasche. */
  gridTemplateColumnsWith(forceClosed: boolean): string {
    return (
      `${this.effectiveSizeWith('left', forceClosed)}px 1fr ` +
      `${this.effectiveSizeWith('right', forceClosed)}px`
    );
  }
  gridTemplateRowsWith(forceClosed: boolean): string {
    return (
      `${this.effectiveSizeWith('top', forceClosed)}px 1fr ` +
      `${this.effectiveSizeWith('bottom', forceClosed)}px`
    );
  }

  /**
   * Effektive open-Anzeige für einen Panel — true wenn open UND nicht
   * extern force-closed (z.B. via Inspector aktiv). Panel.svelte hängt
   * sein content-rendering daran auf.
   */
  effectiveOpenWith(id: PanelId, forceClosed: boolean): boolean {
    if (forceClosed) return false;
    return this.panels[id].open;
  }

  /**
   * Hydrate mirror from authoritative backend snapshot.
   * Called by backend-state/sync.svelte.ts auf jedem StateSnapshot-receive.
   */
  hydrate(view: PanelStateView): void {
    // Defensive mit ?? falls field missing (pzc-bug #1086 dropped required fields)
    if (view.top) {
      this.panels.top.open = view.top.open ?? this.panels.top.open;
      this.panels.top.size = view.top.size ?? this.panels.top.size;
    }
    if (view.bottom) {
      this.panels.bottom.open = view.bottom.open ?? this.panels.bottom.open;
      this.panels.bottom.size = view.bottom.size ?? this.panels.bottom.size;
    }
    if (view.left) {
      this.panels.left.open = view.left.open ?? this.panels.left.open;
      this.panels.left.size = view.left.size ?? this.panels.left.size;
    }
    if (view.right) {
      this.panels.right.open = view.right.open ?? this.panels.right.open;
      this.panels.right.size = view.right.size ?? this.panels.right.size;
    }
  }

  // ----- Intents (optimistic UI + wire-send) ----------------------------------

  /** User clickte tab. Optimistic toggle + send intent. */
  togglePanel(id: PanelId): void {
    this.panels[id].open = !this.panels[id].open;
    void bridge.send({
      kind: 'panel_toggle_requested',
      schema_version: SCHEMA_VERSION,
      panel_id: id,
    });
  }

  /**
   * Während resize-drag: nur lokal mirror updaten. KEIN wire-send pro pointermove —
   * sonst überschwemmt der wire. commitResize() sendet die finale size am drag-end.
   */
  resizePanel(id: PanelId, newSize: number): void {
    const cfg = PANEL_CONFIGS[id];
    this.panels[id].size = Math.max(cfg.minSize, Math.min(cfg.maxSize, newSize));
  }

  /** Am drag-end (pointerup) aufgerufen — sendet finale size ans backend. */
  commitResize(id: PanelId): void {
    void bridge.send({
      kind: 'panel_resize_requested',
      schema_version: SCHEMA_VERSION,
      panel_id: id,
      new_size: this.panels[id].size,
    });
  }

  /** User clickte hide-all/show-all toolbar-button. Optimistic + intent. */
  toggleHideAll(): void {
    const target = this.allHidden;
    for (const id of PANEL_IDS) {
      this.panels[id].open = target;
    }
    void bridge.send({
      kind: 'hide_all_panels_requested',
      schema_version: SCHEMA_VERSION,
      target_open: target,
    });
  }
}
