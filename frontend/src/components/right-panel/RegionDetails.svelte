<!--
  RegionDetails — read-only details + Relations-section für active Region.

  Analog PickDetails. Zeigt: region_id (short), rect (x/y/w/h),
  member-pick-count + Liste der members (clickable → select pick),
  + Relations-section (lookup-service mit nodeKind="region").
  Note-edit ist im RegionItem (left-panel) — Konsistenz mit PickDetails
  vs CommentEditor wäre zu separieren in Phase 2.
-->
<script lang="ts">
  import { backendState } from '../../backend-state/backend-state.svelte';
  import { uiPrefs } from '../../local-state/ui-prefs.svelte';
  import { lookupService } from '../../services/relations';
  import type { Region } from '../../_generated/state';

  let { region }: { region: Region } = $props();

  const allPicks = $derived(backendState.inspector.picks);
  const allRegions = $derived(backendState.inspector.regions);

  const relationsView = $derived(
    lookupService.relationsFor(region.region_id, 'region', backendState.inspector.relations)
  );

  // Members als clickable list
  const members = $derived(
    (region.member_pick_ids ?? [])
      .map((id) => lookupService.pickById(id, allPicks))
      .filter((p): p is NonNullable<typeof p> => p !== null)
  );

  function endpointLabel(nodeId: string, nodeKind: 'pick' | 'region'): string {
    if (nodeKind === 'pick') {
      return lookupService.pickById(nodeId, allPicks)?.element.selector ?? '(missing)';
    }
    const r = lookupService.regionById(nodeId, allRegions);
    return r?.note?.trim() ? r.note : `region:${nodeId.slice(0, 6)}`;
  }

  function selectEndpoint(nodeId: string, nodeKind: 'pick' | 'region'): void {
    if (nodeKind === 'pick') backendState.inspector.selectPick(nodeId);
    else backendState.inspector.selectRegion(nodeId);
  }

  function deleteRelation(relationId: string, e: MouseEvent): void {
    e.stopPropagation();
    backendState.inspector.deleteRelation(relationId);
  }

  const timestampFormatted = $derived(
    new Date(region.timestamp_ms).toLocaleString(undefined, {
      year: 'numeric',
      month: '2-digit',
      day: '2-digit',
      hour: '2-digit',
      minute: '2-digit',
      second: '2-digit',
    })
  );

  // Schema 0.6.0+: region.rect ist in page-absoluten Koordinaten (scrollX+clientX).
  // Direkt usable für screenshot-extraction via page.screenshot({clip}).
  const rectStr = $derived(
    `${Math.round(region.rect.x)}, ${Math.round(region.rect.y)} · ${Math.round(region.rect.width)} × ${Math.round(region.rect.height)} (page-abs)`
  );

  const displayName = $derived(
    region.note?.trim() ? region.note : `region:${region.region_id.slice(0, 6)}`
  );
</script>

<dl class="details">
  <dt>name</dt>
  <dd><code>{displayName}</code></dd>

  <dt>rect</dt>
  <dd><code>{rectStr}</code></dd>

  <dt>members</dt>
  <dd><code>{members.length}</code></dd>

  <dt>created</dt>
  <dd><code>{timestampFormatted}</code></dd>
</dl>

