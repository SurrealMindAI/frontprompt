<!--
  LeftPanel — Composition root für das linke Panel.

  Layout: 2-Zeilen-Grid intern.
    [Tools-Strip] (fixe Höhe, ~40px)
    [TabbedPanel] (flex-rest)

  Tab-active-state via uiPrefs.leftPanelTab — erlaubt external triggers
  (z.B. Toolbar-status-click jumpt zum events tab).
-->

<script lang="ts">
  import { backendState } from '../../backend-state/backend-state.svelte';
  import { overlayContext } from '../../services/context/overlay-context.svelte';
  import { uiPrefs } from '../../local-state/ui-prefs.svelte';
  import { visibleCount } from '../../services/visibility/visible-groups';
  import { pickDomain, regionDomain, relationDomain } from '../../services/visibility/hostname';
  import TabbedPanel from '../primitives/TabbedPanel.svelte';
  import LeftPanelTools from './LeftPanelTools.svelte';
  import EventsTab from './tabs/EventsTab.svelte';
  import PicksTab from './tabs/PicksTab.svelte';
  import RecordingsTab from './tabs/RecordingsTab.svelte';
  import RegionsTab from './tabs/RegionsTab.svelte';
  import RelationsTab from './tabs/RelationsTab.svelte';

  // Maps needed for region/relation domain resolution — same pattern as the tabs.
  const picksById = $derived(new Map(backendState.inspector.picks.map((p) => [p.pick_id, p])));
  const regionsById = $derived(
    new Map(backendState.inspector.regions.map((r) => [r.region_id, r]))
  );
  const currentHostname = $derived(overlayContext.hostname() ?? '');
  const currentSessionId = $derived(overlayContext.currentSessionId);

  // Recordings count + active indicator for the Recordings tab label.
  const recordingsCount = $derived(backendState.recordings.recordings.length);
  const hasActiveRecording = $derived(backendState.recordings.activeRecordingId !== null);

  // Tab-labels with visible counts — must reflect what each tab actually renders
  // (domain-scoped: own = all, foreign = current-hostname only).
  const tabs = $derived([
    {
      id: 'picks' as const,
      label: `Picks (${visibleCount(backendState.inspector.picks, {
        currentSessionId,
        currentHostname,
        domainOf: (p) => pickDomain(p),
      })})`,
    },
    {
      id: 'regions' as const,
      label: `Regions (${visibleCount(backendState.inspector.regions, {
        currentSessionId,
        currentHostname,
        domainOf: (r) => regionDomain(r, picksById),
      })})`,
    },
    {
      id: 'relations' as const,
      label: `Relations (${visibleCount(backendState.inspector.relations, {
        currentSessionId,
        currentHostname,
        domainOf: (rel) => relationDomain(rel, picksById, regionsById),
      })})`,
    },
    { id: 'events' as const, label: 'Events' },
    {
      id: 'recordings' as const,
      label: recordingsCount > 0
        ? `Recordings (${recordingsCount})${hasActiveRecording ? ' ●' : ''}`
        : `Recordings${hasActiveRecording ? ' ●' : ''}`,
    },
  ]);
</script>

<div class="left-panel">
  <LeftPanelTools />
  <div class="tabbed">
    <TabbedPanel
      {tabs}
      activeId={uiPrefs.leftPanelTab}
      onActiveIdChange={(id) => {
        uiPrefs.leftPanelTab = id as typeof uiPrefs.leftPanelTab;
      }}
    >
      {#snippet content(activeId)}
        {#if activeId === 'picks'}
          <PicksTab />
        {:else if activeId === 'regions'}
          <RegionsTab />
        {:else if activeId === 'relations'}
          <RelationsTab />
        {:else if activeId === 'events'}
          <EventsTab />
        {:else if activeId === 'recordings'}
          <RecordingsTab />
        {/if}
      {/snippet}
    </TabbedPanel>
  </div>
</div>

<style>
  .left-panel {
    display: flex;
    flex-direction: column;
    width: 100%;
    height: 100%;
    min-height: 0;
  }

  .tabbed {
    flex: 1 1 auto;
    min-height: 0;
    display: flex;
  }
</style>
