<!--
  EventsTab — diagnostics-tab. Listet captured events, mit filter + controls.

  Wichtig fürs scroll-debugging: zeigt jeden wheel-event mit deltaX/Y, ob
  default_prevented, und ob das danach geforderte scroll-event kam.

  Controls revamped (C2):
    - pause/clear sind icon-only buttons (titles tooltip)
    - type-filter nutzt Dropdown primitive (lowercase-contains search)
    - hud-chrome toggle als kompakter icon button (🛡)
-->

<script lang="ts">
  import { backendState } from '../../../backend-state/backend-state.svelte';
  import Dropdown, { type DropdownOption } from '../../primitives/Dropdown.svelte';
  import {
    eventInterceptor,
    eventMatchesPickPath,
    isHudChrome,
    type InterceptedEventType,
  } from '../../../services/event-interceptor';
  import EventItem from './EventItem.svelte';

  type FilterValue = InterceptedEventType | 'all';

  let typeFilter = $state<FilterValue>('all');
  /** Hide HUD-chrome events. Default: true. InspectorLayer-events bleiben sichtbar. */
  let hideOverlay = $state(true);
  /**
   * Default ON: nur events auf gepickten Elementen (oder deren descendants).
   * Wenn keine picks existieren ist der filter no-op. Toggle-icon ⌖.
   */
  let onPicksOnly = $state(true);

  const picks = $derived(backendState.inspector.picks);
  const pickPaths = $derived(picks.map((p) => p.element.fingerprint.path ?? []));
  const hasPicks = $derived(picks.length > 0);

  // Dropdown-options: live-counts pro type für context
  const filterOptions = $derived<DropdownOption<FilterValue>[]>([
    { value: 'all', label: `all types (${eventInterceptor.events.length})` },
    { value: 'wheel', label: `wheel (${eventInterceptor.countsByType.wheel})` },
    { value: 'scroll', label: `scroll (${eventInterceptor.countsByType.scroll})` },
    { value: 'click', label: `click (${eventInterceptor.countsByType.click})` },
    { value: 'pointerdown', label: `pointerdown (${eventInterceptor.countsByType.pointerdown})` },
    { value: 'keydown', label: `keydown (${eventInterceptor.countsByType.keydown})` },
  ]);

  // Pick-filter aktiv nur wenn (a) on UND (b) picks vorhanden. Sonst no-op.
  const pickFilterActive = $derived(onPicksOnly && hasPicks);

  // Zeige newest first, max 200 in view (Performance — 500-buffer würde DOM-stress)
  const filtered = $derived(
    [...eventInterceptor.events]
      .reverse()
      .filter((e) => {
        if (typeFilter !== 'all' && e.type !== typeFilter) return false;
        if (hideOverlay && isHudChrome(e)) return false;
        if (pickFilterActive) {
          // Path-prefix match gegen IRGENDEINEN pick. Tag-only-paths erlauben
          // false-positives bei geschwister-tags — explizit akzeptiert (siehe
          // eventMatchesPickPath docstring); user kann filter abschalten.
          const matchesAny = pickPaths.some((path) => eventMatchesPickPath(e, path));
          if (!matchesAny) return false;
        }
        return true;
      })
      .slice(0, 200)
  );

  const helperText = $derived(
    pickFilterActive
      ? `Showing events on ${picks.length} picked element${picks.length === 1 ? '' : 's'} (or their descendants).`
      : onPicksOnly && !hasPicks
        ? 'Pick-filter active but no picks captured yet — showing all events.'
        : 'Showing all events. Click ⌖ to filter to picked elements.'
  );

  function toggleRecording(): void {
    eventInterceptor.toggle();
  }

  function clearEvents(): void {
    eventInterceptor.clear();
  }

  function toggleOverlayFilter(): void {
    hideOverlay = !hideOverlay;
  }

  function togglePicksFilter(): void {
    onPicksOnly = !onPicksOnly;
  }
</script>

