<!--
  Toolbar — Inline-Content vom Top-Panel.

  Layout: [brand]  [events · picks · regions · relations]  [actions]

  Stats sind klickbare pills (StatPill primitive):
    - events-stat: live event-count + element-stats. Click → events-tab + open left panel.
    - picks-stat: total picks count + inline overlay-visibility-toggle.
    - regions-stat: total regions count + inline overlay-visibility-toggle.
    - relations-stat: total relations count + inline overlay-visibility-toggle.

  Counters filtern hud-chrome raus (isHudChrome) — InspectorLayer-events bleiben
  drin (user-intent zur Page).
-->

<script lang="ts">
  import { backendState } from '../backend-state/backend-state.svelte';
  import { uiPrefs } from '../local-state/ui-prefs.svelte';
  import { quickCommentMode } from '../local-state/quick-comment-mode.svelte';
  import { eventInterceptor, isHudChrome } from '../services/event-interceptor';
  import StatMetric from './primitives/StatMetric.svelte';
  import StatPill from './primitives/StatPill.svelte';

  const allHidden = $derived(backendState.panel.allHidden);

  // -------- Events stat --------
  const interceptorEnabled = $derived(eventInterceptor.enabled);
  const pageEventCount = $derived(eventInterceptor.events.filter((e) => !isHudChrome(e)).length);
  const elementsSeen = $derived(eventInterceptor.elementsSeen);
  const elementsWithEvents = $derived(eventInterceptor.elementsWithEvents);
  const eventsTooltip = $derived(
    'Page events (HUD-chrome ausgeblendet). Per-type total: ' +
      Object.entries(eventInterceptor.countsByType)
        .map(([k, v]) => `${k}=${v}`)
        .join(', ') +
      '. Klick: events-tab öffnen.'
  );
  const eventsDotState = $derived<'active' | 'paused' | 'neutral'>(
    interceptorEnabled ? 'active' : 'paused'
  );

  // -------- Picks stat --------
  const picksCount = $derived(backendState.inspector.picks.length);
  const activePickId = $derived(backendState.inspector.activePickId);
  const picksTooltip = $derived(
    uiPrefs.picksVisible
      ? `Picks overlay sichtbar · ${picksCount} picks${activePickId ? ` · active: ${activePickId.slice(0, 8)}…` : ''}. Klick: picks-tab öffnen.`
      : `Picks overlay versteckt · ${picksCount} picks. Klick: picks-tab öffnen + overlay an.`
  );
  // Picks-dot: active wenn picks da + visible; paused wenn picks da + hidden;
  // neutral wenn keine picks. Konsistent mit regions/relations-pattern.
  const picksDotState = $derived<'active' | 'paused' | 'neutral'>(
    uiPrefs.picksVisible && picksCount > 0 ? 'active' : picksCount > 0 ? 'paused' : 'neutral'
  );

  // -------- Relations stat --------
  const relationsCount = $derived(backendState.inspector.relations.length);
  const relationsTooltip = $derived(
    uiPrefs.relationsVisible
      ? `Relations overlay sichtbar · ${relationsCount} edges · click to hide / re-open tab`
      : `Relations overlay versteckt · ${relationsCount} edges · click to show / open tab`
  );
  const relationsDotState = $derived<'active' | 'paused' | 'neutral'>(
    uiPrefs.relationsVisible && relationsCount > 0
      ? 'active'
      : relationsCount > 0
        ? 'paused'
        : 'neutral'
  );

  // -------- Regions stat --------
  const regionsCount = $derived(backendState.inspector.regions.length);
  const regionsTooltip = $derived(
    uiPrefs.regionsVisible
      ? `Regions overlay sichtbar · ${regionsCount} regions · click to open tab`
      : `Regions overlay versteckt · ${regionsCount} regions · click to show / open tab`
  );
  const regionsDotState = $derived<'active' | 'paused' | 'neutral'>(
    uiPrefs.regionsVisible && regionsCount > 0 ? 'active' : regionsCount > 0 ? 'paused' : 'neutral'
  );

  // -------- Quick-comment mode --------
  const quickActive = $derived(quickCommentMode.active);

  /** Toggle quick-comment mode: collapse the HUD to a hovering box + rapid-comment loop. */
  function toggleQuickComment(): void {
    if (quickCommentMode.active) {
      quickCommentMode.exit();
    } else {
      quickCommentMode.enter();
    }
  }

  // -------- Handlers --------
  function toggleHideAll(): void {
    backendState.panel.toggleHideAll();
  }

  /** Ensure left panel open. Idempotent. */
  function ensureLeftPanelOpen(): void {
    if (!backendState.panel.panels.left.open) {
      backendState.panel.togglePanel('left');
    }
  }

  function openEventsView(): void {
    ensureLeftPanelOpen();
    uiPrefs.showEventsTab();
  }

  function openPicksView(): void {
    ensureLeftPanelOpen();
    uiPrefs.showPicksTab();
    if (!uiPrefs.picksVisible) {
      uiPrefs.togglePicksVisible();
    }
  }

  function togglePicksOverlay(e: MouseEvent): void {
    e.stopPropagation();
    uiPrefs.togglePicksVisible();
  }

  /**
   * Relations-pill is a dual-action button:
   *   - click → open relations-tab + ensure overlay visible
   *   - matches the events/picks pattern (open the tab)
   * Visibility-toggle bleibt eigener Button daneben (hide-all / show-all macht
   * man oft separat als "ich will jetzt nichts sehen" — gleiche logic).
   */
  function openRelationsView(): void {
    ensureLeftPanelOpen();
    uiPrefs.showRelationsTab();
    // Wenn der overlay-toggle off war, schalten wir ihn jetzt an — der user
    // hat geklickt um Relations zu sehen, also will er sie sehen.
    if (!uiPrefs.relationsVisible) {
      uiPrefs.toggleRelationsVisible();
    }
  }

  function toggleRelationsOverlay(e: MouseEvent): void {
    // Stop-propagation damit der pill-click (openRelationsView) nicht
    // gleichzeitig feuert — wir wollen nur visibility toggeln.
    e.stopPropagation();
    uiPrefs.toggleRelationsVisible();
  }

  function openRegionsView(): void {
    ensureLeftPanelOpen();
    uiPrefs.showRegionsTab();
    if (!uiPrefs.regionsVisible) {
      uiPrefs.toggleRegionsVisible();
    }
  }

  function toggleRegionsOverlay(e: MouseEvent): void {
    e.stopPropagation();
    uiPrefs.toggleRegionsVisible();
  }
