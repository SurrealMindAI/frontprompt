<!--
  RightPanel — Composition root für das rechte Panel.

  Zeigt (Schema 0.4.0 — mutually exclusive zwischen pick und region):
    - PickDetails + CommentEditor wenn activePick gesetzt
    - RegionDetails wenn activeRegion gesetzt
    - Empty-state wenn weder pick noch region selected
-->

<script lang="ts">
  import { backendState } from '../../backend-state/backend-state.svelte';
  import CommentEditor from './CommentEditor.svelte';
  import PickDetails from './PickDetails.svelte';
  import RegionDetails from './RegionDetails.svelte';

  const activePick = $derived(backendState.inspector.activePick);
  const activeRegion = $derived(backendState.inspector.activeRegion);
</script>

<div class="right-panel">
  {#if activePick}
    <PickDetails pick={activePick} />
    <CommentEditor pickId={activePick.pick_id} initialComment={activePick.comment ?? ''} />
  {:else if activeRegion}
    <RegionDetails region={activeRegion} />
  {:else}
    <div class="empty">
      <p class="empty__hint">Nichts selektiert.</p>
      <p class="empty__sub">
        Click einen Pick in der Picks-Liste oder eine Region in der Regions-Liste — Details
        erscheinen hier.
      </p>
    </div>
  {/if}
</div>

<style>
  .right-panel {
    display: flex;
    flex-direction: column;
    width: 100%;
    height: 100%;
    min-height: 0;
    overflow: auto;
  }

  .empty {
    padding: 16px 14px;
    color: var(--fp-color-text-secondary);
  }

  .empty__hint {
    margin: 0 0 4px 0;
    font-size: 12px;
    font-weight: 500;
  }

  .empty__sub {
    margin: 0;
    font-size: 11px;
    color: var(--fp-color-text-secondary);
    line-height: 1.5;
  }
</style>
