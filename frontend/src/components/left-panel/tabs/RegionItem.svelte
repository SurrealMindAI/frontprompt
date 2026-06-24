<!--
  RegionItem — eine Zeile in der Regions-Liste.

  Zeigt: note (oder fallback "region:<short-id>"), member-pick-count,
  + edit/delete-actions. Click selektiert die Region (right-panel öffnet
  RegionDetails).
-->
<script lang="ts">
  import { backendState } from '../../../backend-state/backend-state.svelte';
  import { colorForIndex } from '../../../services/color-palette';
  import { detectLayoutDrift } from '../../../services/relations';
  import type { Region } from '../../../_generated/state';

  let { region }: { region: Region } = $props();

  const isActive = $derived(backendState.inspector.activeRegionId === region.region_id);
  const memberCount = $derived(region.member_pick_ids?.length ?? 0);
  const regionColor = $derived(colorForIndex(region.color_index ?? 0));

  /** True when the stored viewport snapshot deviates significantly from current page size. */
  const hasDrift = $derived(
    region.viewport_snapshot != null &&
      detectLayoutDrift(
        region.viewport_snapshot,
        document.documentElement.scrollWidth,
        document.documentElement.scrollHeight
      )
  );

  let editing = $state(false);
  let editNote = $state('');

  function selectRegion(): void {
    backendState.inspector.selectRegion(region.region_id);
  }

  function startEdit(e: MouseEvent): void {
    e.stopPropagation();
    editing = true;
    editNote = region.note ?? '';
  }

  function commitEdit(): void {
    backendState.inspector.updateRegion(
      region.region_id,
      editNote.trim() === '' ? null : editNote.trim()
    );
    editing = false;
  }

  function cancelEdit(): void {
    editing = false;
  }

  function remove(e: MouseEvent): void {
    e.stopPropagation();
    backendState.inspector.deleteRegion(region.region_id);
  }

  const displayName = $derived(
    region.note?.trim() ? region.note : `region:${region.region_id.slice(0, 6)}`
  );
</script>

<div
  class="region-item"
  class:region-item--active={isActive}
  onclick={selectRegion}
  onkeydown={(e) => e.key === 'Enter' && selectRegion()}
  role="button"
  tabindex="0"
