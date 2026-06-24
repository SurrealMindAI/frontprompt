<!--
  RelationsTab — Tab im LeftPanel: Draft-UI + Relations-Liste.

  Workflow (DnD raus, PickPicker rein):
    1. User clickt "+ Create relation" → relationDraft.start()
    2. Source-PickPicker: aus Dropdown wählen ODER "Inspect"-Button → DOM-element
       picken → wird zur picks-list hinzugefügt UND als source gesetzt
    3. Target-PickPicker analog
    4. User wählt kind (Dropdown) + note (textarea)
    5. User clickt "Create" → relationDraft.commit() → wire-envelope

  Vorteil ggü. der ersten DnD-Variante: kein Tab-switching mehr (Picks vs
  Relations), Picker funktioniert mit existierenden Picks UND erlaubt ad-hoc
  Selection. Inspector-tool ist generisch (event-driven, DRY).
-->
<script lang="ts">
  import { backendState } from '../../../backend-state/backend-state.svelte';
  import { overlayContext } from '../../../services/context/overlay-context.svelte';
  import { visibleGroups } from '../../../services/visibility/visible-groups';
  import { relationDomain } from '../../../services/visibility/hostname';
  import { relationDraft, type RelationKind } from '../../../services/relations';
  import Dropdown, { type DropdownOption } from '../../primitives/Dropdown.svelte';
  import NodePicker from '../../primitives/NodePicker.svelte';
  import RelationItem from './RelationItem.svelte';

  const inspector = backendState.inspector;
  const relations = $derived(inspector.relations);

  const picksById = $derived(new Map(inspector.picks.map((p) => [p.pick_id, p])));
  const regionsById = $derived(new Map(inspector.regions.map((r) => [r.region_id, r])));

  const groups = $derived(
    visibleGroups(relations, {
      currentSessionId: overlayContext.currentSessionId,
      currentHostname: overlayContext.hostname() ?? '',
      domainOf: (rel) => relationDomain(rel, picksById, regionsById),
    })
  );

  const isSelfLoopAttempt = $derived(
    relationDraft.source !== null &&
      relationDraft.target !== null &&
      relationDraft.source.id === relationDraft.target.id &&
      relationDraft.source.kind === relationDraft.target.kind
  );

  const KIND_OPTIONS: DropdownOption<RelationKind>[] = [
    { value: 'relates_to', label: 'relates_to · symmetric link' },
    { value: 'triggers', label: 'triggers · A → B (action)' },
    { value: 'part_of', label: 'part_of · A → B (containment)' },
  ];
</script>

