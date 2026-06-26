<!--
  RecordingDetails — inline name/description edit for the active detail recording.

  Follows the CommentEditor.svelte dirty-bit + Save/Cancel pattern.
  Edit draft is localState $state (ADR-018: in-flight edit is ephemeral).
  Calls backendState.recordings.renameRecording() on Save.

  started_at and ended_at are read-only metadata. When recording is still active
  (ended_at_ms is null), ended_at shows "recording…".

  Also renders:
  - Assertion entries from recording.entries (with delete button)
  - "Add assertion" toggle (localState) → AssertionEditor
  - Parameter declarations list (read-only)
-->

<script lang="ts">
  import { untrack } from 'svelte';
  import { backendState } from '../../backend-state/backend-state.svelte';
  import { bridge } from '../../bridge/bridge.svelte';
  import type { AssertionDeletedRequested } from '../../_generated/schemas';
  import type { AssertionEntry, ParameterDeclaration, Recording } from '../../_generated/state';
  import AssertionEditor from './AssertionEditor.svelte';

  let { recording }: { recording: Recording } = $props();

  // localState: toggle AssertionEditor panel (ADR-018: ephemeral UI state)
  let showAssertionEditor = $state(false);

  // localState edit draft (ADR-018: ephemeral in-flight edit, not backendState)
  let nameValue = $state(untrack(() => recording.name));
  let descValue = $state(untrack(() => recording.description ?? ''));

  // Baseline tracks last saved/confirmed values for dirty detection and Cancel revert.
  let nameBaseline = $state(untrack(() => recording.name));
  let descBaseline = $state(untrack(() => recording.description ?? ''));

  const dirty = $derived(nameValue !== nameBaseline || descValue !== descBaseline);

  // Derived: assertion entries from the recording's timeline (PIT-037: inline, no local $state copy)
  const assertionEntries = $derived(
    (recording.entries ?? []).filter(
      (e): e is AssertionEntry => (e as AssertionEntry).kind === 'assertion'
    )
  );

  // Derived: parameter declarations (read-only display)
  const parameters = $derived<ParameterDeclaration[]>(recording.parameters ?? []);

  const SCHEMA_VERSION = '0.9.0';

  function deleteAssertion(assertionId: string): void {
    const message: AssertionDeletedRequested = {
      kind: 'assertion_deleted_requested',
      schema_version: SCHEMA_VERSION,
      recording_id: recording.recording_id,
      assertion_id: assertionId,
    };
    void bridge.send(message);
  }

  function toggleAssertionEditor(): void {
    showAssertionEditor = !showAssertionEditor;
  }

  // Re-sync when a different recording is selected (recording prop changes).
  $effect(() => {
    // Track recording_id so effect fires when the user selects a different recording.
    void recording.recording_id;
    nameValue = recording.name;
    descValue = recording.description ?? '';
    nameBaseline = recording.name;
    descBaseline = recording.description ?? '';
    // Reset the assertion editor toggle on recording change
    showAssertionEditor = false;
  });

  function save(): void {
    if (!dirty) return;
    backendState.recordings.renameRecording(recording.recording_id, nameValue, descValue);
    nameBaseline = nameValue;
    descBaseline = descValue;
  }

  function cancel(): void {
    nameValue = nameBaseline;
    descValue = descBaseline;
  }

  const startedAtFormatted = $derived(
    new Date(recording.started_at_ms).toLocaleString(undefined, {
      year: 'numeric',
      month: '2-digit',
      day: '2-digit',
      hour: '2-digit',
      minute: '2-digit',
    })
  );

  const endedAtFormatted = $derived(
    recording.ended_at_ms != null
      ? new Date(recording.ended_at_ms).toLocaleString(undefined, {
          year: 'numeric',
          month: '2-digit',
          day: '2-digit',
          hour: '2-digit',
          minute: '2-digit',
        })
      : 'recording…'
  );
</script>

