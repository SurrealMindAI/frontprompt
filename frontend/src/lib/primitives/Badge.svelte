<script lang="ts">
  import type { Snippet } from 'svelte';

  export type BadgeVariant = 'default' | 'success' | 'warning' | 'error' | 'neutral';

  interface Props {
    variant?: BadgeVariant;
    class?: string;
    children?: Snippet;
    [key: string]: unknown;
  }

  let { variant = 'default', class: className, children, ...restProps }: Props = $props();
</script>

<span
  class="fp-badge fp-badge--{variant} {className ?? ''}"
  data-slot="badge"
  data-variant={variant}
  {...restProps}
>
  {#if children}{@render children()}{/if}
</span>

<style>
  .fp-badge {
    display: inline-flex;
    align-items: center;
    border-radius: var(--fp-radius-full);
    padding: 0.125rem 0.625rem;
    font-size: var(--fp-font-size-xs);
    font-weight: var(--fp-font-weight-semibold);
    line-height: var(--fp-line-height-tight);
    white-space: nowrap;
  }

  .fp-badge--default {
    background-color: var(--fp-color-badge-default-bg);
    color: var(--fp-color-badge-default-text);
  }
  .fp-badge--success {
    background-color: var(--fp-color-badge-success-bg);
    color: var(--fp-color-badge-success-text);
  }
  .fp-badge--warning {
    background-color: var(--fp-color-badge-warning-bg);
    color: var(--fp-color-badge-warning-text);
  }
  .fp-badge--error {
    background-color: var(--fp-color-badge-error-bg);
    color: var(--fp-color-badge-error-text);
  }
  .fp-badge--neutral {
    background-color: var(--fp-color-badge-neutral-bg);
    color: var(--fp-color-badge-neutral-text);
  }
</style>