<div class="events-tab">
  <div class="controls">
    <button
      type="button"
      class="icon-btn"
      class:icon-btn--paused={!eventInterceptor.enabled}
      onclick={toggleRecording}
      title={eventInterceptor.enabled ? 'recording pausieren' : 'recording fortsetzen'}
      aria-label={eventInterceptor.enabled ? 'pause recording' : 'resume recording'}
    >
      {eventInterceptor.enabled ? '⏸' : '▶'}
    </button>
    <button
      type="button"
      class="icon-btn"
      onclick={clearEvents}
      title="event-buffer leeren"
      aria-label="clear events"
    >
      ↺
    </button>

    <Dropdown
      options={filterOptions}
      value={typeFilter}
      onChange={(v) => (typeFilter = v)}
      placeholder="filter type..."
      ariaLabel="filter by event type"
    />

    <button
      type="button"
      class="icon-btn"
      class:icon-btn--toggled={!hideOverlay}
      onclick={toggleOverlayFilter}
      title={hideOverlay
        ? 'HUD-chrome events versteckt — click zum anzeigen'
        : 'HUD-chrome events sichtbar — click zum verstecken'}
      aria-label={hideOverlay ? 'show HUD events' : 'hide HUD events'}
      aria-pressed={!hideOverlay}
    >
      🛡
    </button>

    <button
      type="button"
      class="icon-btn"
      class:icon-btn--toggled={onPicksOnly}
      onclick={togglePicksFilter}
      title={onPicksOnly
        ? 'Filter aktiv: nur events auf gepickten Elementen — click zum abschalten'
        : 'Filter aus: alle events sichtbar — click für pick-filter'}
      aria-label={onPicksOnly ? 'show all events' : 'filter to picked elements'}
      aria-pressed={onPicksOnly}
    >
      ⌖
    </button>

    <span class="stats">{filtered.length} shown · {eventInterceptor.events.length} buffered</span>
  </div>

  <div class="helper" class:helper--active={pickFilterActive}>{helperText}</div>

  {#if filtered.length === 0}
    <div class="empty">
      <p class="empty__hint">Noch keine events.</p>
      <p class="empty__sub">
        Bewege die maus, scrolle, click was an. Events erscheinen hier in capture-phase.
      </p>
    </div>
  {:else}
    <div class="list">
      {#each filtered as event (event.seq)}
        <EventItem {event} />
      {/each}
    </div>
  {/if}
</div>

<style>
  .events-tab {
    display: flex;
    flex-direction: column;
    width: 100%;
    height: 100%;
    min-height: 0;
  }

  .controls {
    display: flex;
    align-items: center;
    gap: 4px;
    padding: 6px 10px;
    border-bottom: 1px solid var(--fp-color-border-subtle);
    background: var(--fp-color-surface-secondary);
    flex-shrink: 0;
    flex-wrap: wrap;
  }

  .icon-btn {
    display: inline-flex;
    align-items: center;
    justify-content: center;
    background: var(--fp-color-surface-secondary);
    border: 1px solid var(--fp-color-border);
    color: var(--fp-color-text-primary);
    font: inherit;
    font-size: 11px;
    line-height: 1;
    width: 24px;
    height: 24px;
    padding: 0;
    border-radius: 3px;
    cursor: pointer;
    transition:
      background 120ms ease,
      border-color 120ms ease,
      color 120ms ease;
  }

  .icon-btn:hover {
    background: var(--fp-color-surface-secondary);
    border-color: rgba(120, 180, 255, 0.5);
  }

  .icon-btn:focus-visible {
    outline: 1px solid rgba(120, 180, 255, 0.7);
    outline-offset: 1px;
  }

  .icon-btn--paused {
    background: rgba(255, 180, 120, 0.18);
    border-color: rgba(255, 180, 120, 0.5);
    color: rgba(255, 220, 180, 0.95);
  }

  .icon-btn--toggled {
    background: rgba(120, 180, 255, 0.18);
    border-color: rgba(120, 180, 255, 0.5);
    color: var(--fp-color-text-primary);
  }

  .stats {
    font-size: 9px;
    color: var(--fp-color-text-muted);
    margin-left: auto;
  }

  /* Helper-text — explains the active filter-state to the user in one line. */
  .helper {
    padding: 5px 10px;
    font-size: 10px;
    line-height: 1.4;
    color: var(--fp-color-text-secondary);
    background: var(--fp-color-surface-secondary);
    border-bottom: 1px solid var(--fp-color-border-subtle);
    flex-shrink: 0;
  }

  .helper--active {
    color: var(--fp-color-text-primary);
    background: rgba(120, 180, 255, 0.06);
  }

  .empty {
    padding: 16px 14px;
    color: var(--fp-color-text-secondary);
  }

  .empty__hint {
    margin: 0 0 4px 0;
    font-size: 12px;
    font-weight: 500;
  }

  .empty__sub {
    margin: 0;
    font-size: 11px;
    color: var(--fp-color-text-secondary);
    line-height: 1.5;
  }

  .list {
    flex: 1 1 auto;
    overflow: auto;
    min-height: 0;
  }
</style>