<div class="recording-details">
  <dl class="meta">
    <dt>started</dt>
    <dd class="details-started-at">{startedAtFormatted}</dd>
    <dt>ended</dt>
    <dd class="details-ended-at">{endedAtFormatted}</dd>
    <dt>status</dt>
    <dd><span class="status-badge status-badge--{recording.status}">{recording.status}</span></dd>
  </dl>

  <div class="editor">
    <label class="editor__label" for="recording-name">name</label>
    <input
      id="recording-name"
      class="details-name editor__input"
      type="text"
      bind:value={nameValue}
      placeholder="Recording name"
    />

    <label class="editor__label" for="recording-description">description</label>
    <textarea
      id="recording-description"
      class="details-description editor__textarea"
      bind:value={descValue}
      placeholder="Optional description…"
      rows="4"
    ></textarea>

    <div class="editor__actions">
      <button
        type="button"
        class="details-save editor__save"
        class:editor__save--dirty={dirty}
        onclick={save}
        disabled={!dirty}
      >
        {dirty ? 'Save *' : 'Saved'}
      </button>
      <button
        type="button"
        class="details-cancel editor__cancel"
        onclick={cancel}
        disabled={!dirty}
      >
        Cancel
      </button>
    </div>
  </div>

  <!-- ── Assertions section ── -->
  <div class="assertions-section">
    <div class="section-header">
      <span class="section-label">assertions</span>
      <button
        type="button"
        class="details-add-assertion section-header__btn"
        onclick={toggleAssertionEditor}
      >
        {showAssertionEditor ? '− hide' : '+ add'}
      </button>
    </div>

    {#if assertionEntries.length > 0}
      <ul class="assertion-list">
        {#each assertionEntries as entry (entry.assertion_id)}
          <li class="assertion-row">
            <span class="assertion-chip">{entry.assertion_type}</span>
            <span class="assertion-target-label">{entry.target}</span>
            <button
              type="button"
              class="assertion-delete assertion-row__delete"
              title="Delete assertion"
              onclick={() => deleteAssertion(entry.assertion_id)}
            >
              ×
            </button>
          </li>
        {/each}
      </ul>
    {/if}

    {#if showAssertionEditor}
      <AssertionEditor recording_id={recording.recording_id} />
    {/if}
  </div>

  <!-- ── Parameters section ── -->
  {#if parameters.length > 0}
    <div class="parameters-section">
      <div class="section-header">
        <span class="section-label">parameters</span>
      </div>
      <ul class="parameter-list">
        {#each parameters as param (param.name)}
          <li class="parameter-row">
            <span class="parameter-name">{param.name}</span>
            <span class="parameter-type">{param.param_type}</span>
            {#if param.default_value != null}
              <span class="parameter-default">{param.default_value}</span>
            {/if}
          </li>
        {/each}
      </ul>
    </div>
  {:else}
    <!-- Empty parameter-list for test selector compatibility -->
    <ul class="parameter-list" style="display:none"></ul>
  {/if}
</div>

<style>
  .recording-details {
    display: flex;
    flex-direction: column;
    gap: 0;
  }

  /* ---- Metadata section ---- */

  .meta {
    display: grid;
    grid-template-columns: max-content 1fr;
    column-gap: 12px;
    row-gap: 5px;
    margin: 0;
    padding: 10px 14px 8px;
    font-size: 11px;
    border-bottom: 1px solid var(--fp-color-border-subtle);
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
    color: var(--fp-color-text-primary);
    font-size: 11px;
    font-family: 'SF Mono', 'JetBrains Mono', Menlo, Consolas, monospace;
  }

  .status-badge {
    font-size: 9px;
    padding: 1px 6px;
    border-radius: 7px;
    text-transform: lowercase;
  }

  .status-badge--active {
    background: rgba(255, 80, 80, 0.15);
    color: rgba(255, 120, 120, 0.9);
  }

  .status-badge--stopped {
    background: rgba(100, 180, 100, 0.15);
    color: rgba(120, 200, 120, 0.9);
  }

  /* ---- Editor section ---- */

  .editor {
    display: flex;
    flex-direction: column;
    gap: 6px;
    padding: 10px 14px;
  }

  .editor__label {
    font-size: 10px;
    text-transform: uppercase;
    letter-spacing: 0.05em;
    color: var(--fp-color-text-muted);
    margin-top: 4px;
  }

  .editor__label:first-of-type {
    margin-top: 0;
  }

  .editor__input,
  .editor__textarea {
    background: var(--fp-color-surface-secondary);
    border: 1px solid var(--fp-color-border);
    border-radius: 4px;
    color: var(--fp-color-text-primary);
    font: inherit;
    font-size: 12px;
    line-height: 1.45;
    padding: 6px 8px;
    transition:
      border-color 120ms ease,
      background 120ms ease;
  }

  .editor__input:focus,
  .editor__textarea:focus {
    outline: none;
    border-color: rgba(120, 180, 255, 0.5);
  }

  .editor__textarea {
    resize: vertical;
    min-height: 60px;
  }

  .editor__actions {
    display: flex;
    flex-direction: row;
    gap: 8px;
    justify-content: flex-end;
    margin-top: 2px;
  }

  .editor__save,
  .editor__cancel {
    background: var(--fp-color-surface-secondary);
    border: 1px solid var(--fp-color-border);
    color: var(--fp-color-text-primary);
    font: inherit;
    font-size: 11px;
    padding: 4px 12px;
    border-radius: 4px;
    cursor: pointer;
    transition:
      background 120ms ease,
      border-color 120ms ease,
      color 120ms ease;
  }

  .editor__save:disabled,
  .editor__cancel:disabled {
    opacity: 0.4;
    cursor: not-allowed;
  }

  .editor__save:not(:disabled):hover,
  .editor__cancel:not(:disabled):hover {
    border-color: rgba(120, 180, 255, 0.5);
  }

  .editor__save--dirty {
    background: rgba(120, 180, 255, 0.18);
    border-color: rgba(120, 220, 255, 0.85);
  }

  /* ---- Shared section header ---- */

  .section-header {
    display: flex;
    align-items: center;
    justify-content: space-between;
    padding: 6px 14px 4px;
    border-top: 1px solid var(--fp-color-border-subtle);
  }

  .section-label {
    font-size: 10px;
    text-transform: uppercase;
    letter-spacing: 0.05em;
    color: var(--fp-color-text-muted);
  }

  .section-header__btn {
    background: transparent;
    border: 1px solid var(--fp-color-border);
    color: var(--fp-color-text-secondary);
    font: inherit;
    font-size: 10px;
    padding: 2px 8px;
    border-radius: 3px;
    cursor: pointer;
    transition: background 120ms ease, color 120ms ease;
  }

  .section-header__btn:hover {
    background: var(--fp-color-surface-secondary);
    color: var(--fp-color-text-primary);
  }

  /* ---- Assertions section ---- */

  .assertions-section {
    display: flex;
    flex-direction: column;
  }

  .assertion-list {
    list-style: none;
    margin: 0;
    padding: 0 14px 6px;
  }

  .assertion-row {
    display: flex;
    align-items: center;
    gap: 6px;
    padding: 3px 0;
    font-size: 11px;
  }

  .assertion-chip {
    font-size: 9px;
    padding: 1px 5px;
    border-radius: 7px;
    background: rgba(157, 255, 177, 0.18);
    color: var(--fp-color-text-primary);
    font-family: 'SF Mono', 'JetBrains Mono', Menlo, Consolas, monospace;
    flex-shrink: 0;
  }

  .assertion-target-label {
    flex: 1 1 auto;
    min-width: 0;
    overflow: hidden;
    text-overflow: ellipsis;
    white-space: nowrap;
    font-size: 10px;
    font-family: 'SF Mono', 'JetBrains Mono', Menlo, Consolas, monospace;
    color: var(--fp-color-text-secondary);
  }

  .assertion-row__delete {
    background: transparent;
    border: none;
    color: var(--fp-color-text-muted);
    font: inherit;
    font-size: 13px;
    cursor: pointer;
    padding: 0 2px;
    line-height: 1;
    flex-shrink: 0;
    transition: color 120ms ease;
  }

  .assertion-row__delete:hover {
    color: rgba(255, 100, 100, 0.9);
  }

  /* ---- Parameters section ---- */

  .parameters-section {
    display: flex;
    flex-direction: column;
  }

  .parameter-list {
    list-style: none;
    margin: 0;
    padding: 0 14px 6px;
  }

  .parameter-row {
    display: flex;
    align-items: center;
    gap: 6px;
    padding: 3px 0;
    font-size: 11px;
  }

  .parameter-name {
    font-family: 'SF Mono', 'JetBrains Mono', Menlo, Consolas, monospace;
    font-size: 10px;
    color: var(--fp-color-text-primary);
  }

  .parameter-type {
    font-size: 9px;
    padding: 1px 5px;
    border-radius: 7px;
    background: rgba(180, 120, 255, 0.18);
    color: var(--fp-color-text-primary);
    font-family: 'SF Mono', 'JetBrains Mono', Menlo, Consolas, monospace;
  }

  .parameter-default {
    font-size: 10px;
    color: var(--fp-color-text-muted);
    font-family: 'SF Mono', 'JetBrains Mono', Menlo, Consolas, monospace;
  }
</style>