<div class="relations-tab">
  <div class="header">
    {#if !relationDraft.drafting}
      <button type="button" class="create-btn" onclick={() => relationDraft.start()}>
        + Create relation
      </button>
      <span class="header__hint">Pick two elements and connect them.</span>
    {/if}
  </div>

  {#if relationDraft.drafting}
    <div class="draft">
      <div class="draft__endpoints">
        <NodePicker
          label="Source"
          value={relationDraft.source}
          onChange={(ref) => relationDraft.setSource(ref)}
          excludeRef={relationDraft.target}
          claimId="node-picker:source"
        />

        <span class="draft__arrow" aria-hidden="true">→</span>

        <NodePicker
          label="Target"
          value={relationDraft.target}
          onChange={(ref) => relationDraft.setTarget(ref)}
          excludeRef={relationDraft.source}
          claimId="node-picker:target"
        />
      </div>

      {#if isSelfLoopAttempt}
        <div class="warning">Source and target must differ — pick a different element.</div>
      {/if}

      <div class="config">
        <label class="config__label" for="rel-kind">Kind</label>
        <Dropdown
          options={KIND_OPTIONS}
          value={relationDraft.kind}
          onChange={(v) => relationDraft.setKind(v)}
          ariaLabel="relation kind"
        />
      </div>

      <textarea
        class="note-input"
        placeholder="note (optional) — e.g. 'opens checkout modal'"
        value={relationDraft.note}
        oninput={(e) => relationDraft.setNote(e.currentTarget.value)}
        rows="2"
      ></textarea>

      <div class="actions">
        <button type="button" class="btn-mini" onclick={() => relationDraft.cancel()}>
          cancel
        </button>
        <button
          type="button"
          class="btn-mini btn-mini--primary"
          disabled={!relationDraft.canCommit}
          onclick={() => relationDraft.commit()}
        >
          create
        </button>
      </div>
    </div>
  {/if}

  <div class="list-header">
    <span class="list-header__count"
      >{relations.length} relation{relations.length === 1 ? '' : 's'}</span
    >
  </div>

  {#if groups.length === 0}
    <div class="empty">
      <p class="empty__title">No relations yet.</p>
      <p class="empty__hint">
        Click <strong>+ Create relation</strong> above to connect two picks.
      </p>
    </div>
  {:else}
    <div class="list" role="list">
      {#each groups as g (g.hostname)}
        <div class="group-header">{g.hostname}</div>
        {#each g.items as { entity, isOwned } (entity.relation_id)}
          <div class="row" class:foreign={!isOwned}>
            <RelationItem relation={entity} />
          </div>
        {/each}
      {/each}
    </div>
  {/if}
</div>

<style>
  .relations-tab {
    display: flex;
    flex-direction: column;
    width: 100%;
    height: 100%;
    min-height: 0;
  }

  .header {
    display: flex;
    align-items: center;
    gap: 8px;
    padding: 8px 10px;
    border-bottom: 1px solid var(--fp-color-border-subtle);
    background: var(--fp-color-surface-secondary);
    flex-shrink: 0;
  }

  .create-btn {
    background: rgba(120, 220, 255, 0.18);
    border: 1px solid rgba(120, 220, 255, 0.45);
    color: var(--fp-color-text-primary);
    font: inherit;
    font-size: 11px;
    padding: 4px 10px;
    border-radius: 3px;
    cursor: pointer;
    transition:
      background 120ms ease,
      border-color 120ms ease;
  }

  .create-btn:hover {
    background: rgba(120, 220, 255, 0.28);
    border-color: rgba(120, 220, 255, 0.7);
  }

  .header__hint {
    font-size: 10px;
    color: var(--fp-color-text-muted);
  }

  .draft {
    padding: 10px;
    border-bottom: 1px solid var(--fp-color-border-subtle);
    background: var(--fp-color-surface-secondary);
    display: flex;
    flex-direction: column;
    gap: 10px;
    flex-shrink: 0;
  }

  .draft__endpoints {
    display: flex;
    align-items: center;
    gap: 6px;
  }

  .draft__endpoints > :global(.node-picker) {
    flex: 1 1 0;
    min-width: 0;
  }

  .draft__arrow {
    align-self: flex-end;
    color: var(--fp-color-text-muted);
    font-size: 14px;
    padding-bottom: 6px;
  }

  .warning {
    font-size: 10px;
    color: rgba(255, 180, 120, 0.9);
    padding: 4px 6px;
    background: rgba(255, 180, 120, 0.08);
    border-radius: 2px;
  }

  .config {
    display: flex;
    align-items: center;
    gap: 8px;
  }

  .config__label {
    font-size: 10px;
    color: var(--fp-color-text-secondary);
    text-transform: uppercase;
    letter-spacing: 0.05em;
  }

  .note-input {
    background: var(--fp-color-surface-secondary);
    border: 1px solid var(--fp-color-border-subtle);
    color: var(--fp-color-text-primary);
    font: inherit;
    font-size: 11px;
    padding: 5px 8px;
    border-radius: 2px;
    outline: none;
    resize: vertical;
  }

  .note-input:focus {
    border-color: rgba(120, 180, 255, 0.5);
  }

  .actions {
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
    padding: 3px 12px;
    border-radius: 2px;
    cursor: pointer;
    transition:
      background 120ms ease,
      border-color 120ms ease;
  }

  .btn-mini:hover:not(:disabled) {
    background: var(--fp-color-surface-secondary);
    border-color: rgba(120, 180, 255, 0.3);
  }

  .btn-mini:disabled {
    opacity: 0.4;
    cursor: not-allowed;
  }

  .btn-mini--primary {
    background: rgba(120, 220, 255, 0.18);
    border-color: rgba(120, 220, 255, 0.5);
    color: var(--fp-color-text-primary);
  }

  .btn-mini--primary:hover:not(:disabled) {
    background: rgba(120, 220, 255, 0.28);
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
