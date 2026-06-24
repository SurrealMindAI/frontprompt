<!--
  NodePicker — unified endpoint picker for Relations.

  Replaces the two PickPicker instances in RelationsTab, enabling the user to
  select either a Pick OR a Region as an endpoint in a relation draft.

  Two selection paths:
    1. Dropdown: shows all picks + all regions grouped by kind. Selecting an
       entry calls onChange with the corresponding EndpointRef.
    2. Pick-Button (pick mode only): ad-hoc DOM-pick flow via pickClaim —
       identical to PickPicker's claim coordination. Hidden when a region
       endpoint is already selected.

  Props (NodePickerProps contract — see overview.md#nodepickerprops):
    - value: EndpointRef | null  — currently selected endpoint
    - onChange: (ref: EndpointRef | null) => void
    - excludeRef?: EndpointRef | null  — option to hide (prevents self-loop)
    - label?: string
    - claimId?: string  — stable id for pick-claim coordination

  Serialisation: EndpointRef is serialized as JSON string for the Dropdown
  (which works with string values). Deserialized on selection.
-->
<script lang="ts">
  import { backendState } from '../../backend-state/backend-state.svelte';
  import { pickClaim } from '../../local-state/pick-claim.svelte';
  import type { Pick } from '../../_generated/state';
  import Dropdown, { type DropdownOption } from './Dropdown.svelte';
  import PickButton from './PickButton.svelte';
  import type { EndpointRef } from '../../services/relations/relation-draft.svelte';

  let {
    value,
    onChange,
    excludeRef = null,
    label,
    claimId,
  }: {
    /** Currently selected endpoint, or null. */
    value: EndpointRef | null;
    /** Called with new endpoint ref (or null when cleared). */
    onChange: (ref: EndpointRef | null) => void;
    /** Optional endpoint to exclude from dropdown (prevents self-loop). */
    excludeRef?: EndpointRef | null;
    label?: string;
    /**
     * Stable id for the global pick-claim. Must be unique per NodePicker
     * instance (e.g. "node-picker:source" / "node-picker:target"). Defaults
     * to a label-derived value.
     */
    claimId?: string;
  } = $props();

  const picks = $derived(backendState.inspector.picks);
  const regions = $derived(backendState.inspector.regions);

  const myClaimId = $derived(claimId ?? `node-picker:${label ?? 'unnamed'}`);
  const isActive = $derived(pickClaim.isClaimedBy(myClaimId));
  const isDisabled = $derived(pickClaim.current !== null && !isActive);

  /** Build dropdown options: picks first, then regions, filtered by excludeRef. */
  const options = $derived<DropdownOption<string>[]>([
    ...picks
      .filter((p) => {
        if (!excludeRef) return true;
        return !(excludeRef.id === p.pick_id && excludeRef.kind === 'pick');
      })
      .map((p) => ({
        value: JSON.stringify({ id: p.pick_id, kind: 'pick' }),
        label: `pick · ${p.element.fingerprint.tag} · ${p.element.selector}`,
      })),
    ...regions
      .filter((r) => {
        if (!excludeRef) return true;
        return !(excludeRef.id === r.region_id && excludeRef.kind === 'region');
      })
      .map((r) => ({
        value: JSON.stringify({ id: r.region_id, kind: 'region' }),
        label: `region · ${r.note?.trim() || 'region:' + r.region_id.slice(0, 6)}`,
      })),
  ]);

  /** Resolved pick for the selected value, if kind is 'pick'. */
  const selectedPick = $derived(
    value?.kind === 'pick' ? (picks.find((p) => p.pick_id === value.id) ?? null) : null
  );

  /** Resolved region for the selected value, if kind is 'region'. */
  const selectedRegion = $derived(
    value?.kind === 'region' ? (regions.find((r) => r.region_id === value.id) ?? null) : null
  );

  /** Label for the selected region chip. */
  const regionChipLabel = $derived(
    selectedRegion
      ? selectedRegion.note?.trim() || `region:${selectedRegion.region_id.slice(0, 6)}`
      : ''
  );

  /** Only show PickButton when kind is pick or nothing is selected yet. */
  const showPickButton = $derived(value === null || value.kind === 'pick');

  function selectFromDropdown(rawValue: string): void {
    if (!rawValue) return;
    try {
      const ref = JSON.parse(rawValue) as EndpointRef;
      onChange(ref);
    } catch {
      // malformed JSON — ignore
    }
  }

  function clear(): void {
    onChange(null);
    if (isActive) pickClaim.release();
  }

  function onPickFromInspector(pick: Pick): void {
    const resolvedPickId = backendState.inspector.submitPick(pick);
    onChange({ id: resolvedPickId, kind: 'pick' });
  }

  function startPick(): void {
    if (isActive) {
      pickClaim.release();
      return;
    }
    pickClaim.acquire({
      id: myClaimId,
      onPick: onPickFromInspector,
    });
  }
</script>

<div class="node-picker">
  {#if label}
    <span class="node-picker__label">{label}</span>
  {/if}
  <div class="node-picker__controls">
    {#if selectedPick}
      <!-- Pick chip -->
      <div class="node-picker__chip node-picker__chip--pick" title={selectedPick.element.selector}>
        <span class="node-picker__chip-kind">pick</span>
        <span class="node-picker__chip-tag">{selectedPick.element.fingerprint.tag}</span>
        <span class="node-picker__chip-selector">{selectedPick.element.selector}</span>
        <button type="button" class="node-picker__chip-clear" onclick={clear} aria-label="clear">
          ×
        </button>
      </div>
    {:else if selectedRegion}
      <!-- Region chip -->
      <div class="node-picker__chip node-picker__chip--region" title={regionChipLabel}>
        <span class="node-picker__chip-kind">region</span>
        <span class="node-picker__chip-label">{regionChipLabel}</span>
        <button type="button" class="node-picker__chip-clear" onclick={clear} aria-label="clear">
          ×
        </button>
      </div>
    {:else if options.length === 0}
      <span class="node-picker__empty">No picks or regions yet</span>
    {:else}
      <Dropdown
        {options}
        value={''}
        onChange={(v) => v && selectFromDropdown(v)}
        placeholder="Search picks & regions…"
        ariaLabel={label ?? 'select endpoint'}
      />
    {/if}
    {#if showPickButton}
      <PickButton
        variant="icon"
        active={isActive}
        disabled={isDisabled}
        onclick={startPick}
        title={isActive
          ? 'Pick aktiv — click ein element auf der page'
          : 'Element auf der page picken'}
        ariaLabel="pick element on page"
      />
    {/if}
  </div>
</div>

<style>
  .node-picker {
    display: flex;
    flex-direction: column;
    gap: 4px;
    min-width: 0;
  }

  .node-picker__label {
    font-size: 9px;
    text-transform: uppercase;
    color: var(--fp-color-text-muted);
    letter-spacing: 0.06em;
  }

  .node-picker__controls {
    display: flex;
    align-items: stretch;
    gap: 4px;
    min-width: 0;
  }

  .node-picker__chip {
    display: flex;
    align-items: center;
    gap: 4px;
    flex: 1 1 auto;
    min-width: 0;
    padding: 4px 6px;
    border-radius: 3px;
  }

  .node-picker__chip--pick {
    background: rgba(120, 180, 255, 0.12);
    border: 1px solid rgba(120, 220, 255, 0.4);
  }

  .node-picker__chip--region {
    background: rgba(157, 255, 177, 0.08);
    border: 1px solid rgba(157, 255, 177, 0.35);
  }

  .node-picker__chip-kind {
    font-family: 'SF Mono', 'JetBrains Mono', Menlo, Consolas, monospace;
    font-size: 8px;
    text-transform: uppercase;
    padding: 1px 4px;
    border-radius: 2px;
    flex-shrink: 0;
    letter-spacing: 0.05em;
  }

  .node-picker__chip--pick .node-picker__chip-kind {
    background: rgba(120, 180, 255, 0.18);
    color: var(--fp-color-text-primary);
  }

  .node-picker__chip--region .node-picker__chip-kind {
    background: rgba(157, 255, 177, 0.14);
    color: var(--fp-color-text-primary);
  }

  .node-picker__chip-tag {
    font-family: 'SF Mono', 'JetBrains Mono', Menlo, Consolas, monospace;
    font-size: 9px;
    text-transform: uppercase;
    background: rgba(120, 180, 255, 0.14);
    color: var(--fp-color-text-primary);
    padding: 1px 3px;
    border-radius: 2px;
    flex-shrink: 0;
  }

  .node-picker__chip-selector,
  .node-picker__chip-label {
    font-family: 'SF Mono', 'JetBrains Mono', Menlo, Consolas, monospace;
    font-size: 10px;
    color: var(--fp-color-text-primary);
    overflow: hidden;
    text-overflow: ellipsis;
    white-space: nowrap;
    flex: 1 1 auto;
    min-width: 0;
  }

  .node-picker__chip-clear {
    background: transparent;
    border: none;
    color: var(--fp-color-text-secondary);
    font-size: 13px;
    cursor: pointer;
    padding: 0 4px;
    line-height: 1;
    flex-shrink: 0;
  }

  .node-picker__chip-clear:hover {
    color: rgba(255, 140, 140, 0.95);
  }

  .node-picker__empty {
    flex: 1 1 auto;
    padding: 5px 8px;
    font-size: 10px;
    font-style: italic;
    color: var(--fp-color-text-muted);
    border: 1px dashed rgba(120, 180, 255, 0.2);
    border-radius: 3px;
  }
</style>
