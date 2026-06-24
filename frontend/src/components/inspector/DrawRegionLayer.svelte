<!--
  DrawRegionLayer — full-viewport pointer-overlay für rect-drag.

  Aktiv wenn ``regionDraft.drafting`` true ist. User-Flow:
    1. Click Region-Tool im LeftPanelTools → regionDraft.start() → drafting=true
    2. Pointer-down auf der Page → regionDraft.setOrigin()
    3. Pointer-move → regionDraft.updateCurrent() → live rect-preview
    4. Pointer-up → regionDraft.commit() → scan DOM, build picks, persist Region
    ESC → regionDraft.cancel()

  Layer ist sibling zum InspectorLayer im Shadow DOM. Eines zur Zeit aktiv
  (über Toolbar-button-toggle gesteuert — Phase-1 nutzt nicht den pickClaim
  da der Layer eine andere Mechanik hat).
-->
<script lang="ts">
  import { regionDraft } from '../../services/regions';
  import { keyboard } from '../../services/keyboard/keyboard.svelte';
  import { forwardWheel } from '../../services/scroll-router';
  import { contrastingColor } from '../../services/color-contrast';

  // Mint affordance hue, lightness-adapted against the page background so the
  // region preview always stands out (task "dynamisch färben"). The layer covers
  // the page, so we sample the page-level background (document.body) rather than
  // a per-element one — the draft rect spans arbitrary content anyway.
  const accent = contrastingColor('hsl(143, 85%, 68%)', document.body);

  function onPointerDown(e: PointerEvent): void {
    e.preventDefault();
    e.stopPropagation();
    if (e.button !== 0) return; // nur linksklick
    regionDraft.setOrigin(e.clientX, e.clientY);
    (e.target as Element).setPointerCapture?.(e.pointerId);
  }

  function onPointerMove(e: PointerEvent): void {
    if (regionDraft.origin === null) return;
    regionDraft.updateCurrent(e.clientX, e.clientY);
  }

  function onPointerUp(e: PointerEvent): void {
    e.preventDefault();
    e.stopPropagation();
    regionDraft.commit();
  }

  /**
   * Wheel-forwarding via scroll-router service — Layer hat pointer-events:auto
   * (für die drag-erkennung), würde sonst wheel-events schlucken und scroll
   * ginge nicht. Analog zum InspectorLayer-fix (R29 google-dsgvo-bug).
   * scroll-router findet den korrekten scrollable ancestor unter dem mouse-
   * cursor (auch inner-div-scrolls wie cookie-consent-modals).
   */
  function onWheel(e: WheelEvent): void {
    forwardWheel(e);
  }

  $effect(() => {
    const unsubEsc = keyboard.subscribe('Escape', () => {
      regionDraft.cancel();
    });
    return unsubEsc;
  });
</script>

<!-- svelte-ignore a11y_no_static_element_interactions -->
<div
  class="draw-region-layer"
  style:--fp-region-accent={accent}
  onpointerdown={onPointerDown}
  onpointermove={onPointerMove}
  onpointerup={onPointerUp}
  onwheel={onWheel}
>
  {#if regionDraft.rect}
    <div
      class="draw-region-preview"
      style:left="{regionDraft.rect.x}px"
      style:top="{regionDraft.rect.y}px"
      style:width="{regionDraft.rect.width}px"
      style:height="{regionDraft.rect.height}px"
    ></div>
  {/if}

  {#if regionDraft.origin === null}
    <div class="draw-region-hint">Drag to mark a region · ESC to cancel</div>
  {/if}
</div>

<style>
  .draw-region-layer {
    position: fixed;
    inset: 0;
    z-index: 2;
    pointer-events: auto;
    cursor: crosshair;
    background: rgba(10, 12, 24, 0.06);
  }

  .draw-region-preview {
    position: absolute;
    pointer-events: none;
    background: color-mix(in srgb, var(--fp-region-accent) 14%, transparent);
    border: 2px dashed var(--fp-region-accent);
    border-radius: 2px;
    box-shadow: 0 0 12px color-mix(in srgb, var(--fp-region-accent) 35%, transparent);
  }

  .draw-region-hint {
    position: fixed;
    bottom: 12px;
    left: 50%;
    transform: translateX(-50%);
    background: rgba(22, 25, 36, 0.92);
    color: rgba(220, 240, 230, 0.95);
    padding: 6px 12px;
    border: 1px solid rgba(157, 255, 177, 0.4);
    border-radius: 4px;
    font-family: 'SF Mono', 'JetBrains Mono', Menlo, Consolas, monospace;
    font-size: 11px;
    pointer-events: none;
  }
</style>
