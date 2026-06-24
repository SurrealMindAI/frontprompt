/**
 * ResizeManager — Pointer-Event-basierter Drag-Resize für Panels.
 *
 * Single-active-drag-Slot: nur ein Resize gleichzeitig (zweiter pointerdown
 * während aktivem Drag wird ignoriert). Bei pointerdown setzt der Manager
 * PointerCapture auf den Resizer-Element, damit der Drag auch funktioniert
 * wenn der Mauszeiger über die Page hinausgeht.
 *
 * Direction-Parameter (+1 / -1) handelt panel-Asymmetrie:
 *   - top-panel:    axis='vertical',   direction=+1 (move down  → grow)
 *   - bottom-panel: axis='vertical',   direction=-1 (move up    → grow)
 *   - left-panel:   axis='horizontal', direction=+1 (move right → grow)
 *   - right-panel:  axis='horizontal', direction=-1 (move left  → grow)
 *
 * Während des Drags wird der globale Cursor-Stil + user-select gesetzt
 * (verhindert Text-Selektion auf der Host-Page beim ziehen).
 */

import type { Axis, PanelId } from '../backend-state/panel-state.svelte';

export type ResizeDirection = 1 | -1;

interface ActiveDrag {
  pointerId: number;
  target: HTMLElement;
  axis: Axis;
  direction: ResizeDirection;
  startPos: number;
  startSize: number;
  onUpdate: (newSize: number) => void;
  onEnd?: () => void;
}

export class ResizeManager {
  private active: ActiveDrag | null = null;
  private prevBodyCursor = '';
  private prevBodyUserSelect = '';

  /**
   * Start a resize drag. Caller passes:
   *   - panelId für Logging/Debugging
   *   - axis ('horizontal' für left/right, 'vertical' für top/bottom)
   *   - direction (+1 für left/top, -1 für right/bottom)
   *   - event (der pointerdown event, .preventDefault() wird hier gemacht)
   *   - currentSize: aktuelle Größe in px (start-baseline)
   *   - onUpdate: callback der bei jedem pointermove die neue Größe bekommt
   */
  startDrag(
    panelId: PanelId,
    axis: Axis,
    direction: ResizeDirection,
    event: PointerEvent,
    currentSize: number,
    onUpdate: (newSize: number) => void,
    onEnd?: () => void
  ): void {
    if (this.active) return;
    event.preventDefault();
    event.stopPropagation();

    const target = event.currentTarget as HTMLElement;
    try {
      target.setPointerCapture(event.pointerId);
    } catch {
      // setPointerCapture kann werfen wenn pointer nicht mehr aktiv ist;
      // dann brechen wir ab, der Browser räumt selbst auf.
      return;
    }

    this.active = {
      pointerId: event.pointerId,
      target,
      axis,
      direction,
      startPos: axis === 'horizontal' ? event.clientX : event.clientY,
      startSize: currentSize,
      onUpdate,
      onEnd,
    };

    // Inline-listener (nicht delegated): müssen vom selben target kommen
    // damit PointerCapture greift.
    target.addEventListener('pointermove', this.handleMove);
    target.addEventListener('pointerup', this.handleEnd);
    target.addEventListener('pointercancel', this.handleEnd);

    // Global cursor + selection-prevention.
    this.prevBodyCursor = document.body.style.cursor;
    this.prevBodyUserSelect = document.body.style.userSelect;
    document.body.style.cursor = axis === 'horizontal' ? 'ew-resize' : 'ns-resize';
    document.body.style.userSelect = 'none';

    void panelId; // currently unused for logging — placeholder for future structlog-like trace
  }

  private handleMove = (e: PointerEvent): void => {
    const a = this.active;
    if (!a || e.pointerId !== a.pointerId) return;
    const currentPos = a.axis === 'horizontal' ? e.clientX : e.clientY;
    const delta = (currentPos - a.startPos) * a.direction;
    a.onUpdate(a.startSize + delta);
  };

  private handleEnd = (e: PointerEvent): void => {
    const a = this.active;
    if (!a || e.pointerId !== a.pointerId) return;

    try {
      a.target.releasePointerCapture(a.pointerId);
    } catch {
      // ignore — pointer already released
    }
    a.target.removeEventListener('pointermove', this.handleMove);
    a.target.removeEventListener('pointerup', this.handleEnd);
    a.target.removeEventListener('pointercancel', this.handleEnd);

    document.body.style.cursor = this.prevBodyCursor;
    document.body.style.userSelect = this.prevBodyUserSelect;

    const onEnd = a.onEnd;
    this.active = null;

    // onEnd nach active=null callen damit ein recursive startDrag-call in onEnd
    // (theoretisch) korrekt sieht "kein drag aktiv".
    if (onEnd) {
      try {
        onEnd();
      } catch (err) {
        // eslint-disable-next-line no-console
        console.error('[fp resize-manager] onEnd handler threw:', err);
      }
    }
  };

  /** True wenn aktuell ein Drag aktiv ist. Used für transition-disabling während drag. */
  get isDragging(): boolean {
    return this.active !== null;
  }
}

/** Module-Singleton. */
export const resize = new ResizeManager();
