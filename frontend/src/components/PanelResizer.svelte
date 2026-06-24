<!--
  PanelResizer — dünner Drag-Strip am inner-edge des Panels.
  Nur sichtbar wenn Panel open ist (resize-while-collapsed macht keinen Sinn).

  Direction per panel:
    left:   horizontal, +1 (drag right grows)
    right:  horizontal, -1 (drag left grows)
    top:    vertical,   +1 (drag down grows)
    bottom: vertical,   -1 (drag up grows)
-->

<script lang="ts">
  import { backendState } from '../backend-state/backend-state.svelte';
  import type { PanelId } from '../backend-state/panel-state.svelte';
  import { PANEL_CONFIGS } from '../backend-state/panel-state.svelte';
  import type { ResizeDirection } from '../managers/resize-manager.svelte';
  import { resize } from '../managers/resize-manager.svelte';

  let { id }: { id: PanelId } = $props();

  const config = $derived(PANEL_CONFIGS[id]);
  const isHorizontal = $derived(config.axis === 'horizontal');
  const direction = $derived<ResizeDirection>(id === 'left' || id === 'top' ? 1 : -1);

  function onPointerDown(event: PointerEvent) {
    resize.startDrag(
      id,
      config.axis,
      direction,
      event,
      backendState.panel.panels[id].size,
      // pointermove: optimistic local update only
      (newSize) => backendState.panel.resizePanel(id, newSize),
      // pointerup (drag-end): send final size ans backend
      () => backendState.panel.commitResize(id)
    );
  }
</script>

<div
  class="resizer"
  class:resizer--horizontal={isHorizontal}
  class:resizer--vertical={!isHorizontal}
  onpointerdown={onPointerDown}
  role="separator"
  aria-orientation={isHorizontal ? 'vertical' : 'horizontal'}
  aria-label="resize {id} panel"
></div>

<style>
  .resizer {
    flex-shrink: 0;
    background: transparent;
    transition: background 120ms ease;
    touch-action: none;
    pointer-events: auto;
  }

  /* Horizontal-axis (left/right): vertical strip, ew-resize cursor */
  .resizer--horizontal {
    width: 4px;
    height: 100%;
    cursor: ew-resize;
  }

  /* Vertical-axis (top/bottom): horizontal strip, ns-resize cursor */
  .resizer--vertical {
    height: 4px;
    width: 100%;
    cursor: ns-resize;
  }

  .resizer:hover {
    background: rgba(120, 180, 255, 0.4);
  }

  .resizer:active {
    background: rgba(120, 180, 255, 0.7);
  }
</style>