>
  <div class="region-item__row">
    <span class="region-item__icon" style={`color: ${regionColor}`} aria-hidden="true">▭</span>
    <span class="region-item__name" title={displayName}>{displayName}</span>
    <span class="region-item__count" title="{memberCount} member picks">{memberCount}</span>
    {#if hasDrift}
      <span
        class="region-item__drift"
        title="Region drawn at different page size — rect may be stale">△ drift</span
      >
    {/if}
    <div class="region-item__actions">
      <button
        type="button"
        class="icon-btn"
        onclick={startEdit}
        title="Edit note"
        aria-label="Edit region note">✎</button
      >
      <button
        type="button"
        class="icon-btn icon-btn--danger"
        onclick={remove}
        title="Delete region (members bleiben als picks)"
        aria-label="Delete region">×</button
      >
    </div>
  </div>

  {#if editing}
    <div class="region-item__edit" onclick={(e) => e.stopPropagation()} role="presentation">
      <textarea
        class="region-item__note-input"
        bind:value={editNote}
        placeholder="note (optional)"
        rows="2"
      ></textarea>
      <div class="region-item__edit-actions">
        <button type="button" class="btn-mini" onclick={cancelEdit}>cancel</button>
        <button type="button" class="btn-mini btn-mini--primary" onclick={commitEdit}>save</button>
      </div>
    </div>
  {/if}
</div>

<style>
  .region-item {
    display: flex;
    flex-direction: column;
    gap: 4px;
    padding: 8px 10px;
    border-bottom: 1px solid var(--fp-color-border-subtle);
    cursor: pointer;
    transition: background 120ms ease;
    text-align: left;
  }

  .region-item:hover {
    background: var(--fp-color-surface-secondary);
  }

  .region-item--active {
    background: rgba(157, 255, 177, 0.12);
    border-left: 2px solid rgba(157, 255, 177, 0.7);
  }

  .region-item__row {
    display: flex;
    align-items: center;
    gap: 6px;
    min-width: 0;
  }

  .region-item__icon {
    /* color kommt inline aus der color-palette */
    font-size: 14px;
    line-height: 1;
    flex-shrink: 0;
  }

  .region-item__name {
    color: var(--fp-color-text-primary);
    font-family: 'SF Mono', 'JetBrains Mono', Menlo, Consolas, monospace;
    font-size: 11px;
    text-overflow: ellipsis;
    overflow: hidden;
    white-space: nowrap;
    flex: 1 1 auto;
    min-width: 0;
  }

  .region-item__count {
    background: rgba(120, 180, 255, 0.18);
    color: var(--fp-color-text-primary);
    font-size: 10px;
    padding: 1px 6px;
    border-radius: 8px;
    font-family: 'SF Mono', 'JetBrains Mono', Menlo, Consolas, monospace;
    flex-shrink: 0;
  }

  .region-item__drift {
    background: rgba(255, 200, 100, 0.12);
    color: rgba(255, 200, 100, 0.9);
    font-size: 9px;
    padding: 1px 5px;
    border-radius: 8px;
    font-family: 'SF Mono', 'JetBrains Mono', Menlo, Consolas, monospace;
    flex-shrink: 0;
    cursor: default;
  }

  .region-item__actions {
    display: flex;
    align-items: center;
    gap: 2px;
    flex-shrink: 0;
  }

  .icon-btn {
    background: transparent;
    border: none;
    color: var(--fp-color-text-secondary);
    font-size: 12px;
    cursor: pointer;
    padding: 1px 5px;
    line-height: 1;
    border-radius: 2px;
    transition:
      color 120ms ease,
      background 120ms ease;
  }

  .icon-btn:hover {
    color: var(--fp-color-text-primary);
    background: rgba(120, 180, 255, 0.18);
  }

  .icon-btn--danger:hover {
    color: rgba(255, 140, 140, 0.95);
    background: rgba(255, 80, 80, 0.12);
  }

  .region-item__edit {
    display: flex;
    flex-direction: column;
    gap: 6px;
    padding: 6px;
    background: var(--fp-color-surface-secondary);
    border: 1px solid rgba(157, 255, 177, 0.25);
    border-radius: 3px;
    margin-top: 4px;
  }

  .region-item__note-input {
    background: var(--fp-color-surface-secondary);
    border: 1px solid var(--fp-color-border-subtle);
    color: var(--fp-color-text-primary);
    font: inherit;
    font-size: 11px;
    padding: 4px 6px;
    border-radius: 2px;
    resize: vertical;
    outline: none;
  }

  .region-item__note-input:focus {
    border-color: rgba(157, 255, 177, 0.5);
  }

  .region-item__edit-actions {
    display: flex;
    justify-content: flex-end;
    gap: 6px;
  }

  .btn-mini {
    background: transparent;
    border: 1px solid var(--fp-color-border);
    color: var(--fp-color-text-primary);
    font: inherit;
    font-size: 10px;
    padding: 2px 8px;
    border-radius: 2px;
    cursor: pointer;
    transition:
      background 120ms ease,
      border-color 120ms ease;
  }

  .btn-mini:hover {
    background: var(--fp-color-surface-secondary);
    border-color: rgba(157, 255, 177, 0.3);
  }

  .btn-mini--primary {
    background: rgba(157, 255, 177, 0.18);
    border-color: rgba(157, 255, 177, 0.5);
    color: var(--fp-color-text-primary);
  }

  .btn-mini--primary:hover {
    background: rgba(157, 255, 177, 0.28);
  }
</style>
