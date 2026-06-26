<!--
  RecordingDetails — inline name/description edit for the active detail recording.

  Follows the CommentEditor.svelte dirty-bit + Save/Cancel pattern.
  Edit draft is localState $state (ADR-018: in-flight edit is ephemeral).
  Calls backendState.recordings.renameRecording() on Save.

  started_at and ended_at are read-only metadata. When recording is still active
  (ended_at_ms is null), ended_at shows "recording…".
-->

<script lang="ts">
  import { untrack } from 'svelte';
  import { backendState } from '../../backend-state/backend-state.svelte';
  import type { Recording } from '../../_generated/state';

  let { recording }: { recording: Recording } = $props();

  // localState edit draft (ADR-018: ephemeral in-flight edit, not backendState)
  let nameValue = $state(untrack(() => recording.name));
  let descValue = $state(untrack(() => recording.description ?? ''));

  // Baseline tracks last saved/confirmed values for dirty detection and Cancel revert.
  let nameBaseline = $state(untrack(() => recording.name));
  let descBaseline = $state(untrack(() => recording.description ?? ''));

  const dirty = $derived(nameValue !== nameBaseline || descValue !== descBaseline);

  // Re-sync when a different recording is selected (recording prop changes).
  $effect(() => {
    // Track recording_id so effect fires when the user selects a different recording.
    void recording.recording_id;
    nameValue = recording.name;
    descValue = recording.description ?? '';
    nameBaseline = recording.name;
    descBaseline = recording.description ?? '';
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
</style>
