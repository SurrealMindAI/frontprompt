<!--
  RelationItem — eine Zeile in der Relations-Liste.

  Zeigt: source.selector → (kind-badge) → target.selector + optional note.
  Hover-on setzt uiPrefs.hoveredRelationId → RelationsLayer highlightet die Edge.
  Edit (✏) öffnet inline-popover mit kind-Dropdown + note-textarea.
  Delete (×) entfernt die Relation.
-->
<script lang="ts">
  import { backendState } from '../../../backend-state/backend-state.svelte';
  import { uiPrefs } from '../../../local-state/ui-prefs.svelte';
  import { lookupService, type RelationKind } from '../../../services/relations';
  import Dropdown, { type DropdownOption } from '../../primitives/Dropdown.svelte';
  import type { Relation } from '../../../_generated/state';

  let { relation }: { relation: Relation } = $props();

  const picks = $derived(backendState.inspector.picks);
  const regions = $derived(backendState.inspector.regions);
  const isHovered = $derived(uiPrefs.hoveredRelationId === relation.relation_id);

  /** Source-label: pick.selector wenn pick, region.note (oder "region: <id>") wenn region. */
  const sourceLabel = $derived(
    endpointLabel(relation.source_id, relation.source_kind, picks, regions)
  );
  const targetLabel = $derived(
    endpointLabel(relation.target_id, relation.target_kind, picks, regions)
  );

  function endpointLabel(
    nodeId: string,
    nodeKind: 'pick' | 'region',
    allPicks: typeof picks,
    allRegions: typeof regions
  ): string {
    if (nodeKind === 'pick') {
      const p = lookupService.pickById(nodeId, allPicks);
      return p?.element.selector ?? '(missing)';
    }
    const r = lookupService.regionById(nodeId, allRegions);
    return r?.note?.trim() ? r.note : `region:${nodeId.slice(0, 6)}`;
  }

  function selectEndpoint(nodeId: string, nodeKind: 'pick' | 'region'): void {
    if (nodeKind === 'pick') backendState.inspector.selectPick(nodeId);
    else backendState.inspector.selectRegion(nodeId);
  }

  /** Symmetric (relates_to) → ↔, directed → → */
  const arrow = $derived(relation.kind === 'relates_to' ? '↔' : '→');

  // Edit-popover state — lokal pro RelationItem (kein global service)
  // Initial-werte aus relation kommen via getter-derivation, sonst frozen-at-mount.
  let editing = $state(false);
  let editKind = $state<RelationKind>('relates_to');
  let editNote = $state('');

  const KIND_OPTIONS: DropdownOption<RelationKind>[] = [
    { value: 'relates_to', label: 'relates_to · symmetric link' },
    { value: 'triggers', label: 'triggers · A → B (action)' },
    { value: 'part_of', label: 'part_of · A → B (containment)' },
  ];

  function startEdit(e: MouseEvent): void {
    e.stopPropagation();
    editing = true;
    editKind = relation.kind;
    editNote = relation.note ?? '';
  }

  function commitEdit(): void {
    backendState.inspector.updateRelation(
      relation.relation_id,
      editKind,
      editNote.trim() === '' ? null : editNote.trim()
    );
    editing = false;
  }

  function cancelEdit(): void {
    editing = false;
  }

  function remove(e: MouseEvent): void {
    e.stopPropagation();
    backendState.inspector.deleteRelation(relation.relation_id);
  }

  function selectSource(): void {
    selectEndpoint(relation.source_id, relation.source_kind);
  }

  function selectTarget(): void {
    selectEndpoint(relation.target_id, relation.target_kind);
  }
</script>

<div
  class="rel-item"
  class:rel-item--hovered={isHovered}
  data-kind={relation.kind}
  onmouseenter={() => uiPrefs.hoverRelation(relation.relation_id)}
  onmouseleave={() => uiPrefs.hoverRelation(null)}
  role="listitem"
