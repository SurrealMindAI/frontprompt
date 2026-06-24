<!--
  StatPill — clickable pill mit status-dot + frei wählbarem content snippet.
  Layout: [dot] [content via snippet]. Reusable primitive für die Toolbar-stats
  (events + picks). API + usage-beispiel siehe Script-JSDoc unten.
-->

<script lang="ts">
  /**
   * StatPill — clickable status-pill mit dot + content-snippet.
   *
   * @example
   * ```svelte
   * <StatPill
   *   ariaLabel="open events tab"
   *   title="..."
   *   onclick={() => openEventsView()}
   *   dotState="active"
   * >
   *   {#snippet content()}
   *     <span class="metric">42 events</span>
   *   {/snippet}
   * </StatPill>
   * ```
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
  }: {
    onclick: () => void;
    title?: string;
    ariaLabel?: string;
    dotState?: DotState;
    content: Snippet;
  } = $props();
</script>

<button type="button" class="pill" {onclick} {title} aria-label={ariaLabel}>
  <span
    class="pill__dot"
    class:pill__dot--active={dotState === 'active'}
    class:pill__dot--paused={dotState === 'paused'}
  ></span>
  {@render content()}
</button>

<style>
  .pill {
    display: flex;
    align-items: center;
    gap: 8px;
    font-size: 10px;
    color: var(--fp-color-text-secondary);
    padding: 3px 10px;
    background: var(--fp-color-surface-secondary);
    border: 1px solid var(--fp-color-border-subtle);
    border-radius: 12px;
    white-space: nowrap;
    cursor: pointer;
    font-family: inherit;
    transition:
      background 120ms ease,
      border-color 120ms ease,
      color 120ms ease;
  }

  .pill:hover {
    background: var(--fp-color-surface-secondary);
    border-color: rgba(120, 180, 255, 0.4);
    color: var(--fp-color-text-primary);
  }

  .pill:focus-visible {
    outline: 1px solid rgba(120, 180, 255, 0.7);
    outline-offset: 1px;
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
