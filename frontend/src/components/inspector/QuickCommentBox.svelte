<!--
  QuickCommentBox — the floating hovering box for quick-comment mode + the
  inline comment input that pops up next to each freshly picked element.

  Quick-comment mode (``quickCommentMode`` localState) collapses the whole HUD:
  App.svelte hides the normal panels and renders only this box. The box shows the
  mode is active plus a Done + ✕ button (both exit the mode — picks are saved on
  click, a half-typed note is flushed on blur).

  The rapid loop:
    click element  → InspectorLayer captures the Pick → submitPick + openInput
    inline <input> → auto-focused; user types a note
    Enter / blur-with-text → updateComment + commitInput → input clears, ready
    Escape → cancelInput (discard, no save); pick-mode stays active

  Esc with NO input open exits the whole mode (mirrors the box's exit button).
  Persisting the typed comment uses the same wire-path as CommentEditor:
  ``backendState.inspector.updateComment(pickId, comment)``.

  Position: the inline input is anchored just under the picked element using the
  pending pick's viewport ``rect`` (position: fixed). If the rect is null it
  falls back to anchoring at the hovering box. The box is pinned bottom-right;
  ``pointer-events: auto`` so its controls + the input are clickable while the
  InspectorLayer surface underneath stays pick-active.
-->

<script lang="ts">
  import { backendState } from '../../backend-state/backend-state.svelte';
  import { keyboard } from '../../services/keyboard/keyboard.svelte';
  import { quickCommentMode } from '../../local-state/quick-comment-mode.svelte';

  const active = $derived(quickCommentMode.active);
  const pending = $derived(quickCommentMode.pending);

  // The inline input's value — local draft, reset every time a new pick opens.
  let draft = $state('');
  // Bound to the <input> so we can imperatively focus it on open.
  let inputEl = $state<HTMLInputElement | null>(null);

  /**
   * Whenever a new pick becomes pending, clear the draft + auto-focus the
   * freshly-rendered input. ``pending`` is the tracked dependency; the
   * focus()/select() run after the DOM updates (requestAnimationFrame).
   */
  $effect(() => {
    const p = quickCommentMode.pending;
    if (!p) return;
    draft = '';
    const handle = requestAnimationFrame(() => {
      inputEl?.focus();
    });
    return () => cancelAnimationFrame(handle);
  });

  /**
   * Save the typed comment (if any) for the pending pick + ready the next pick.
   * Empty/whitespace-only drafts are NOT persisted, but still advance the loop.
   */
  function save(): void {
    const p = quickCommentMode.pending;
    if (!p) return;
    const text = draft.trim();
    if (text.length > 0) {
      backendState.inspector.updateComment(p.pickId, text);
    }
    quickCommentMode.commitInput();
    draft = '';
  }

  /** Discard the inline input without saving. */
  function discard(): void {
    quickCommentMode.cancelInput();
    draft = '';
  }

  function onKeydown(e: KeyboardEvent): void {
    if (e.key === 'Enter') {
      e.preventDefault();
      e.stopPropagation();
      save();
    } else if (e.key === 'Escape') {
      e.preventDefault();
      e.stopPropagation();
      discard();
    }
  }

  /**
   * Blur commits the comment IF the user typed something — leaving a note half-
   * typed and clicking elsewhere should keep it, not silently drop it. An empty
   * blur is a no-op (the input just stays open for the same pick).
   */
  function onBlur(): void {
    if (draft.trim().length > 0) save();
  }

  function exit(): void {
    quickCommentMode.exit();
  }

  /**
   * Global Escape handler: when NO inline input is open, Esc exits the whole
   * mode. (When an input IS open, the input's own onKeydown handles Esc to
   * discard first — capture-phase fires there, and we guard on pending here.)
   */
  $effect(() => {
    const unsub = keyboard.subscribe('Escape', () => {
      if (quickCommentMode.active && quickCommentMode.pending === null) {
        quickCommentMode.exit();
      }
    });
    return unsub;
  });
</script>

{#if active}
  {#if pending}
    <!--
      Inline input anchored to the picked element (rect) or the box (null rect).
      svelte-ignore: the keydown is handled on the input itself.
    -->
    <div
      class="qc-input"
      class:qc-input--floating={pending.rect !== null}
      style:left={pending.rect ? `${pending.rect.x}px` : undefined}
      style:top={pending.rect ? `${pending.rect.y + pending.rect.height + 6}px` : undefined}
    >
      <!-- svelte-ignore a11y_autofocus -->
      <input
        bind:this={inputEl}
        bind:value={draft}
        class="qc-input__field"
        type="text"
        placeholder="Notiz — Enter speichert, Esc verwirft"
        aria-label="quick comment"
        onkeydown={onKeydown}
        onblur={onBlur}
      />
    </div>
  {/if}

  <div class="qc-box" role="status" aria-label="quick-comment mode active">
    <span class="qc-box__dot"></span>
    <span class="qc-box__title">⚡ quick-comment</span>
    <!-- Done + ✕ are the same action: deactivate the tool (picks are already saved
         on click; a half-typed note is flushed by the input's blur). -->
    <button
      type="button"
      class="qc-box__done"
      onclick={exit}
      title="Done — exit quick-comment mode (Esc)"
      aria-label="done, exit quick-comment mode"
    >
      Done
    </button>
    <button
      type="button"
      class="qc-box__exit"
      onclick={exit}
      title="Done — exit quick-comment mode (Esc)"
      aria-label="exit quick-comment mode"
    >
      ✕
    </button>
  </div>
{/if}

<style>
  /* ---- floating hovering box (bottom-right) ---- */
  .qc-box {
    position: fixed;
    right: 16px;
    bottom: 16px;
    z-index: 12;
    pointer-events: auto;
    display: flex;
    align-items: center;
    gap: 10px;
    padding: 8px 10px 8px 12px;
    background: var(--fp-color-surface-overlay);
    border: 1px solid var(--fp-color-border-strong);
    border-radius: 8px;
    box-shadow: 0 6px 24px rgba(0, 0, 0, 0.35);
    font-family: inherit;
    color: var(--fp-color-text-primary);
  }

  .qc-box__dot {
    width: 8px;
    height: 8px;
    border-radius: 50%;
    background: var(--fp-color-accent);
    box-shadow: 0 0 8px color-mix(in srgb, var(--fp-color-accent) 70%, transparent);
    flex-shrink: 0;
    animation: qc-pulse 1.4s ease-in-out infinite;
  }

  @keyframes qc-pulse {
    0%,
    100% {
      opacity: 1;
    }
    50% {
      opacity: 0.35;
    }
  }

  .qc-box__title {
    font-size: 12px;
    font-weight: 600;
    letter-spacing: 0.02em;
    margin-right: 6px;
  }

  .qc-box__done {
    background: var(--fp-color-accent);
    border: 1px solid var(--fp-color-accent);
    color: var(--fp-color-accent-text);
    font: inherit;
    font-size: 11px;
    font-weight: 600;
    line-height: 1;
    padding: 5px 12px;
    border-radius: 4px;
    cursor: pointer;
    transition: filter 120ms ease;
  }

  .qc-box__done:hover {
    filter: brightness(1.08);
  }

  .qc-box__exit {
    background: var(--fp-color-surface-secondary);
    border: 1px solid var(--fp-color-border);
    color: var(--fp-color-text-secondary);
    font: inherit;
    font-size: 11px;
    line-height: 1;
    padding: 4px 7px;
    border-radius: 4px;
    cursor: pointer;
    transition:
      background 120ms ease,
      border-color 120ms ease,
      color 120ms ease;
  }

  .qc-box__exit:hover {
    background: var(--fp-color-hover-bg);
    border-color: var(--fp-color-accent);
    color: var(--fp-color-text-primary);
  }

  /* ---- inline comment input ---- */
  .qc-input {
    position: fixed;
    /* Default (null rect): sit just above the bottom-right box. */
    right: 16px;
    bottom: 64px;
    z-index: 13;
    pointer-events: auto;
  }

  /* Floating variant: anchored to the picked element via left/top, so unset the
     bottom-right pinning. */
  .qc-input--floating {
    right: auto;
    bottom: auto;
  }

  .qc-input__field {
    width: 280px;
    max-width: 60vw;
    background: var(--fp-color-surface-overlay);
    border: 1px solid var(--fp-color-accent);
    border-radius: 6px;
    color: var(--fp-color-text-primary);
    font: inherit;
    font-size: 12px;
    padding: 7px 10px;
    box-shadow: 0 4px 18px rgba(0, 0, 0, 0.35);
  }

  .qc-input__field::placeholder {
    color: var(--fp-color-text-muted);
  }

  .qc-input__field:focus {
    outline: none;
    border-color: var(--fp-color-accent);
    box-shadow:
      0 4px 18px rgba(0, 0, 0, 0.35),
      0 0 0 2px color-mix(in srgb, var(--fp-color-accent) 35%, transparent);
  }
</style>
