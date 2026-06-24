<!--
  Dashboard — read-only composition root for the about:blank management view.

  Rendered by App.svelte inside `.area--center--dashboard` when
  `overlayContext.isAboutBlank` is true. No backend writes, no schema bump.

  Data sources (all reactive/read-only):
    - SCHEMA_VERSION         ← schema-version.ts (extracted constant)
    - BUILD_VERSION/GIT_SHA  ← _generated/build-info.ts (auto-generated)
    - currentSessionId       ← overlayContext.currentSessionId
    - picks/regions/relations/active ← backendState.inspector
    - events count           ← eventInterceptor.events.filter(!isHudChrome)

  Panel open/closed state is deliberately NOT shown: on about:blank
  the forceClosed wiring collapses all panels regardless of stored .open value,
  so displaying it would be tautological. A static "suppressed" note is shown.

  Layout: a hero stat-band (the four entity counts as big tiles) over a
  responsive auto-fit card grid (Build Info · Session · State). All colours come
  from the inherited `--fp-color-*` theme tokens (defined on `.grid` in
  App.svelte), so the dashboard auto-adapts to the page's light/dark HUD theme.

  All styles live in the <style> block (shadow DOM — no external CSS imports).
-->
<script lang="ts">
  import { SCHEMA_VERSION } from '../../schema-version';
  import { BUILD_VERSION, BUILD_GIT_SHA, BUILD_SESSION } from '../../_generated/build-info';
  import { overlayContext } from '../../services/context/overlay-context.svelte';
  import { backendState } from '../../backend-state/backend-state.svelte';
  import { eventInterceptor, isHudChrome } from '../../services/event-interceptor';
  import { formatCount } from '../../lib/utils/format';
  import DashboardSection from './DashboardSection.svelte';
  import DashboardRow from './DashboardRow.svelte';

  const picksCount = $derived(backendState.inspector.picks.length);
  const regionsCount = $derived(backendState.inspector.regions.length);
  const relationsCount = $derived(backendState.inspector.relations.length);
  const inspectorActive = $derived(backendState.inspector.active);
  const pageEventsCount = $derived(
    eventInterceptor.events.filter((e) => !isHudChrome(e)).length
  );
  const sessionId = $derived(overlayContext.currentSessionId);

  const stats = $derived([
    { label: 'picks', num: picksCount },
    { label: 'regions', num: regionsCount },
    { label: 'relations', num: relationsCount },
    { label: 'events', num: pageEventsCount },
  ]);
</script>

