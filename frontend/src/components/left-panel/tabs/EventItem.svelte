<!--
  EventItem — eine Zeile in der EventsTab-Liste.

  Layout: [type-chip] [target] [flags] [extra]
    - type-chip: farbig pro event-type
    - target: tag#id.class
    - flags: ⚠ wenn default_prevented, 🛡 wenn in_fp_overlay
    - extra: deltaY für wheel, key für keyboard, scrollY für scroll
-->

<script lang="ts">
  import type { InterceptedEvent } from '../../../services/event-interceptor';

  let { event }: { event: InterceptedEvent } = $props();

  const typeClass = $derived(`type type--${event.type}`);

  const extra = $derived.by((): string => {
    if (event.type === 'wheel') {
      const dx = event.delta_x ?? 0;
      const dy = event.delta_y ?? 0;
      return `Δ ${dx.toFixed(0)},${dy.toFixed(0)}`;
    }
    if (event.type === 'scroll') {
      return `scrollY=${event.scroll_y?.toFixed(0) ?? '?'}`;
    }
    if (event.type === 'keydown') {
      return event.key ?? '';
    }
    return '';
  });
</script>

<div class="event-item">
  <span class={typeClass}>{event.type}</span>
  <span class="target" title={event.target}>{event.target}</span>
  {#if event.default_prevented}
    <span class="flag flag--prevented" title="default_prevented = true beim capture">⚠</span>
  {/if}
  {#if event.in_fp_overlay}
    <span class="flag flag--ours" title="target ist innerhalb fp-overlay">🛡</span>
  {/if}
  {#if extra}
    <span class="extra">{extra}</span>
  {/if}
</div>

<style>
  .event-item {
    display: flex;
    align-items: center;
    gap: 6px;
    padding: 3px 10px;
    font-size: 10px;
    font-family: 'SF Mono', 'JetBrains Mono', Menlo, Consolas, monospace;
    border-bottom: 1px solid var(--fp-color-border-subtle);
    min-width: 0;
  }

  .type {
    display: inline-block;
    font-size: 9px;
    text-transform: uppercase;
    letter-spacing: 0.04em;
    padding: 1px 5px;
    border-radius: 2px;
    flex-shrink: 0;
    width: 56px;
    text-align: center;
  }

  .type--wheel {
    background: rgba(120, 220, 255, 0.18);
    color: rgba(180, 230, 255, 0.95);
  }
  .type--scroll {
    background: rgba(200, 180, 255, 0.18);
    color: var(--fp-color-text-primary);
  }
  .type--click {
    background: rgba(120, 255, 180, 0.18);
    color: rgba(180, 255, 200, 0.95);
  }
  .type--pointerdown {
    background: rgba(255, 220, 120, 0.18);
    color: rgba(255, 230, 160, 0.95);
  }
  .type--keydown {
    background: rgba(255, 180, 220, 0.18);
    color: var(--fp-color-text-primary);
  }

  .target {
    flex: 1 1 auto;
    color: var(--fp-color-text-primary);
    overflow: hidden;
    text-overflow: ellipsis;
    white-space: nowrap;
    min-width: 0;
  }

  .flag {
    font-size: 11px;
    flex-shrink: 0;
    cursor: help;
  }

  .flag--prevented {
    color: rgba(255, 160, 100, 0.95);
  }

  .flag--ours {
    color: var(--fp-color-text-secondary);
  }

  .extra {
    color: var(--fp-color-text-secondary);
    font-size: 9px;
    flex-shrink: 0;
  }
</style>
