<script lang="ts">
  import type { Snippet } from 'svelte';
  import type { HTMLButtonAttributes } from 'svelte/elements';

  export type ButtonVariant = 'primary' | 'ghost' | 'outline' | 'danger';
  export type ButtonSize = 'sm' | 'md' | 'lg';

  interface Props extends Omit<HTMLButtonAttributes, 'class'> {
    variant?: ButtonVariant;
    size?: ButtonSize;
    disabled?: boolean;
    class?: string;
    children?: Snippet;
  }

  let {
    variant = 'primary',
    size = 'md',
    disabled = false,
    class: className,
    children,
    ...restProps
  }: Props = $props();
</script>

<button
  {disabled}
  class="fp-btn fp-btn--{variant} fp-btn--{size} {className ?? ''}"
  data-slot="button"
  data-variant={variant}
  data-size={size}
  {...restProps}
>
  {#if children}{@render children()}{/if}
</button>

<style>
  .fp-btn {
    display: inline-flex;
    align-items: center;
    justify-content: center;
    gap: 0.5rem;
    white-space: nowrap;
    border-radius: var(--fp-radius-md);
    font-family: var(--fp-font-sans);
    font-weight: var(--fp-font-weight-medium);
    line-height: var(--fp-line-height-tight);
    cursor: pointer;
    border: 1px solid transparent;
    transition:
      background-color 150ms ease,
      color 150ms ease,
      border-color 150ms ease,
      box-shadow 150ms ease;
  }

  .fp-btn:disabled {
    opacity: 0.5;
    cursor: not-allowed;
    pointer-events: none;
  }

  /* Sizes */
  .fp-btn--sm {
    padding: 0.25rem 0.75rem;
    font-size: var(--fp-font-size-sm);
  }
  .fp-btn--md {
    padding: 0.5rem 1rem;
    font-size: var(--fp-font-size-sm);
  }
  .fp-btn--lg {
    padding: 0.625rem 1.25rem;
    font-size: var(--fp-font-size-md);
  }

  /* Variants */
  .fp-btn--primary {
    background-color: var(--fp-color-accent);
    color: var(--fp-white);
    border-color: var(--fp-color-accent);
    box-shadow: var(--fp-shadow-sm);
  }
  .fp-btn--primary:hover:not(:disabled) {
    background-color: var(--fp-color-accent-hover);
    border-color: var(--fp-color-accent-hover);
  }

  .fp-btn--ghost {
    background-color: transparent;
    color: var(--fp-color-text-primary);
    border-color: transparent;
  }
  .fp-btn--ghost:hover:not(:disabled) {
    background-color: var(--fp-color-accent-subtle);
  }

  .fp-btn--outline {
    background-color: transparent;
    color: var(--fp-color-accent);
    border-color: var(--fp-color-border);
  }
  .fp-btn--outline:hover:not(:disabled) {
    background-color: var(--fp-color-accent-subtle);
    border-color: var(--fp-color-accent);
  }

  .fp-btn--danger {
    background-color: var(--fp-color-error);
    color: var(--fp-white);
    border-color: var(--fp-color-error);
  }
  .fp-btn--danger:hover:not(:disabled) {
    filter: brightness(0.9);
  }
</style>
