<!--
  FloatingRecorderToolbar — schwebende HUD-Toolbar für aktive Recording-Sessions.

  Wird von App.svelte nur dann gemountet wenn ``recorder.isActive === true``
  (``{#if recorder.isActive}<FloatingRecorderToolbar />{/if}``).

  Enthält drei Aktionen:
    ⏹ Stop  — recorder.stop() → beendet aktive Recording
    ▭ Region — regionDraft.start() → öffnet Region-Draw-Mode (während Recording)
    🎯 Pick  — pickClaim.acquire({ id: 'pick:recorder-toolbar', ... })

  Die Toolbar ist draggbar: Pointer-Events auf dem Drag-Handle (.drag-handle)
  verschieben ``recorder.floatingToolbarPosition`` via ``recorder.moveToolbar()``.
  Pointer-Capture verhindert Slip-out beim schnellen Ziehen. recorder.activeDragHandle
  hält die aktive pointerId (null = kein aktiver Drag).

  Positionierung: ``position: fixed`` mit left/top aus ``recorder.floatingToolbarPosition``.
  Rendert INNERHALB des ``<fp-overlay>``-Shadow-Root → der ``isHudChrome``-Prädikat
  (``in_fp_overlay && !in_inspector_layer``) schließt alle Toolbar-Clicks korrekt von
  der durable Recording-Capture aus. Kein Code-Change nötig.

  window.__fp: diese Komponente erzeugt KEINE Globals mit Unterstrich-Suffix.
  Nur ``window.__fp`` (single global) ist erlaubt — Arch-test guards this.
-->
<script lang="ts">
  import { recorder } from '../local-state/recorder.svelte';
  import { regionDraft } from '../services/regions';
  import { pickClaim } from '../local-state/pick-claim.svelte';
  import { backendState } from '../backend-state/backend-state.svelte';

  const pos = $derived(recorder.floatingToolbarPosition);
  const recorderActive = $derived(recorder.isActive);

  // Active recording display name for the status label.
  const activeRecordingName = $derived(backendState.recordings.activeRecording?.name ?? 'Recording…');

  // ----- Drag-Handle -------------------------------------------------------

  /** Drag-State: origin des pointer-down + Toolbar-Position zu diesem Zeitpunkt. */
  let dragOrigin = $state<{ px: number; py: number; tx: number; ty: number } | null>(null);

  function handleDragStart(e: PointerEvent): void {
    // Only primary button drag.
    if (e.button !== 0) return;
    e.preventDefault();
    e.stopPropagation();

    const target = e.currentTarget as HTMLElement;
    try {
      target.setPointerCapture(e.pointerId);
    } catch {
      return;
    }

    dragOrigin = {
      px: e.clientX,
      py: e.clientY,
      tx: recorder.floatingToolbarPosition.x,
      ty: recorder.floatingToolbarPosition.y,
    };
    recorder.activeDragHandle = String(e.pointerId);

    target.addEventListener('pointermove', handleDragMove);
    target.addEventListener('pointerup', handleDragEnd);
    target.addEventListener('pointercancel', handleDragEnd);
  }

  function handleDragMove(e: PointerEvent): void {
    if (!dragOrigin) return;
    const dx = e.clientX - dragOrigin.px;
    const dy = e.clientY - dragOrigin.py;
    recorder.moveToolbar({
      x: Math.max(0, dragOrigin.tx + dx),
      y: Math.max(0, dragOrigin.ty + dy),
    });
  }

  function handleDragEnd(e: PointerEvent): void {
    const target = e.currentTarget as HTMLElement;
    try {
      target.releasePointerCapture(e.pointerId);
    } catch {
      // ignore
    }
    target.removeEventListener('pointermove', handleDragMove);
    target.removeEventListener('pointerup', handleDragEnd);
    target.removeEventListener('pointercancel', handleDragEnd);
    dragOrigin = null;
    recorder.activeDragHandle = null;
  }

  // ----- Actions ------------------------------------------------------------

  function onStop(): void {
    recorder.stop();
  }

  function onDrawRegion(): void {
    // Region tool works normally during recording; recorded as timeline entry
    // by the pick/region auto-link path (sub-plan 04).
    pickClaim.release();
    regionDraft.start();
  }

  function onPick(): void {
    // Acquire pick-mode scoped to the recorder toolbar. The picked element is
    // auto-linked to the active recording timeline via the existing submitPick
    // path (sub-plan 01 StateManager.add_pick() auto-link).
    pickClaim.acquire({
      id: 'pick:recorder-toolbar',
      onPick: (pick) => backendState.inspector.submitPick(pick),
    });
  }
</script>

{#if recorderActive}
  <!--
    position: fixed so the toolbar sits above the host page and is not affected
    by the grid layout. left/top derived from recorder.floatingToolbarPosition (localState).
    pointer-events: auto so buttons are clickable while page stays pick-through.
  -->
  <div
    class="rec-toolbar"
    style:left="{pos.x}px"
    style:top="{pos.y}px"
    role="toolbar"
    aria-label="Recorder toolbar"
  >
    <!--
      Drag handle: grabbing the top bar repositions the toolbar.
      No text / buttons — just a visual grip area.
    -->
    <div
      class="rec-toolbar__drag-handle"
      onpointerdown={handleDragStart}
      title="Drag to move"
      aria-hidden="true"
    >
      <span class="rec-toolbar__recording-dot" aria-hidden="true">⏺</span>
      <span class="rec-toolbar__label">{activeRecordingName}</span>
    </div>

    <!-- Actions row -->
    <div class="rec-toolbar__actions">
      <button
        type="button"
        class="rec-btn rec-btn--stop"
        onclick={onStop}
        aria-label="Stop recording"
        title="Stop recording"
      >
        <span aria-hidden="true">⏹</span>
        <span class="rec-btn__label">Stop</span>
      </button>

      <button
        type="button"
        class="rec-btn"
        onclick={onDrawRegion}
        aria-label="Draw region"
        title="Draw a region on the page"
      >
        <span aria-hidden="true">▭</span>
        <span class="rec-btn__label">Region</span>
      </button>

      <button
        type="button"
        class="rec-btn"
        onclick={onPick}
        aria-label="Pick element"
        title="Pick an element on the page"
      >
        <span aria-hidden="true">🎯</span>
        <span class="rec-btn__label">Pick</span>
      </button>
    </div>
  </div>
{/if}

<style>
  .rec-toolbar {
    position: fixed;
    z-index: 100;
    display: flex;
    flex-direction: column;
    background: rgba(18, 18, 26, 0.96);
    border: 1px solid rgba(255, 80, 80, 0.5);
    border-radius: 6px;
    box-shadow: 0 4px 16px rgba(0, 0, 0, 0.5);
    min-width: 120px;
    pointer-events: auto;
    user-select: none;
  }

  .rec-toolbar__drag-handle {
    display: flex;
    align-items: center;
    gap: 6px;
    padding: 5px 8px 4px;
    cursor: grab;
    border-bottom: 1px solid rgba(255, 80, 80, 0.25);
    border-radius: 5px 5px 0 0;
  }

  .rec-toolbar__drag-handle:active {
    cursor: grabbing;
  }

  .rec-toolbar__recording-dot {
    font-size: 10px;
    color: #ff5050;
    /* Pulsing dot to signal live recording. */
    animation: rec-pulse 1.2s ease-in-out infinite;
  }

  @keyframes rec-pulse {
    0%,
    100% {
      opacity: 1;
    }
    50% {
      opacity: 0.35;
    }
  }

  .rec-toolbar__label {
    font-family: 'SF Mono', 'JetBrains Mono', Menlo, Consolas, monospace;
    font-size: 10px;
    color: rgba(230, 230, 240, 0.72);
    letter-spacing: 0.02em;
    max-width: 90px;
    overflow: hidden;
    text-overflow: ellipsis;
    white-space: nowrap;
  }

  .rec-toolbar__actions {
    display: flex;
    flex-direction: column;
    gap: 2px;
    padding: 4px;
  }

  .rec-btn {
    display: flex;
    align-items: center;
    gap: 6px;
    padding: 4px 8px;
    background: transparent;
    border: 1px solid rgba(255, 255, 255, 0.1);
    border-radius: 3px;
    color: rgba(230, 230, 240, 0.9);
    font: inherit;
    font-size: 11px;
    cursor: pointer;
    text-align: left;
    transition: background 120ms ease;
  }

  .rec-btn:hover {
    background: rgba(255, 255, 255, 0.08);
    border-color: rgba(255, 255, 255, 0.2);
  }

  .rec-btn--stop {
    border-color: rgba(255, 80, 80, 0.4);
    color: #ff9f9f;
  }

  .rec-btn--stop:hover {
    background: rgba(255, 80, 80, 0.15);
  }

  .rec-btn__label {
    font-family: 'SF Mono', 'JetBrains Mono', Menlo, Consolas, monospace;
    font-size: 10px;
    text-transform: lowercase;
    letter-spacing: 0.02em;
  }
</style>
