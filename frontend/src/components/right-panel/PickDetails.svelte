<!--
  PickDetails — read-only Element-Details des aktiven Picks.

  Tag, classes, id, selector, url, timestamp, text-snippet — plus collapsible
  Scrapling-fingerprint-Ansicht (path, parent_*, siblings, children) für die
  Adaptive-Relocate-Datenbasis (Phase 2).
-->

<script lang="ts">
  import { backendState } from '../../backend-state/backend-state.svelte';
  import { uiPrefs } from '../../local-state/ui-prefs.svelte';
  import { lookupService } from '../../services/relations';
  import type { Pick } from '../../_generated/state';

  let { pick }: { pick: Pick } = $props();

  // Relations involving this pick — derived via lookup-service (Pick selber
  // trägt KEINE relations-felder; saubere Trennung Pick ↔ Relations).
  // Schema 0.4.0: explizit nodeKind="pick" — Relations können auch Region-
  // endpoints haben, hier interessieren uns nur die mit pick-side für diesen pick_id.
  const relationsView = $derived(
    lookupService.relationsFor(pick.pick_id, 'pick', backendState.inspector.relations)
  );
  const allPicks = $derived(backendState.inspector.picks);
  const allRegions = $derived(backendState.inspector.regions);

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

  const tag = $derived(pick.element.fingerprint.tag);
  const attributes = $derived(pick.element.fingerprint.attributes ?? {});
  const classes = $derived((attributes['class'] ?? '').trim() || null);
  const elementId = $derived(attributes['id'] ?? null);
  const selector = $derived(pick.element.selector);
  const url = $derived(pick.url);
  const textSnippet = $derived(pick.element.text_snippet ?? '');

  // Fingerprint-fields (Scrapling-format) für die "fingerprint"-section
  const fingerprint = $derived(pick.element.fingerprint);
  const path = $derived(fingerprint.path ?? []);
  const parentName = $derived(fingerprint.parent_name);
  const parentAttribs = $derived(fingerprint.parent_attribs ?? {});
  const parentText = $derived(fingerprint.parent_text ?? '');
  const siblings = $derived(fingerprint.siblings ?? []);
  const children = $derived(fingerprint.children ?? []);
  const fingerprintText = $derived(fingerprint.text ?? '');

  // Attribute-rows (key/value pairs außer id/class — die haben eigene rows oben)
  const otherAttribs = $derived(
    Object.entries(attributes).filter(([k]) => k !== 'id' && k !== 'class')
  );

  const timestampFormatted = $derived(
    new Date(pick.timestamp_ms).toLocaleString(undefined, {
      year: 'numeric',
      month: '2-digit',
      day: '2-digit',
      hour: '2-digit',
      minute: '2-digit',
      second: '2-digit',
    })
  );
</script>