>
  <div class="rel-item__row">
    <button type="button" class="rel-item__node" onclick={selectSource} title={sourceLabel}>
      {sourceLabel}
    </button>
    <span class="rel-item__arrow" aria-hidden="true">{arrow}</span>
    <span class="rel-item__kind kind-{relation.kind}" title={relation.kind}>{relation.kind}</span>
    <span class="rel-item__arrow" aria-hidden="true">{arrow}</span>
    <button type="button" class="rel-item__node" onclick={selectTarget} title={targetLabel}>
      {targetLabel}
    </button>
    <div class="rel-item__actions">
      <button
        type="button"
        class="icon-btn"
        onclick={startEdit}
        title="Edit kind + note"
        aria-label="Edit relation"
      >
        ✎
      </button>
      <button
        type="button"
        class="icon-btn icon-btn--danger"
        onclick={remove}
        title="Delete relation"
        aria-label="Delete relation"
      >
        ×
      </button>
    </div>
  </div>

  {#if relation.note && !editing}
    <div class="rel-item__note">{relation.note}</div>
  {/if}

  {#if editing}
    <div class="rel-item__edit">
      <Dropdown
        options={KIND_OPTIONS}
        value={editKind}
        onChange={(v) => (editKind = v)}
        ariaLabel="relation kind"
      />
      <textarea
        class="rel-item__note-input"
        bind:value={editNote}
        placeholder="note (optional)"
        rows="2"
      ></textarea>
      <div class="rel-item__edit-actions">
        <button type="button" class="btn-mini" onclick={cancelEdit}>cancel</button>
        <button type="button" class="btn-mini btn-mini--primary" onclick={commitEdit}>save</button>
      </div>
    </div>
  {/if}
</div>

<style>
  .rel-item {
    display: flex;
    flex-direction: column;
    gap: 4px;
    padding: 8px 10px;
    border-bottom: 1px solid var(--fp-color-border-subtle);
    transition: background 120ms ease;
  }

  .rel-item:hover,
  .rel-item--hovered {
    background: var(--fp-color-surface-secondary);
  }

  .rel-item__row {
    display: flex;
    align-items: center;
    gap: 6px;
    min-width: 0;
  }

  .rel-item__node {
    background: transparent;
    border: none;
    color: var(--fp-color-text-primary);
    font-family: 'SF Mono', 'JetBrains Mono', Menlo, Consolas, monospace;
    font-size: 10px;
    cursor: pointer;
    padding: 1px 4px;
    border-radius: 2px;
    text-overflow: ellipsis;
    overflow: hidden;
    white-space: nowrap;
    max-width: 80px;
    flex: 0 1 auto;
    transition:
      background 120ms ease,
      color 120ms ease;
  }

  .rel-item__node:hover {
    background: rgba(120, 180, 255, 0.18);
    color: var(--fp-color-text-primary);
  }

  .rel-item__arrow {
    color: var(--fp-color-text-muted);
    font-size: 12px;
    flex-shrink: 0;
  }

  .rel-item__kind {
    font-size: 9px;
    padding: 2px 6px;
    border-radius: 8px;
    font-family: 'SF Mono', 'JetBrains Mono', Menlo, Consolas, monospace;
    text-transform: lowercase;
    flex-shrink: 0;
  }

  .kind-relates_to {
    background: rgba(120, 220, 255, 0.18);
    color: var(--fp-color-text-primary);
  }

  .kind-triggers {
    background: rgba(255, 109, 209, 0.18);
    color: var(--fp-color-text-primary);
  }

  .kind-part_of {
    background: rgba(157, 255, 177, 0.18);
    color: var(--fp-color-text-primary);
  }

  .rel-item__actions {
    display: flex;
    align-items: center;
    gap: 2px;
    margin-left: auto;
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

  .rel-item__note {
    font-size: 11px;
    color: var(--fp-color-text-secondary);
    font-style: italic;
    padding-left: 4px;
  }

  .rel-item__edit {
    display: flex;
    flex-direction: column;
    gap: 6px;
    padding: 6px;
    background: var(--fp-color-surface-secondary);
    border: 1px solid rgba(120, 180, 255, 0.25);
    border-radius: 3px;
    margin-top: 4px;
  }

  .rel-item__note-input {
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

  .rel-item__note-input:focus {
    border-color: rgba(120, 180, 255, 0.5);
  }

  .rel-item__edit-actions {
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
    border-color: rgba(120, 180, 255, 0.3);
  }

  .btn-mini--primary {
    background: rgba(120, 220, 255, 0.18);
    border-color: rgba(120, 220, 255, 0.5);
    color: var(--fp-color-text-primary);
  }

  .btn-mini--primary:hover {
    background: rgba(120, 220, 255, 0.28);
  }
</style>
