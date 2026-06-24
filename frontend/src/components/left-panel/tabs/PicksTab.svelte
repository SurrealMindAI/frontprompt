<!--
  PicksTab — Liste aller gepickten Elements im linken Panel.

  Empty-state: hinweis dass User Inspector aktivieren kann.
-->

<script lang="ts">
  import { backendState } from '../../../backend-state/backend-state.svelte';
  import { overlayContext } from '../../../services/context/overlay-context.svelte';
  import { visibleGroups } from '../../../services/visibility/visible-groups';
  import { pickDomain } from '../../../services/visibility/hostname';
  import PickItem from './PickItem.svelte';

  const picks = $derived(backendState.inspector.picks);

  const groups = $derived(
    visibleGroups(picks, {
      currentSessionId: overlayContext.currentSessionId,
      currentHostname: overlayContext.hostname() ?? '',
      domainOf: (p) => pickDomain(p),
    })
  );
</script>

<div class="picks-tab">
  {#if groups.length === 0}
    <div class="empty">
      <p class="empty__hint">Noch keine Picks.</p>
      <p class="empty__sub">
        Click oben auf <strong>inspect</strong>, dann ein Element auf der Page wählen.
      </p>
    </div>
  {:else}
    <div class="list">
      {#each groups as g (g.hostname)}
        <div class="group-header">{g.hostname}</div>
        {#each g.items as { entity, isOwned } (entity.pick_id)}
          <div class="row" class:foreign={!isOwned}>
            <PickItem pick={entity} />
          </div>
        {/each}
      {/each}
    </div>
  {/if}
</div>

<style>
  .picks-tab {
    width: 100%;
    height: 100%;
    display: flex;
    flex-direction: column;
    min-height: 0;
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
