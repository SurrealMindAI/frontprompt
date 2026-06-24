<script lang="ts">
  export type StatusDotStatus = 'connected' | 'reconnecting' | 'disconnected';

  interface Props {
    status: StatusDotStatus;
    /** Zugänglicher Text für Screen-Reader */
    label?: string;
    class?: string;
  }

  let { status, label, class: className }: Props = $props();

  const labelMap: Record<StatusDotStatus, string> = {
    connected: 'Verbunden',
    reconnecting: 'Verbinde...',
    disconnected: 'Getrennt',
  };

  let accessibleLabel = $derived(label ?? labelMap[status]);
</script>

<span
  role="status"
  aria-label={accessibleLabel}
  class="fp-status-dot fp-status-dot--{status} {className ?? ''}"
  data-slot="status-dot"
  data-status={status}
></span>

<style>
  .fp-status-dot {
    display: inline-block;
    width: 0.5rem;
    height: 0.5rem;
    border-radius: var(--fp-radius-full);
    flex-shrink: 0;
  }

  .fp-status-dot--connected {
    background-color: var(--fp-color-status-connected);
  }

  .fp-status-dot--reconnecting {
    background-color: var(--fp-color-status-reconnecting);
    animation: fp-pulse 1.5s ease-in-out infinite;
  }

  .fp-status-dot--disconnected {
    background-color: var(--fp-color-status-disconnected);
  }

  @keyframes fp-pulse {
    0%,
    100% {
      opacity: 1;
    }
    50% {
      opacity: 0.4;
    }
  }

  @media (prefers-reduced-motion: reduce) {
    .fp-status-dot--reconnecting {
      animation: none;
    }
  }
</style>
