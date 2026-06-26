<!--
  AssertionEditor — form to author a new AssertionEntry on a stored recording.

  Sends AssertionAddedToRecordingRequested via bridge on submit.
  All form fields are localState draft (ADR-018: in-flight edit is ephemeral).

  Props:
    recording_id — the recording to add the assertion to
    insert_after_seq — optional; if provided, inserts after that seq; otherwise appends

  Assertion types that don't need an expected value (selector_exists, visible)
  auto-set expected=null + comparator="none". Other types show the expected input.
-->

<script lang="ts">
  import { bridge } from '../../bridge/bridge.svelte';
  import type { AssertionAddedToRecordingRequested } from '../../_generated/schemas';

  let {
    recording_id,
    insert_after_seq = null,
  }: {
    recording_id: string;
    insert_after_seq?: number | null;
  } = $props();

  const SCHEMA_VERSION = '0.9.0';

  // localState draft (ADR-018: ephemeral in-flight edit)
  let assertionType = $state<string>('selector_exists');
  let target = $state('');
  let expected = $state('');
  let comparator = $state<string>('none');
  let description = $state('');

  // Types that don't need an expected value / have comparator="none"
  const noExpectedTypes = new Set(['selector_exists', 'visible']);
  const showExpected = $derived(!noExpectedTypes.has(assertionType));

  // target_kind: url_equals uses url, everything else uses selector
  const targetKind = $derived(assertionType === 'url_equals' ? 'url' : 'selector');

  function resetDraft(): void {
    assertionType = 'selector_exists';
    target = '';
    expected = '';
    comparator = 'none';
    description = '';
  }

  function submit(): void {
    const resolvedExpected = showExpected ? expected : null;
    const resolvedComparator = showExpected ? comparator : 'none';

    const message: AssertionAddedToRecordingRequested = {
      kind: 'assertion_added_to_recording_requested',
      schema_version: SCHEMA_VERSION,
      recording_id,
      assertion: {
        assertion_id: crypto.randomUUID(),
        assertion_type: assertionType,
        target,
        target_kind: targetKind,
        expected: resolvedExpected || null,
        comparator: resolvedComparator,
        description,
      },
      insert_after_seq: insert_after_seq ?? null,
    };

    void bridge.send(message);
    resetDraft();
  }

  function cancel(): void {
    resetDraft();
  }
</script>

<div class="assertion-editor">
  <div class="assertion-editor__row">
    <label class="assertion-editor__label" for="assertion-type">type</label>
    <select id="assertion-type" class="assertion-type assertion-editor__select" bind:value={assertionType}>
      <option value="selector_exists">selector_exists</option>
      <option value="text_equals">text_equals</option>
      <option value="text_contains">text_contains</option>
      <option value="visible">visible</option>
      <option value="url_equals">url_equals</option>
    </select>
  </div>

  <div class="assertion-editor__row">
    <label class="assertion-editor__label" for="assertion-target">target</label>
    <input
      id="assertion-target"
      class="assertion-target assertion-editor__input"
      type="text"
      bind:value={target}
      placeholder={assertionType === 'url_equals' ? 'https://example.com/path' : 'CSS selector'}
    />
  </div>

  {#if showExpected}
    <div class="assertion-editor__row">
      <label class="assertion-editor__label" for="assertion-expected">expected</label>
      <input
        id="assertion-expected"
        class="assertion-expected assertion-editor__input"
        type="text"
        bind:value={expected}
        placeholder="Expected value"
      />
    </div>

    <div class="assertion-editor__row">
      <label class="assertion-editor__label" for="assertion-comparator">comparator</label>
      <select id="assertion-comparator" class="assertion-comparator assertion-editor__select" bind:value={comparator}>
        <option value="equals">equals</option>
        <option value="contains">contains</option>
        <option value="regex">regex</option>
      </select>
    </div>
  {:else}
    <!-- comparator="none" for selector_exists/visible — invisible but present for arch tests -->
    <input type="hidden" class="assertion-comparator" value="none" />
  {/if}

  <div class="assertion-editor__row">
    <label class="assertion-editor__label" for="assertion-description">description</label>
    <input
      id="assertion-description"
      class="assertion-description assertion-editor__input"
      type="text"
      bind:value={description}
      placeholder="Optional label for report"
    />
  </div>

  <div class="assertion-editor__actions">
    <button type="button" class="assertion-submit assertion-editor__btn assertion-editor__btn--primary" onclick={submit}>
      Add
    </button>
    <button type="button" class="assertion-cancel assertion-editor__btn" onclick={cancel}>
      Cancel
    </button>
  </div>
</div>

<style>
  .assertion-editor {
    display: flex;
    flex-direction: column;
    gap: 6px;
    padding: 10px 14px;
    border-top: 1px solid var(--fp-color-border-subtle);
  }

  .assertion-editor__row {
    display: flex;
    flex-direction: column;
    gap: 3px;
  }

  .assertion-editor__label {
    font-size: 10px;
    text-transform: uppercase;
    letter-spacing: 0.05em;
    color: var(--fp-color-text-muted);
  }

  .assertion-editor__input,
  .assertion-editor__select {
    background: var(--fp-color-surface-secondary);
    border: 1px solid var(--fp-color-border);
    border-radius: 4px;
    color: var(--fp-color-text-primary);
    font: inherit;
    font-size: 12px;
    padding: 5px 8px;
    transition: border-color 120ms ease, background 120ms ease;
  }

  .assertion-editor__input:focus,
  .assertion-editor__select:focus {
    outline: none;
    border-color: rgba(120, 180, 255, 0.5);
  }

  .assertion-editor__actions {
    display: flex;
    flex-direction: row;
    gap: 8px;
    justify-content: flex-end;
    margin-top: 2px;
  }

  .assertion-editor__btn {
    background: var(--fp-color-surface-secondary);
    border: 1px solid var(--fp-color-border);
    color: var(--fp-color-text-primary);
    font: inherit;
    font-size: 11px;
    padding: 4px 12px;
    border-radius: 4px;
    cursor: pointer;
    transition: background 120ms ease, border-color 120ms ease;
  }

  .assertion-editor__btn:hover {
    border-color: rgba(120, 180, 255, 0.5);
  }

  .assertion-editor__btn--primary {
    background: rgba(120, 180, 255, 0.18);
    border-color: rgba(120, 220, 255, 0.85);
  }
</style>
