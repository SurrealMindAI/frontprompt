<!--
  RegionsTab — Tab im LeftPanel: Region-Liste + hint zum Region-tool.

  Schema 0.4.0. Regions sind räumliche Container über Picks. Erzeugt werden sie
  über das Region-Tool im LeftPanelTools (drag-rect auf der Page).
-->
<script lang="ts">
  import { backendState } from '../../../backend-state/backend-state.svelte';
  import { overlayContext } from '../../../services/context/overlay-context.svelte';
  import { visibleGroups } from '../../../services/visibility/visible-groups';
  import { regionDomain } from '../../../services/visibility/hostname';
  import { regionDraft } from '../../../services/regions';
  import RegionItem from './RegionItem.svelte';

  const regions = $derived(backendState.inspector.regions);
  const picksById = $derived(new Map(backendState.inspector.picks.map((p) => [p.pick_id, p])));

  const groups = $derived(
    visibleGroups(regions, {
      currentSessionId: overlayContext.currentSessionId,
      currentHostname: overlayContext.hostname() ?? '',
      domainOf: (r) => regionDomain(r, picksById),
    })
  );
</script>

<div class="regions-tab">
  <div class="header">
    <button
      type="button"
      class="header__btn"
      class:header__btn--active={regionDraft.drafting}
      onclick={() => (regionDraft.drafting ? regionDraft.cancel() : regionDraft.start())}
    >
      {regionDraft.drafting ? 'Cancel region draw' : '+ Draw region'}
    </button>
    <span class="header__hint">
      {regionDraft.drafting
        ? 'Drag a rect on the page to mark a region.'
        : 'Draw a rectangle on the page to capture multiple elements at once.'}
    </span>
  </div>

  <div class="list-header">
    <span class="list-header__count">{regions.length} region{regions.length === 1 ? '' : 's'}</span>
  </div>

  {#if groups.length === 0}
    <div class="empty">
      <p class="empty__title">No regions yet.</p>
      <p class="empty__hint">
        Click <strong>+ Draw region</strong> above, then drag a rectangle on the page. Every element inside
        becomes a pick; they're collected as members of the region.
      </p>
    </div>
  {:else}
    <div class="list" role="list">
      {#each groups as g (g.hostname)}
        <div class="group-header">{g.hostname}</div>
        {#each g.items as { entity, isOwned } (entity.region_id)}
          <div class="row" class:foreign={!isOwned}>
            <RegionItem region={entity} />
          </div>
        {/each}
      {/each}
    </div>
  {/if}
</div>

<style>
  .regions-tab {
    display: flex;
    flex-direction: column;
    width: 100%;
    height: 100%;
    min-height: 0;
  }

  .header {
    display: flex;
    flex-direction: column;
    gap: 4px;
    padding: 8px 10px;
    border-bottom: 1px solid var(--fp-color-border-subtle);
    background: var(--fp-color-surface-secondary);
    flex-shrink: 0;
  }

  .header__btn {
    background: rgba(157, 255, 177, 0.18);
    border: 1px solid rgba(157, 255, 177, 0.45);
    color: var(--fp-color-text-primary);
    font: inherit;
    font-size: 11px;
    padding: 4px 10px;
    border-radius: 3px;
    cursor: pointer;
    transition:
      background 120ms ease,
      border-color 120ms ease;
    align-self: flex-start;
  }

  .header__btn:hover {
    background: rgba(157, 255, 177, 0.28);
    border-color: rgba(157, 255, 177, 0.7);
  }

  .header__btn--active {
    background: rgba(255, 180, 120, 0.18);
    border-color: rgba(255, 180, 120, 0.6);
    color: var(--fp-color-text-primary);
  }

  .header__hint {
    font-size: 10px;
    color: var(--fp-color-text-muted);
  }

  .list-header {
    padding: 6px 10px;
    border-bottom: 1px solid var(--fp-color-border-subtle);
    background: var(--fp-color-surface-secondary);
    flex-shrink: 0;
  }

  .list-header__count {
    font-size: 9px;
    text-transform: uppercase;
    letter-spacing: 0.05em;
    color: var(--fp-color-text-muted);
  }

  .empty {
    padding: 16px 14px;
    color: var(--fp-color-text-secondary);
  }

  .empty__title {
    margin: 0 0 4px 0;
    font-size: 12px;
    font-weight: 500;
  }

  .empty__hint {
    margin: 0;
    font-size: 11px;
    color: var(--fp-color-text-secondary);
    line-height: 1.5;
  }

  .list {
    flex: 1 1 auto;
    overflow: auto;
    min-height: 0;
  }

  .group-header {
    font-size: 9px;
    text-transform: uppercase;
    letter-spacing: 0.05em;
    color: var(--fp-color-text-muted);
    padding: 5px 10px 3px;
    background: var(--fp-color-surface-secondary);
    border-bottom: 1px solid var(--fp-color-border-subtle);
    position: sticky;
    top: 0;
  }

  .foreign {
    opacity: 0.55;
  }
</style>
