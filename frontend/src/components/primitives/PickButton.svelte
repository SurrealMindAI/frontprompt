<!--
  PickButton — DRY-shared visual primitive für "Pick" (Element auf der Page wählen).

  Renamed von InspectButton: "Pick" ist semantisch das was der
  User tut — ein Page-Element auswählen. "Inspect" wäre passiver. Der
  technische DOM-overlay-layer heißt weiter ``InspectorLayer`` (implementation-
  detail, separate concern).

  Zwei Varianten:
    - **full** (default): Icon + Label "pick". Used by LeftPanelTools-toolbar.
    - **icon**: kompakter icon-only square. Used by PickPicker (in einer Zeile
      neben dem Dropdown).

  Verhalten ist Caller-defined via ``onclick``. ``active`` + ``disabled`` states
  sind prop-driven — der globale ``pickClaim`` entscheidet wer "active" rendert
  und wer disabled erscheint.
-->
<script lang="ts">
  let {
    variant = 'full',
    active = false,
    disabled = false,
    onclick,
    label = 'pick',
    title,
    ariaLabel,
  }: {
    variant?: 'full' | 'icon';
    active?: boolean;
    disabled?: boolean;
    onclick: () => void;
    label?: string;
    title?: string;
    ariaLabel?: string;
  } = $props();
</script>

<button
  type="button"
  class="pick-btn"
  class:pick-btn--icon={variant === 'icon'}
  class:pick-btn--active={active}
  {disabled}
  {onclick}
  {title}
  aria-pressed={active}
  aria-label={ariaLabel ?? label}
>
  <span class="pick-btn__icon" aria-hidden="true">⊙</span>
  {#if variant === 'full'}
    <span class="pick-btn__label">{label}</span>
  {/if}
</button>

<style>
  .pick-btn {
    display: inline-flex;
    align-items: center;
    justify-content: center;
    gap: 5px;
    background: var(--fp-color-surface-secondary);
    border: 1px solid var(--fp-color-border);
    color: var(--fp-color-text-primary);
    font: inherit;
    font-size: 11px;
    padding: 4px 10px;
    border-radius: 4px;
    cursor: pointer;
    transition:
      background 120ms ease,
      border-color 120ms ease,
      color 120ms ease,
      box-shadow 120ms ease,
      opacity 120ms ease;
    white-space: nowrap;
    flex-shrink: 0;
  }

  .pick-btn:hover:not(:disabled) {
    background: var(--fp-color-surface-secondary);
    border-color: rgba(120, 220, 255, 0.5);
    color: var(--fp-color-text-primary);
  }

  .pick-btn:focus-visible {
    outline: 1px solid rgba(120, 180, 255, 0.7);
    outline-offset: 1px;
  }

  .pick-btn:disabled {
    opacity: 0.4;
    cursor: not-allowed;
  }

  .pick-btn--active {
    background: rgba(120, 220, 255, 0.2);
    border-color: rgba(120, 220, 255, 0.7);
    color: var(--fp-color-text-primary);
    box-shadow: 0 0 0 1px rgba(120, 220, 255, 0.35);
  }

  /* Icon-only square: 28x28, no label */
  .pick-btn--icon {
    width: 28px;
    height: 28px;
    padding: 0;
    gap: 0;
  }

  .pick-btn__icon {
    font-size: 12px;
    line-height: 1;
    opacity: 0.9;
  }

  .pick-btn--icon .pick-btn__icon {
    font-size: 13px;
  }

  .pick-btn--active .pick-btn__icon {
    opacity: 1;
  }

  .pick-btn__label {
    font-size: 10px;
    letter-spacing: 0.02em;
    text-transform: lowercase;
  }
</style>
