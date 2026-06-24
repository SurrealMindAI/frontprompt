<!--
  PickItem — Eine Zeile in der Picks-Liste.

  Zeigt Tag + Selector-Preview + Comment-Preview. Klick selektiert den Pick
  (right-panel rendert Details). Delete-Button entfernt den Pick.
-->

<script lang="ts">
  import { backendState } from '../../../backend-state/backend-state.svelte';
  import { colorForIndex } from '../../../services/color-palette';
  import type { Pick } from '../../../_generated/state';

  let { pick }: { pick: Pick } = $props();

  const isActive = $derived(backendState.inspector.activePickId === pick.pick_id);
  const tag = $derived(pick.element.fingerprint.tag);
  const selector = $derived(pick.element.selector);
  const preview = $derived(pick.element.text_snippet ?? '');
  const commentPreview = $derived((pick.comment ?? '').trim());
  const colorDot = $derived(colorForIndex(pick.color_index ?? 0));

  function select(): void {
    backendState.inspector.selectPick(pick.pick_id);
  }

  function remove(e: MouseEvent): void {
    e.stopPropagation();
    backendState.inspector.deletePick(pick.pick_id);
  }
</script>

<!-- svelte-ignore a11y_click_events_have_key_events a11y_no_static_element_interactions -->
<div class="pick" class:pick--active={isActive} role="button" tabindex="0" onclick={select}>
  <div class="pick__head">
    <span class="pick__color" style={`background: ${colorDot}`} aria-hidden="true"></span>
    <span class="pick__tag">{tag}</span>
    <span class="pick__selector" title={selector}>{selector}</span>
    <button
      type="button"
      class="pick__delete"
      onclick={remove}
      title="Pick löschen"
      aria-label="Pick löschen">×</button
    >
  </div>
  {#if preview}
    <div class="pick__preview">{preview}</div>
  {/if}
  {#if commentPreview}
    <div class="pick__comment">💬 {commentPreview}</div>
  {/if}
</div>

<style>
  .pick {
    display: flex;
    flex-direction: column;
    gap: 4px;
    padding: 8px 10px;
    cursor: pointer;
    border-bottom: 1px solid var(--fp-color-border-subtle);
    transition: background 120ms ease;
  }

  .pick:hover {
    background: var(--fp-color-surface-secondary);
  }

  .pick--active {
    background: rgba(120, 180, 255, 0.12);
    border-left: 2px solid rgba(120, 220, 255, 0.85);
    padding-left: 8px;
  }

  .pick__head {
    display: flex;
    flex-direction: row;
    align-items: center;
    gap: 6px;
    min-width: 0;
  }

  .pick__color {
    display: inline-block;
    width: 10px;
    height: 10px;
    border-radius: 50%;
    flex-shrink: 0;
    box-shadow: 0 0 0 1px rgba(0, 0, 0, 0.4);
  }

  .pick__tag {
    font-family: 'SF Mono', 'JetBrains Mono', Menlo, Consolas, monospace;
    font-size: 10px;
    text-transform: uppercase;
    color: rgba(180, 220, 255, 0.9);
    background: rgba(120, 180, 255, 0.12);
    padding: 1px 5px;
    border-radius: 2px;
    flex-shrink: 0;
  }

  .pick__selector {
    font-family: 'SF Mono', 'JetBrains Mono', Menlo, Consolas, monospace;
    font-size: 11px;
    color: var(--fp-color-text-primary);
    white-space: nowrap;
    overflow: hidden;
    text-overflow: ellipsis;
    flex: 1 1 auto;
    min-width: 0;
  }

  .pick__delete {
    background: transparent;
    border: none;
    color: var(--fp-color-text-secondary);
    font-size: 14px;
    cursor: pointer;
    padding: 0 4px;
    line-height: 1;
    border-radius: 2px;
    transition:
      color 120ms ease,
      background 120ms ease;
    flex-shrink: 0;
  }

  .pick__delete:hover {
    color: rgba(255, 140, 140, 0.95);
    background: rgba(255, 80, 80, 0.12);
  }

  .pick__preview {
    font-size: 11px;
    color: var(--fp-color-text-secondary);
    overflow: hidden;
    text-overflow: ellipsis;
    white-space: nowrap;
  }

  .pick__comment {
    font-size: 11px;
    color: var(--fp-color-text-secondary);
    font-style: italic;
    overflow: hidden;
    text-overflow: ellipsis;
    white-space: nowrap;
  }
</style>