<div class="dashboard">
  <header class="dashboard__header">
    <div class="dashboard__brand">
      <span class="dashboard__mark" aria-hidden="true"></span>
      <h1 class="dashboard__title">frontprompt</h1>
    </div>
    <span class="dashboard__subtitle">Management Dashboard</span>
  </header>

  <div class="dashboard__stats">
    {#each stats as stat (stat.label)}
      <div class="stat">
        <span class="stat__num">{formatCount(stat.num)}</span>
        <span class="stat__label">{stat.label}</span>
      </div>
    {/each}
  </div>

  <div class="dashboard__sections">
    <DashboardSection title="Build Info">
      <DashboardRow label="schema" value={SCHEMA_VERSION} />
      <DashboardRow label="build" value={BUILD_VERSION} />
      <DashboardRow label="sha" value={BUILD_GIT_SHA} />
      <DashboardRow label="session" value={BUILD_SESSION} />
    </DashboardSection>

    <DashboardSection title="Session">
      <DashboardRow label="session id" value={sessionId} />
    </DashboardSection>

    <DashboardSection title="State">
      <div class="state-row">
        <span class="state-row__label">inspector</span>
        <span class="pill" class:pill--active={inspectorActive}>
          {inspectorActive ? 'active' : 'idle'}
        </span>
      </div>
      <p class="dashboard__note">HUD panels suppressed on about:blank</p>
    </DashboardSection>
  </div>
</div>

<style>
  .dashboard {
    display: flex;
    flex-direction: column;
    gap: 28px;
    width: 100%;
    max-width: 940px;
    padding: 8px 4px 40px;
    box-sizing: border-box;
    font-family: -apple-system, system-ui, sans-serif;
    color: var(--fp-color-text-primary);
  }

  /* ── Header ─────────────────────────────────────────────────────────── */
  .dashboard__header {
    display: flex;
    flex-direction: column;
    gap: 6px;
  }

  .dashboard__brand {
    display: flex;
    align-items: center;
    gap: 12px;
  }

  .dashboard__mark {
    width: 12px;
    height: 12px;
    border-radius: 50%;
    background: var(--fp-color-accent);
    box-shadow: 0 0 0 4px color-mix(in srgb, var(--fp-color-accent) 22%, transparent);
    flex-shrink: 0;
  }

  .dashboard__title {
    margin: 0;
    font-size: 34px;
    line-height: 1;
    font-weight: 700;
    letter-spacing: -0.02em;
    font-family: 'SF Mono', 'JetBrains Mono', Menlo, Consolas, monospace;
    color: var(--fp-color-text-primary);
  }

  .dashboard__subtitle {
    font-size: 12px;
    font-weight: 600;
    text-transform: uppercase;
    letter-spacing: 0.22em;
    color: var(--fp-color-text-muted);
    padding-left: 24px;
  }

  /* ── Hero stat band ─────────────────────────────────────────────────── */
  .dashboard__stats {
    display: grid;
    grid-template-columns: repeat(auto-fit, minmax(150px, 1fr));
    gap: 14px;
  }

  .stat {
    display: flex;
    flex-direction: column;
    gap: 6px;
    padding: 20px 22px;
    border-radius: 14px;
    background: var(--fp-color-surface-secondary);
    border: 1px solid var(--fp-color-border);
    box-shadow: 0 1px 2px rgba(0, 0, 0, 0.04), 0 8px 24px rgba(0, 0, 0, 0.06);
  }

  .stat__num {
    font-family: 'SF Mono', 'JetBrains Mono', Menlo, Consolas, monospace;
    font-size: 40px;
    line-height: 1;
    font-weight: 600;
    letter-spacing: -0.03em;
    color: var(--fp-color-accent);
    font-variant-numeric: tabular-nums;
  }

  .stat__label {
    font-size: 11px;
    font-weight: 600;
    text-transform: uppercase;
    letter-spacing: 0.12em;
    color: var(--fp-color-text-muted);
  }

  /* ── Info card grid ─────────────────────────────────────────────────── */
  .dashboard__sections {
    display: grid;
    grid-template-columns: repeat(auto-fit, minmax(280px, 1fr));
    gap: 16px;
    align-items: start;
  }

  /* ── State pill ─────────────────────────────────────────────────────── */
  .state-row {
    display: flex;
    align-items: center;
    justify-content: space-between;
    gap: 12px;
    min-height: 28px;
  }

  .state-row__label {
    font-size: 13px;
    color: var(--fp-color-text-secondary);
  }

  .pill {
    display: inline-flex;
    align-items: center;
    padding: 3px 12px;
    border-radius: 999px;
    font-family: 'SF Mono', 'JetBrains Mono', Menlo, Consolas, monospace;
    font-size: 12px;
    font-weight: 600;
    letter-spacing: 0.02em;
    color: var(--fp-color-text-secondary);
    background: var(--fp-color-hover-bg);
    border: 1px solid var(--fp-color-border);
  }

  .pill--active {
    color: var(--fp-color-accent-text);
    background: var(--fp-color-accent);
    border-color: transparent;
  }

  .dashboard__note {
    margin: 12px 0 0;
    font-size: 12px;
    line-height: 1.4;
    color: var(--fp-color-text-muted);
    font-style: italic;
  }
</style>