</script>

<div class="toolbar">
  <span class="brand">frontprompt</span>

  <div class="stats">
    <StatPill
      onclick={openEventsView}
      title={eventsTooltip}
      ariaLabel="open events tab"
      dotState={eventsDotState}
    >
      {#snippet content()}
        <StatMetric num={pageEventCount} label="events" />
        <span class="metric__sep">·</span>
        <StatMetric num={elementsWithEvents} divider="/" secondaryNum={elementsSeen} label="el" />
      {/snippet}
    </StatPill>

    <StatPill
      onclick={openPicksView}
      title={picksTooltip}
      ariaLabel="open picks tab"
      dotState={picksDotState}
    >
      {#snippet content()}
        <StatMetric num={picksCount} label="picks" />
        <button
          type="button"
          class="pill-toggle"
          class:pill-toggle--off={!uiPrefs.picksVisible}
          onclick={togglePicksOverlay}
          title={uiPrefs.picksVisible ? 'Hide picks overlay' : 'Show picks overlay'}
          aria-label={uiPrefs.picksVisible ? 'hide picks overlay' : 'show picks overlay'}
          aria-pressed={uiPrefs.picksVisible}
        >
          {uiPrefs.picksVisible ? '◉' : '○'}
        </button>
      {/snippet}
    </StatPill>

    <StatPill
      onclick={openRegionsView}
      title={regionsTooltip}
      ariaLabel="open regions tab"
      dotState={regionsDotState}
    >
      {#snippet content()}
        <StatMetric num={regionsCount} label="regions" />
        <button
          type="button"
          class="pill-toggle"
          class:pill-toggle--off={!uiPrefs.regionsVisible}
          onclick={toggleRegionsOverlay}
          title={uiPrefs.regionsVisible ? 'Hide regions overlay' : 'Show regions overlay'}
          aria-label={uiPrefs.regionsVisible ? 'hide regions overlay' : 'show regions overlay'}
          aria-pressed={uiPrefs.regionsVisible}
        >
          {uiPrefs.regionsVisible ? '◉' : '○'}
        </button>
      {/snippet}
    </StatPill>

    <StatPill
      onclick={openRelationsView}
      title={relationsTooltip}
      ariaLabel="open relations tab"
      dotState={relationsDotState}
    >
      {#snippet content()}
        <StatMetric num={relationsCount} label="relations" />
        <!--
          Inline visibility-toggle als kleines Icon — Doppel-funktion: pill-click
          öffnet tab + macht overlay sichtbar, dieses kleine icon togglet NUR
          visibility (stop-propagation). Spart einen extra-Button im actions-strip.
        -->
        <button
          type="button"
          class="pill-toggle"
          class:pill-toggle--off={!uiPrefs.relationsVisible}
          onclick={toggleRelationsOverlay}
          title={uiPrefs.relationsVisible ? 'Hide relations overlay' : 'Show relations overlay'}
          aria-label={uiPrefs.relationsVisible
            ? 'hide relations overlay'
            : 'show relations overlay'}
          aria-pressed={uiPrefs.relationsVisible}
        >
          {uiPrefs.relationsVisible ? '◉' : '○'}
        </button>
      {/snippet}
    </StatPill>
  </div>

  <div class="actions">
    <button
      type="button"
      class="btn"
      class:btn--active={quickActive}
      onclick={toggleQuickComment}
      aria-label={quickActive ? 'exit quick-comment mode' : 'enter quick-comment mode'}
      aria-pressed={quickActive}
      title={quickActive
        ? 'Exit quick-comment mode'
        : 'Quick-comment: collapse HUD, comment many elements fast'}
    >
      <span class="btn__icon">⚡</span>
      <span class="btn__label">quick</span>
    </button>
    <button
      type="button"
      class="btn"
      onclick={toggleHideAll}
      aria-label={allHidden ? 'show all panels' : 'hide all panels'}
      title={allHidden ? 'Show all panels' : 'Hide all panels'}
    >
      <span class="btn__icon">{allHidden ? '▣' : '▢'}</span>
      <span class="btn__label">{allHidden ? 'show all' : 'hide all'}</span>
    </button>
  </div>
</div>

<style>
  .toolbar {
    display: flex;
    align-items: center;
    justify-content: space-between;
    gap: 12px;
    width: 100%;
    height: 100%;
    font-family: inherit;
  }

  .brand {
    font-size: 12px;
    font-weight: 600;
    letter-spacing: 0.04em;
    text-transform: lowercase;
    color: var(--fp-color-accent);
    white-space: nowrap;
    flex-shrink: 0;
  }

  /* ---- stats cluster (centered) ---- */

  .stats {
    display: flex;
    align-items: center;
    gap: 6px;
    flex-shrink: 0;
  }

  /* StatMetric primitive owns metric/metric__num/metric__label/metric__divider
     styling now (DRY). Only metric__sep (separator dot between two StatMetrics
     within the same pill) lives here, because it's pill-layout-specific. */
  :global(.stats .metric__sep) {
    color: var(--fp-color-text-muted);
    margin: 0 2px;
  }

  /* Inline-icon-button INSIDE a StatPill — used by relations-pill for the
     visibility-toggle. Stays subtle so it doesn't overshadow the count. */
  .pill-toggle {
    background: transparent;
    border: none;
    color: var(--fp-color-text-secondary);
    font: inherit;
    font-size: 11px;
    line-height: 1;
    padding: 0 2px 0 6px;
    margin-left: 4px;
    cursor: pointer;
    border-left: 1px solid var(--fp-color-border-subtle);
    transition: color 120ms ease;
  }

  .pill-toggle:hover {
    color: var(--fp-color-text-primary);
  }

  .pill-toggle--off {
    color: var(--fp-color-text-muted);
  }

  /* ---- actions ---- */

  .actions {
    display: flex;
    align-items: center;
    gap: 6px;
    flex-shrink: 0;
  }

  .btn {
    background: var(--fp-color-surface-secondary);
    border: 1px solid var(--fp-color-border);
    color: var(--fp-color-text-secondary);
    font: inherit;
    font-size: 11px;
    padding: 3px 9px;
    border-radius: 4px;
    cursor: pointer;
    display: inline-flex;
    align-items: center;
    gap: 5px;
    transition:
      background 120ms ease,
      border-color 120ms ease,
      color 120ms ease;
    white-space: nowrap;
  }

  .btn:hover {
    background: var(--fp-color-hover-bg);
    border-color: var(--fp-color-accent);
    color: var(--fp-color-text-primary);
  }

  /* Active toggle (quick-comment mode on) — accent-tinted so the mode is obvious. */
  .btn--active {
    background: color-mix(in srgb, var(--fp-color-accent) 22%, transparent);
    border-color: var(--fp-color-accent);
    color: var(--fp-color-text-primary);
  }

  .btn:focus-visible {
    outline: 1px solid var(--fp-color-accent);
    outline-offset: 1px;
  }

  .btn__icon {
    font-size: 11px;
    line-height: 1;
    opacity: 0.85;
  }

  .btn__label {
    font-size: 10px;
    letter-spacing: 0.02em;
  }
</style>
