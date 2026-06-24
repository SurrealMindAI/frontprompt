<!--
  CommentEditor — multiline textarea + Save / Discard mit dirty-state.

  Wenn die activePickId von außen wechselt, der editor re-sync'd seinen
  internen wert via $effect.

  Auto-save NICHT angeschaltet (user-Wahl): explizit Save-button + dirty-marker.
-->

<script lang="ts">
  import { untrack } from 'svelte';
  import { backendState } from '../../backend-state/backend-state.svelte';

  let {
    pickId,
    initialComment,
  }: {
    pickId: string;
    initialComment: string;
  } = $props();

  // untrack(): initial-values aus props nur beim mount lesen. Re-sync bei
  // pickId-Wechsel passiert im $effect unten — kontrolliert + explizit.
  let editorValue = $state(untrack(() => initialComment));
  let baseline = $state(untrack(() => initialComment));

  const dirty = $derived(editorValue !== baseline);

  // Wenn der user einen anderen Pick auswählt, props ändern sich → re-sync.
  $effect(() => {
    // dependency-track auf initialComment + pickId damit der effect bei beiden
    // Änderungen feuert
    void pickId;
    editorValue = initialComment;
    baseline = initialComment;
  });

  function save(): void {
    if (!dirty) return;
    backendState.inspector.updateComment(pickId, editorValue);
    baseline = editorValue;
  }

  function discard(): void {
    editorValue = baseline;
  }
</script>

<div class="editor">
  <label class="editor__label" for="comment-textarea">notiz</label>
  <textarea
    id="comment-textarea"
    class="editor__textarea"
    bind:value={editorValue}
    placeholder="Was ist an diesem Element relevant?"
    rows="6"
  ></textarea>
  <div class="editor__actions">
    <button
      type="button"
      class="editor__save"
      class:editor__save--dirty={dirty}
      onclick={save}
      disabled={!dirty}
    >
      {dirty ? 'Speichern *' : 'Gespeichert'}
    </button>
    <button type="button" class="editor__discard" onclick={discard} disabled={!dirty}>
      Verwerfen
    </button>
  </div>
</div>

<style>
  .editor {
    display: flex;
    flex-direction: column;
    gap: 6px;
    padding: 10px 14px;
    border-top: 1px solid var(--fp-color-border-subtle);
  }

  .editor__label {
    font-size: 10px;
    text-transform: uppercase;
    letter-spacing: 0.05em;
    color: var(--fp-color-text-muted);
  }

  .editor__textarea {
    background: var(--fp-color-surface-secondary);
    border: 1px solid var(--fp-color-border);
    border-radius: 4px;
    color: var(--fp-color-text-primary);
    font: inherit;
    font-size: 12px;
    line-height: 1.45;
    padding: 8px 10px;
    resize: vertical;
    min-height: 80px;
    transition:
      border-color 120ms ease,
      background 120ms ease;
  }

  .editor__textarea:focus {
    outline: none;
    border-color: rgba(120, 180, 255, 0.5);
    background: var(--fp-color-surface-secondary);
  }

  .editor__actions {
    display: flex;
    flex-direction: row;
    gap: 8px;
    justify-content: flex-end;
  }

  .editor__save,
  .editor__discard {
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
  .editor__discard:disabled {
    opacity: 0.4;
    cursor: not-allowed;
  }

  .editor__save:not(:disabled):hover,
  .editor__discard:not(:disabled):hover {
    background: var(--fp-color-surface-secondary);
    border-color: rgba(120, 180, 255, 0.5);
    color: var(--fp-color-text-primary);
  }

  .editor__save--dirty {
    background: rgba(120, 180, 255, 0.18);
    border-color: rgba(120, 220, 255, 0.85);
    color: var(--fp-color-text-primary);
  }
</style>
