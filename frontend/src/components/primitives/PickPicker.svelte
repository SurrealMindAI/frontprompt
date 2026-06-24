<!--
  PickPicker — searchable Pick-Auswahl mit ad-hoc Pick-Button.

  Reusable primitive für jede UI die einen Pick als Input braucht
  (RelationsTab Source/Target, Phase 2 region-corners, etc).

  Zwei Eingabe-Pfade — DRY:
    1. **Dropdown** (Dropdown.svelte mit lowercase-contains-search): wähle aus
       der existierenden picks-Liste.
    2. **Pick-Button**: acquired den globalen pick-claim (siehe
       local-state/pick-claim.svelte.ts). App.svelte's InspectorLayer ist die
       EINZIGE mount-stelle — wir registrieren nur den callback. Vorteil:
       panels-retract läuft via ``backendState.inspector.active`` derived, OHNE
       hier extra zu mounten. Plus: nur EINER kann gleichzeitig picken.

  Output-Contract: ``value: string | null`` ist immer ein ``pick_id`` aus
  ``backendState.inspector.picks``. Pick-captured Pick wird ZUERST zur
  picks-Liste hinzugefügt (atomare backend-mutation, durchläuft Phase-1-
  fingerprint-dedupe in inspector-state.submitPick), DANN seine pick_id als
  unser value emittiert.
-->
<script lang="ts">
  import { backendState } from '../../backend-state/backend-state.svelte';
  import { pickClaim } from '../../local-state/pick-claim.svelte';
  import { lookupService } from '../../services/relations';
  import type { Pick } from '../../_generated/state';
  import Dropdown, { type DropdownOption } from './Dropdown.svelte';
  import PickButton from './PickButton.svelte';

  let {
    value,
    onChange,
    excludePickId = null,
    placeholder = 'Search picks…',
    label,
    claimId,
  }: {
    /** Currently selected pick_id, or null. */
    value: string | null;
    /** Called with new pick_id (or null when cleared). */
    onChange: (pickId: string | null) => void;
    /** Optional pick to hide from dropdown (e.g. the other endpoint to prevent self-loop). */
    excludePickId?: string | null;
    placeholder?: string;
    label?: string;
    /**
     * Stable id für den globalen pick-claim. MUSS pro PickPicker-instance
     * unique sein (z.B. "picker:source" / "picker:target"), sonst können wir
     * nicht erkennen welcher von zweien gerade claimt. Default = derived from label.
     */
    claimId?: string;
  } = $props();

  const picks = $derived(backendState.inspector.picks);
  const myClaimId = $derived(claimId ?? `picker:${label ?? 'unnamed'}`);
  const isActive = $derived(pickClaim.isClaimedBy(myClaimId));
  const isDisabled = $derived(pickClaim.current !== null && !isActive);

  const options = $derived<DropdownOption<string>[]>(
    picks
      .filter((p) => p.pick_id !== excludePickId)
      .map((p) => ({
        value: p.pick_id,
        label: `${p.element.fingerprint.tag} · ${p.element.selector}`,
      }))
  );

  const selected = $derived(value ? lookupService.pickById(value, picks) : null);

  function selectPick(pickId: string): void {
    onChange(pickId);
  }

  function clear(): void {
    onChange(null);
  }

  function onPickFromInspector(pick: Pick): void {
    // submitPick handles fingerprint-dedupe (returns existing pick_id if any
    // existing pick matches the fingerprint). For new picks, the returned
    // pick_id IS the one we asked for.
    const resolvedPickId = backendState.inspector.submitPick(pick);
    onChange(resolvedPickId);
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

<div class="pick-picker">
  {#if label}
    <span class="pick-picker__label">{label}</span>
  {/if}
  <div class="pick-picker__controls">
    {#if selected}
      <div class="pick-picker__chip" title={selected.element.selector}>
        <span class="pick-picker__chip-tag">{selected.element.fingerprint.tag}</span>
        <span class="pick-picker__chip-selector">{selected.element.selector}</span>
        <button type="button" class="pick-picker__chip-clear" onclick={clear} aria-label="clear">
          ×
        </button>
      </div>
    {:else if options.length === 0}
      <span class="pick-picker__empty">No picks yet — use Pick →</span>
    {:else}
      <Dropdown
        {options}
        value={''}
        onChange={(v) => v && selectPick(v)}
        {placeholder}
        ariaLabel={label ?? 'select pick'}
      />
    {/if}
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
  </div>
</div>

<style>
  .pick-picker {
    display: flex;
    flex-direction: column;
    gap: 4px;
    min-width: 0;
  }

  .pick-picker__label {
    font-size: 9px;
    text-transform: uppercase;
    color: var(--fp-color-text-muted);
    letter-spacing: 0.06em;
  }

  .pick-picker__controls {
    display: flex;
    align-items: stretch;
    gap: 4px;
    min-width: 0;
  }

  .pick-picker__chip {
    display: flex;
    align-items: center;
    gap: 4px;
    flex: 1 1 auto;
    min-width: 0;
    padding: 4px 6px;
    background: rgba(120, 180, 255, 0.12);
    border: 1px solid rgba(120, 220, 255, 0.4);
    border-radius: 3px;
  }

  .pick-picker__chip-tag {
    font-family: 'SF Mono', 'JetBrains Mono', Menlo, Consolas, monospace;
    font-size: 9px;
    text-transform: uppercase;
    background: rgba(120, 180, 255, 0.18);
    color: var(--fp-color-text-primary);
    padding: 1px 4px;
    border-radius: 2px;
    flex-shrink: 0;
  }

  .pick-picker__chip-selector {
    font-family: 'SF Mono', 'JetBrains Mono', Menlo, Consolas, monospace;
    font-size: 10px;
    color: var(--fp-color-text-primary);
    overflow: hidden;
    text-overflow: ellipsis;
    white-space: nowrap;
    flex: 1 1 auto;
    min-width: 0;
  }

  .pick-picker__chip-clear {
    background: transparent;
    border: none;
    color: var(--fp-color-text-secondary);
    font-size: 13px;
    cursor: pointer;
    padding: 0 4px;
    line-height: 1;
    flex-shrink: 0;
  }

  .pick-picker__chip-clear:hover {
    color: rgba(255, 140, 140, 0.95);
  }

  .pick-picker__empty {
    flex: 1 1 auto;
    padding: 5px 8px;
    font-size: 10px;
    font-style: italic;
    color: var(--fp-color-text-muted);
    border: 1px dashed rgba(120, 180, 255, 0.2);
    border-radius: 3px;
  }
</style>