{#if members.length > 0}
  <div class="members-section">
    <h4 class="members-section__title">Member picks</h4>
    {#each members as pick (pick.pick_id)}
      <button
        type="button"
        class="member-row"
        onclick={() => backendState.inspector.selectPick(pick.pick_id)}
        title={pick.element.selector}
      >
        <span class="member-row__icon" aria-hidden="true">⊙</span>
        <span class="member-row__selector">{pick.element.selector}</span>
      </button>
    {/each}
  </div>
{/if}

{#if relationsView.outgoing.length > 0 || relationsView.incoming.length > 0}
  <div class="relations-section">
    <h4 class="relations-section__title">Relations</h4>

    {#if relationsView.outgoing.length > 0}
      <div class="relations-section__group">
        <div class="relations-section__group-label">outgoing</div>
        {#each relationsView.outgoing as rel (rel.relation_id)}
          {@const arrow = rel.kind === 'relates_to' ? '↔' : '→'}
          <button
            type="button"
            class="rel-row kind-{rel.kind}"
            class:rel-row--hovered={uiPrefs.hoveredRelationId === rel.relation_id}
            onmouseenter={() => uiPrefs.hoverRelation(rel.relation_id)}
            onmouseleave={() => uiPrefs.hoverRelation(null)}
            onclick={() => selectEndpoint(rel.target_id, rel.target_kind)}
            title={rel.note ?? rel.kind}
          >
            <span class="rel-row__arrow">{arrow}</span>
            <span class="rel-row__kind">{rel.kind}</span>
            <span class="rel-row__arrow">{arrow}</span>
            <span class="rel-row__node">{endpointLabel(rel.target_id, rel.target_kind)}</span>
            {#if rel.note}
              <span class="rel-row__note">· {rel.note}</span>
            {/if}
            <span
              class="rel-row__delete"
              role="button"
              tabindex="0"
              aria-label="Delete relation"
              onclick={(e) => deleteRelation(rel.relation_id, e)}
              onkeydown={(e) =>
                e.key === 'Enter' && deleteRelation(rel.relation_id, e as unknown as MouseEvent)}
              >×</span
            >
          </button>
        {/each}
      </div>
    {/if}

    {#if relationsView.incoming.length > 0}
      <div class="relations-section__group">
        <div class="relations-section__group-label">incoming</div>
        {#each relationsView.incoming as rel (rel.relation_id)}
          {@const arrow = rel.kind === 'relates_to' ? '↔' : '←'}
          <button
            type="button"
            class="rel-row kind-{rel.kind}"
            class:rel-row--hovered={uiPrefs.hoveredRelationId === rel.relation_id}
            onmouseenter={() => uiPrefs.hoverRelation(rel.relation_id)}
            onmouseleave={() => uiPrefs.hoverRelation(null)}
            onclick={() => selectEndpoint(rel.source_id, rel.source_kind)}
            title={rel.note ?? rel.kind}
          >
            <span class="rel-row__arrow">{arrow}</span>
            <span class="rel-row__kind">{rel.kind}</span>
            <span class="rel-row__arrow">{arrow}</span>
            <span class="rel-row__node">{endpointLabel(rel.source_id, rel.source_kind)}</span>
            {#if rel.note}
              <span class="rel-row__note">· {rel.note}</span>
            {/if}
            <span
              class="rel-row__delete"
              role="button"
              tabindex="0"
              aria-label="Delete relation"
              onclick={(e) => deleteRelation(rel.relation_id, e)}
              onkeydown={(e) =>
                e.key === 'Enter' && deleteRelation(rel.relation_id, e as unknown as MouseEvent)}
              >×</span
            >
          </button>
        {/each}
      </div>
    {/if}
  </div>
{/if}

<style>
  .details {
    display: grid;
    grid-template-columns: 70px 1fr;
    gap: 4px 12px;
    padding: 12px 14px;
    margin: 0;
    font-size: 11px;
  }

  dt {
    color: var(--fp-color-text-muted);
    text-transform: lowercase;
    font-family: 'SF Mono', 'JetBrains Mono', Menlo, Consolas, monospace;
  }

  dd {
    margin: 0;
    color: var(--fp-color-text-primary);
    word-break: break-word;
  }

  code {
    font-family: 'SF Mono', 'JetBrains Mono', Menlo, Consolas, monospace;
    font-size: 11px;
  }

  .members-section,
  .relations-section {
    padding: 8px 14px;
    border-top: 1px solid var(--fp-color-border-subtle);
  }

  .members-section__title,
  .relations-section__title {
    margin: 0 0 6px 0;
    font-size: 10px;
    text-transform: uppercase;
    letter-spacing: 0.05em;
    color: var(--fp-color-text-muted);
    font-weight: 500;
  }

  .member-row {
    display: flex;
    align-items: center;
    gap: 6px;
    width: 100%;
    background: transparent;
    border: 1px solid transparent;
    border-radius: 2px;
    color: var(--fp-color-text-primary);
    font: inherit;
    font-size: 11px;
    padding: 3px 6px;
    cursor: pointer;
    text-align: left;
    margin-bottom: 2px;
    transition:
      background 120ms ease,
      border-color 120ms ease;
  }

  .member-row:hover {
    background: var(--fp-color-surface-secondary);
    border-color: rgba(120, 180, 255, 0.3);
  }

  .member-row__icon {
    color: rgba(120, 220, 255, 0.7);
    flex-shrink: 0;
  }

  .member-row__selector {
    font-family: 'SF Mono', 'JetBrains Mono', Menlo, Consolas, monospace;
    text-overflow: ellipsis;
    overflow: hidden;
    white-space: nowrap;
    min-width: 0;
  }

  .relations-section__group {
    margin-bottom: 8px;
  }

  .relations-section__group-label {
    font-size: 9px;
    text-transform: uppercase;
    letter-spacing: 0.05em;
    color: var(--fp-color-text-muted);
    margin-bottom: 3px;
  }

  .rel-row {
    display: flex;
    align-items: center;
    gap: 5px;
    width: 100%;
    background: transparent;
    border: 1px solid transparent;
    border-radius: 2px;
    color: var(--fp-color-text-primary);
    font: inherit;
    font-size: 11px;
    padding: 3px 6px;
    cursor: pointer;
    text-align: left;
    margin-bottom: 2px;
    transition:
      background 120ms ease,
      border-color 120ms ease;
  }

  .rel-row:hover,
  .rel-row--hovered {
    background: var(--fp-color-surface-secondary);
    border-color: rgba(120, 180, 255, 0.3);
  }

  .rel-row__arrow {
    color: var(--fp-color-text-muted);
    flex-shrink: 0;
  }

  .rel-row__kind {
    font-size: 9px;
    padding: 1px 5px;
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

  .rel-row__node {
    font-family: 'SF Mono', 'JetBrains Mono', Menlo, Consolas, monospace;
    text-overflow: ellipsis;
    overflow: hidden;
    white-space: nowrap;
    min-width: 0;
    flex: 1 1 auto;
  }

  .rel-row__note {
    color: var(--fp-color-text-secondary);
    font-style: italic;
    font-size: 10px;
    text-overflow: ellipsis;
    overflow: hidden;
    white-space: nowrap;
    flex-shrink: 1;
  }

  .rel-row__delete {
    color: var(--fp-color-text-secondary);
    cursor: pointer;
    padding: 0 4px;
    flex-shrink: 0;
    transition: color 120ms ease;
  }

  .rel-row__delete:hover {
    color: rgba(255, 140, 140, 0.95);
  }
</style>
