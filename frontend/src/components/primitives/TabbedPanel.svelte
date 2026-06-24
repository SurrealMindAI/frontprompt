<!--
  TabbedPanel — generic reusable tabbed container, **controlled-component**.

  API:
    <TabbedPanel
      tabs={[{ id: 'picks', label: 'Picks' }, ...]}
      activeId={someStateVar}
      onActiveIdChange={(id) => someStateVar = id}
    >
      {#snippet content(activeId)}
        ...
      {/snippet}
    </TabbedPanel>

  Controlled-component: caller besitzt activeId-state. Erlaubt external
  control (z.B. Toolbar-status-click setzt activeId in ui-prefs). Wenn caller
  nur "self-managed" tab will, einfach lokale ``let active = $state(...)``
  + ``bind:activeId={active}`` würde via callback gehen — oder mit
  ``activeId={active}`` + ``onActiveIdChange={(id) => active = id}``.
-->

<script lang="ts">
  import type { Snippet } from 'svelte';

  export interface Tab {
    /** Stable id for state tracking. */
    id: string;
    /** Display-label im Tab-Header. */
    label: string;
  }

  let {
    tabs,
    activeId,
    onActiveIdChange,
    content,
  }: {
    tabs: readonly Tab[];
    activeId: string;
    onActiveIdChange: (id: string) => void;
    content: Snippet<[string]>;
  } = $props();

  function selectTab(id: string): void {
    onActiveIdChange(id);
  }
</script>

<div class="tabbed-panel">
  <div class="tabs" role="tablist">
    {#each tabs as tab (tab.id)}
      <button
        type="button"
        role="tab"
        class="tab"
        class:tab--active={activeId === tab.id}
        aria-selected={activeId === tab.id}
        onclick={() => selectTab(tab.id)}
      >
        {tab.label}
      </button>
    {/each}
  </div>
  <div class="tab-content" role="tabpanel">
    {@render content(activeId)}
  </div>
</div>

<style>
  .tabbed-panel {
    display: flex;
    flex-direction: column;
    width: 100%;
    height: 100%;
    min-height: 0;
  }

  .tabs {
    display: flex;
    flex-direction: row;
    gap: 1px;
    border-bottom: 1px solid var(--fp-color-border-subtle);
    background: var(--fp-color-surface-secondary);
    flex-shrink: 0;
  }

  .tab {
    background: transparent;
    border: none;
    color: rgba(180, 200, 255, 0.6);
    font: inherit;
    font-size: 11px;
    font-weight: 500;
    letter-spacing: 0.02em;
    text-transform: lowercase;
    padding: 6px 12px;
    cursor: pointer;
    transition:
      color 120ms ease,
      background 120ms ease,
      border-color 120ms ease;
    border-bottom: 2px solid transparent;
    margin-bottom: -1px;
  }

  .tab:hover {
    color: var(--fp-color-text-primary);
    background: var(--fp-color-surface-secondary);
  }

  .tab--active {
    color: var(--fp-color-text-primary);
    border-bottom-color: rgba(120, 180, 255, 0.85);
  }

  .tab-content {
    flex: 1 1 auto;
    min-height: 0;
    overflow: auto;
  }
</style>