<dl class="details">
  <dt>tag</dt>
  <dd><code>{tag}</code></dd>

  {#if elementId}
    <dt>id</dt>
    <dd><code>#{elementId}</code></dd>
  {/if}

  {#if classes}
    <dt>classes</dt>
    <dd><code>.{classes.split(/\s+/).join(' .')}</code></dd>
  {/if}

  <dt>selector</dt>
  <dd class="details__selector"><code>{selector}</code></dd>

  {#if textSnippet}
    <dt>text</dt>
    <dd class="details__text">{textSnippet}</dd>
  {/if}

  <dt>url</dt>
  <dd class="details__url" title={url}>{url}</dd>

  <dt>at</dt>
  <dd>{timestampFormatted}</dd>
</dl>

<details class="fingerprint">
  <summary>fingerprint <span class="fingerprint__hint">(scrapling-format)</span></summary>

  <dl class="details details--nested">
    <dt>path</dt>
    <dd class="fingerprint__path">
      {#if path.length > 0}
        <code>{path.join(' › ')}</code>
      {:else}
        <span class="fingerprint__empty">—</span>
      {/if}
    </dd>

    <dt>parent</dt>
    <dd>
      {#if parentName}
        <code>{parentName}</code>
        {#if parentAttribs['id']}<code class="fingerprint__attr">#{parentAttribs['id']}</code>{/if}
        {#if parentAttribs['class']}<code class="fingerprint__attr"
            >.{parentAttribs['class'].split(/\s+/).join(' .')}</code
          >{/if}
      {:else}
        <span class="fingerprint__empty">(orphan)</span>
      {/if}
    </dd>

    {#if parentText}
      <dt>parent.text</dt>
      <dd class="details__text">{parentText.slice(0, 200)}{parentText.length > 200 ? '…' : ''}</dd>
    {/if}

    <dt>siblings</dt>
    <dd>
      {#if siblings.length > 0}
        <code>{siblings.join(', ')}</code>
        <span class="fingerprint__count">({siblings.length})</span>
      {:else}
        <span class="fingerprint__empty">—</span>
      {/if}
    </dd>

    <dt>children</dt>
    <dd>
      {#if children.length > 0}
        <code>{children.join(', ')}</code>
        <span class="fingerprint__count">({children.length})</span>
      {:else}
        <span class="fingerprint__empty">—</span>
      {/if}
    </dd>

    {#if fingerprintText && fingerprintText !== textSnippet}
      <dt>full text</dt>
      <dd class="details__text">
        {fingerprintText.slice(0, 200)}{fingerprintText.length > 200 ? '…' : ''}
      </dd>
    {/if}

    {#if otherAttribs.length > 0}
      <dt>attrs</dt>
      <dd class="fingerprint__attrs">
        {#each otherAttribs as [k, v] (k)}
          <code class="fingerprint__attr"
            ><b>{k}</b>={v.length > 60 ? v.slice(0, 60) + '…' : v}</code
          >
        {/each}
      </dd>
    {/if}
  </dl>
</details>

<!--
  Relations-Section — derived display via lookup-service. Relations leben
  NICHT am Pick (siehe Design-Decision), die Section konsultiert
  die zentrale relations-liste. Hover-rows synchronisieren mit RelationsLayer-
  overlay via uiPrefs.hoveredRelationId.
-->
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
    grid-template-columns: max-content 1fr;
    column-gap: 12px;
    row-gap: 6px;
    margin: 0;
    padding: 10px 14px;
    font-size: 11px;
    color: var(--fp-color-text-primary);
  }

  dt {
    font-size: 10px;
    text-transform: uppercase;
    letter-spacing: 0.05em;
    color: var(--fp-color-text-muted);
    align-self: center;
  }

  dd {
    margin: 0;
    min-width: 0;
    overflow: hidden;
    text-overflow: ellipsis;
    word-break: break-all;
  }

  code {
    font-family: 'SF Mono', 'JetBrains Mono', Menlo, Consolas, monospace;
    font-size: 11px;
    background: var(--fp-color-surface-secondary);
    padding: 1px 4px;
    border-radius: 2px;
    color: var(--fp-color-text-primary);
  }

  .details__selector code {
    white-space: pre-wrap;
    display: inline-block;
    max-width: 100%;
    word-break: break-all;
  }

  .details__text {
    color: var(--fp-color-text-primary);
    font-style: italic;
  }

  .details__url {
    color: var(--fp-color-text-secondary);
    font-size: 10px;
    overflow: hidden;
    text-overflow: ellipsis;
    white-space: nowrap;
  }

  .fingerprint {
    margin: 6px 14px 14px 14px;
    padding: 8px 0 0 0;
    border-top: 1px solid var(--fp-color-border-subtle);
  }

  .fingerprint > summary {
    cursor: pointer;
    font-size: 10px;
    text-transform: uppercase;
    letter-spacing: 0.05em;
    color: var(--fp-color-text-muted);
    padding: 4px 0;
    user-select: none;
  }

  .fingerprint > summary:hover {
    color: var(--fp-color-text-primary);
  }

  .fingerprint__hint {
    color: var(--fp-color-text-muted);
    font-size: 9px;
    margin-left: 4px;
    text-transform: none;
    letter-spacing: 0;
  }

  .details--nested {
    padding: 6px 0 0 0;
    margin: 0;
  }

  .fingerprint__path {
    font-size: 10px;
    line-height: 1.6;
    word-break: break-all;
  }

  .fingerprint__path code {
    background: var(--fp-color-text-muted);
    color: var(--fp-color-text-primary);
  }

  .fingerprint__empty {
    color: var(--fp-color-text-muted);
    font-style: italic;
    font-size: 10px;
  }

  .fingerprint__count {
    color: var(--fp-color-text-muted);
    font-size: 9px;
    margin-left: 4px;
  }

  .fingerprint__attr {
    margin-right: 4px;
  }

  .fingerprint__attrs {
    display: flex;
    flex-wrap: wrap;
    gap: 4px;
  }

  .fingerprint__attrs code {
    font-size: 10px;
  }

  .fingerprint__attrs code b {
    color: var(--fp-color-text-secondary);
    font-weight: 500;
  }

  /* ---- Relations-section ---- */

  .relations-section {
    margin: 0 14px 14px 14px;
    padding: 8px 0 0 0;
    border-top: 1px solid var(--fp-color-border-subtle);
    display: flex;
    flex-direction: column;
    gap: 6px;
  }

  .relations-section__title {
    font-size: 10px;
    text-transform: uppercase;
    letter-spacing: 0.05em;
    color: var(--fp-color-text-muted);
    margin: 0 0 2px 0;
    font-weight: 500;
  }

  .relations-section__group {
    display: flex;
    flex-direction: column;
    gap: 3px;
  }

  .relations-section__group-label {
    font-size: 9px;
    text-transform: uppercase;
    letter-spacing: 0.05em;
    color: var(--fp-color-text-muted);
    margin-left: 2px;
  }

  .rel-row {
    display: flex;
    align-items: center;
    gap: 4px;
    padding: 4px 6px;
    border: none;
    background: var(--fp-color-surface-secondary);
    border-radius: 3px;
    cursor: pointer;
    font: inherit;
    text-align: left;
    transition: background 120ms ease;
    min-width: 0;
  }

  .rel-row:hover,
  .rel-row--hovered {
    background: rgba(120, 180, 255, 0.16);
  }

  .rel-row__arrow {
    color: var(--fp-color-text-muted);
    font-size: 11px;
    flex-shrink: 0;
  }

  .rel-row__kind {
    font-size: 9px;
    padding: 1px 5px;
    border-radius: 7px;
    font-family: 'SF Mono', 'JetBrains Mono', Menlo, Consolas, monospace;
    text-transform: lowercase;
    flex-shrink: 0;
  }

  .kind-relates_to .rel-row__kind {
    background: rgba(120, 220, 255, 0.18);
    color: var(--fp-color-text-primary);
  }

  .kind-triggers .rel-row__kind {
    background: rgba(255, 109, 209, 0.18);
    color: var(--fp-color-text-primary);
  }

  .kind-part_of .rel-row__kind {
    background: rgba(157, 255, 177, 0.18);
    color: var(--fp-color-text-primary);
  }

  .rel-row__node {
    font-family: 'SF Mono', 'JetBrains Mono', Menlo, Consolas, monospace;
    font-size: 10px;
    color: var(--fp-color-text-primary);
    overflow: hidden;
    text-overflow: ellipsis;
    white-space: nowrap;
    flex: 1 1 auto;
    min-width: 0;
  }

  .rel-row__note {
    color: var(--fp-color-text-muted);
    font-style: italic;
    font-size: 10px;
    overflow: hidden;
    text-overflow: ellipsis;
    white-space: nowrap;
  }

  .rel-row__delete {
    background: transparent;
    color: var(--fp-color-text-secondary);
    font-size: 13px;
    cursor: pointer;
    padding: 0 4px;
    line-height: 1;
    border-radius: 2px;
    flex-shrink: 0;
    transition:
      color 120ms ease,
      background 120ms ease;
    user-select: none;
  }

  .rel-row__delete:hover {
    color: rgba(255, 140, 140, 0.95);
    background: rgba(255, 80, 80, 0.12);
  }
</style>
