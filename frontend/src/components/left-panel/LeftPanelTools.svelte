<!--
  LeftPanelTools — Tool-Button-Strip im oberen Bereich des linken Panels.

  DIE zentrale Tool-Heimat: pick · region · quick · hide-all. Pick triggert
  pickClaim (single-pick-at-a-time). Region triggert regionDraft (drag-rect-to-
  region UX). Pick/Region sind mutex — wenn pick aktiv, region disabled; wenn
  region drafting, pick disabled (das pick-overlay würde sonst pointer-events
  fangen). Quick togglet den quick-comment-Modus (HUD kollabiert zur Hover-Box,
  schnelles Pick+Kommentar-Loop). Hide-all togglet alle Panels.

  (quick + hide-all lebten früher in der Toolbar des Top-Panels — konsolidiert
  hierher, damit ALLE Tools an einem Ort sind.)
-->
<script lang="ts">
  import { GLOBAL_PICK_ID, pickClaim } from '../../local-state/pick-claim.svelte';
  import { backendState } from '../../backend-state/backend-state.svelte';
  import { quickCommentMode } from '../../local-state/quick-comment-mode.svelte';
  import { regionDraft } from '../../services/regions';
  import PickButton from '../primitives/PickButton.svelte';

  const isPickActive = $derived(pickClaim.isClaimedBy(GLOBAL_PICK_ID));
  const isRegionActive = $derived(regionDraft.drafting);
  const isPickDisabled = $derived(isRegionActive || (pickClaim.current !== null && !isPickActive));
  const isRegionDisabled = $derived(pickClaim.current !== null && !isPickActive);
  const quickActive = $derived(quickCommentMode.active);
  const allHidden = $derived(backendState.panel.allHidden);

  function togglePick(): void {
    if (isPickActive) {
      pickClaim.release();
      return;
    }
    // Default-mode: captured pick wird zur picks-list hinzugefügt.
    pickClaim.acquire({
      id: GLOBAL_PICK_ID,
      onPick: (pick) => backendState.inspector.submitPick(pick),
    });
  }

  function toggleRegion(): void {
    if (isRegionActive) {
      regionDraft.cancel();
      return;
    }
    // Region-mode kollidiert mit pickClaim, release first.
    pickClaim.release();
    regionDraft.start();
  }

  /** Toggle quick-comment mode: collapse the HUD to a hovering box + rapid-comment loop. */
  function toggleQuickComment(): void {
    if (quickCommentMode.active) {
      quickCommentMode.exit();
    } else {
      quickCommentMode.enter();
    }
  }

  function toggleHideAll(): void {
    backendState.panel.toggleHideAll();
  }
</script>

<div class="tools">
  <PickButton
    variant="full"
    active={isPickActive}
    disabled={isPickDisabled}
    onclick={togglePick}
    title={isPickActive ? 'Pick-mode aus' : 'Pick — click + ein Element auf der Page wählen'}
  />
  <button
    type="button"
    class="tool-btn"
    class:tool-btn--active={isRegionActive}
    disabled={isRegionDisabled}
    onclick={toggleRegion}
    aria-pressed={isRegionActive}
    title={isRegionActive ? 'Region-mode aus' : 'Region — drag eine Box auf der Page'}
    aria-label="region"
  >
    <span class="tool-btn__icon" aria-hidden="true">▭</span>
    <span class="tool-btn__label">region</span>
  </button>
  <button
    type="button"
    class="tool-btn"
    class:tool-btn--active={quickActive}
    onclick={toggleQuickComment}
    aria-pressed={quickActive}
    aria-label={quickActive ? 'exit quick-comment mode' : 'enter quick-comment mode'}
    title="quick pick and comment"
  >
    <span class="tool-btn__icon" aria-hidden="true">⚡</span>
    <span class="tool-btn__label">quick</span>
  </button>
  <button
    type="button"
    class="tool-btn"
    onclick={toggleHideAll}
    aria-label={allHidden ? 'show all panels' : 'hide all panels'}
    title={allHidden ? 'Show all panels' : 'Hide all panels'}
  >
    <span class="tool-btn__icon" aria-hidden="true">{allHidden ? '⊞' : '⊟'}</span>
    <span class="tool-btn__label">{allHidden ? 'show all' : 'hide all'}</span>
  </button>
</div>

<style>
  .tools {
    display: flex;
    flex-direction: row;
    flex-wrap: wrap; /* alle Tools (pick/region/quick/hide-all) umbrechen statt überlaufen */
    align-items: center;
    gap: 6px;
    padding: 6px 10px;
    border-bottom: 1px solid var(--fp-color-border-subtle);
    background: var(--fp-color-surface-secondary);
    flex-shrink: 0;
  }

  .tool-btn {
    display: inline-flex;
    align-items: center;
    gap: 4px;
    background: transparent;
    border: 1px solid var(--fp-color-border);
    color: var(--fp-color-text-primary);
    font: inherit;
    font-size: 11px;
    padding: 3px 8px;
    border-radius: 3px;
    cursor: pointer;
    transition:
      background 120ms ease,
      border-color 120ms ease,
      color 120ms ease;
  }

  .tool-btn:hover:not(:disabled) {
    background: var(--fp-color-surface-secondary);
    border-color: rgba(157, 255, 177, 0.4);
  }

  .tool-btn:disabled {
    opacity: 0.4;
    cursor: not-allowed;
  }

  .tool-btn--active {
    background: rgba(157, 255, 177, 0.2);
    border-color: rgba(157, 255, 177, 0.6);
    color: var(--fp-color-text-primary);
  }

  .tool-btn--active:hover:not(:disabled) {
    background: rgba(157, 255, 177, 0.3);
  }

  .tool-btn__icon {
    font-size: 13px;
    line-height: 1;
  }

  .tool-btn__label {
    font-family: 'SF Mono', 'JetBrains Mono', Menlo, Consolas, monospace;
    font-size: 10px;
    text-transform: lowercase;
    letter-spacing: 0.02em;
  }
</style>
