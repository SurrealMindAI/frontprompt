<!--
  StatPill — status pill with a dot + a clickable "open" area + an optional
  inline action. Layout: [ [dot] [content] ]  [action?]. Reusable primitive for
  the Toolbar stats. API + usage example see the script JSDoc below.

  a11y: the pill is a presentational <div>; the clickable stat is its own
  <button class="pill__open">, and the optional `action` snippet (e.g. a
  visibility-toggle button) is rendered as a SIBLING of that button — never
  nested inside it. A <button> inside a <button> is invalid HTML and a WCAG
  nested-interactive violation, which the previous single-button design had.
-->

<script lang="ts">
  /**
   * StatPill — status pill with dot + clickable "open" button + optional action.
   *
   * @example
   * ```svelte
   * <StatPill
   *   ariaLabel="open picks tab"
   *   title="..."
   *   onclick={() => openPicksView()}
   *   dotState="active"
   * >
   *   {#snippet content()}
   *     <StatMetric num={42} label="picks" />
   *   {/snippet}
   *   {#snippet action()}
   *     <button class="pill-toggle" onclick={toggle}>…</button>
   *   {/snippet}
   * </StatPill>
   * ```
   *
   * `content` renders inside the clickable "open" button. `action` (optional)
   * renders as a sibling — use it for an independent control (e.g. a visibility
   * toggle) so it does not nest interactive elements inside the button.
   *
   * dotState values:
   *   - "active": pulsing green dot (alive, listening)
   *   - "paused": orange dot (intentionally stopped)
   *   - "neutral": gray dot (idle, no signal)
   */
  import type { Snippet } from 'svelte';

  export type DotState = 'active' | 'paused' | 'neutral';

  let {
    onclick,
    title,
    ariaLabel,
    dotState = 'neutral',
    content,
    action,
  }: {
    onclick: () => void;
    title?: string;
    ariaLabel?: string;
    dotState?: DotState;
    content: Snippet;
    action?: Snippet;
  } = $props();
</script>

<div class="pill">
  <button type="button" class="pill__open" {onclick} {title} aria-label={ariaLabel}>
    <span
      class="pill__dot"
      class:pill__dot--active={dotState === 'active'}
      class:pill__dot--paused={dotState === 'paused'}
    ></span>
    {@render content()}
  </button>
  {#if action}{@render action()}{/if}
</div>

<style>
  /* Presentational container — owns the pill chrome (bg/border/radius/padding).
     Not interactive itself; the .pill__open button and any action are. */
  .pill {
    display: inline-flex;
    align-items: center;
    font-size: 10px;
    color: var(--fp-color-text-secondary);
    padding: 3px 10px;
    background: var(--fp-color-surface-secondary);
    border: 1px solid var(--fp-color-border-subtle);
    border-radius: 12px;
    white-space: nowrap;
    font-family: inherit;
    transition:
      background 120ms ease,
      border-color 120ms ease,
      color 120ms ease;
  }

  .pill:hover {
    border-color: rgba(120, 180, 255, 0.4);
    color: var(--fp-color-text-primary);
  }

  /* The clickable "open" area — transparent; the .pill div carries the chrome. */
  .pill__open {
    display: inline-flex;
    align-items: center;
    gap: 8px;
    background: transparent;
    border: none;
    color: inherit;
    font: inherit;
    cursor: pointer;
    padding: 0;
  }

  .pill__open:focus-visible {
    outline: 1px solid rgba(120, 180, 255, 0.7);
    outline-offset: 1px;
    border-radius: 8px;
  }

  .pill__dot {
    width: 6px;
    height: 6px;
    border-radius: 50%;
    background: var(--fp-color-text-muted);
    flex-shrink: 0;
  }

  .pill__dot--active {
    background: rgba(140, 230, 160, 0.95);
    box-shadow: 0 0 4px rgba(140, 230, 160, 0.6);
    animation: pulse 1.8s ease-in-out infinite;
  }

  .pill__dot--paused {
    background: rgba(255, 180, 120, 0.85);
  }

  @keyframes pulse {
    0%,
    100% {
      opacity: 1;
    }
    50% {
      opacity: 0.4;
    }
  }
</style>
