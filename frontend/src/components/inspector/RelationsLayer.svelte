<!--
  RelationsLayer — SVG-overlay-on-page for Relations + Regions visualization.

  Sibling zu InspectorLayer im Shadow-Root. Visibility liest direkt aus
  localState.uiPrefs.relationsVisible (kein wire-call).

  Schema 0.4.0: Renderer kriegt sowohl relations (mit heterogeneous endpoints)
  als auch regions (rect-borders) durchgereicht — overlay rendert solange
  IRGENDWAS sichtbar wäre (commands ODER regions vorhanden).
-->
<script lang="ts">
  import { backendState } from '../../backend-state/backend-state.svelte';
  import { uiPrefs } from '../../local-state/ui-prefs.svelte';
  import { planPaths, positionService, positionTracker } from '../../services/relations';
  import SvgRenderer from '../../services/relations/renderer/svg-renderer.svelte';

  const inspector = backendState.inspector;
  // Relations brauchen für die heterogeneous-endpoint-resolution beide Listen
  // (positionService.centerForNode dispatcht auf pick/region) — auch wenn regions
  // nicht visuell gerendert werden, dürfen sie nicht aus dem planPaths-pool fallen.
  // ``positionTracker.tick`` als reactive dep — bei resize/scroll re-eval mit
  // frischen live-rects via querySelector + bbox.
  const commands = $derived.by(() => {
    void positionTracker.tick;
    return planPaths(inspector.relations, inspector.picks, inspector.regions, positionService);
  });
  // Was an den renderer geht: regions nur wenn uiPrefs.regionsVisible.
  const visibleRegions = $derived(uiPrefs.regionsVisible ? inspector.regions : []);
  // Renderer mounten wenn IRGENDWAS sichtbar wäre — picks, regions, oder relations.
  const hasContent = $derived(
    (uiPrefs.relationsVisible && commands.length > 0) ||
      (uiPrefs.regionsVisible && inspector.regions.length > 0) ||
      (uiPrefs.picksVisible && inspector.picks.length > 0)
  );
</script>

{#if hasContent}
  <SvgRenderer
    commands={uiPrefs.relationsVisible ? commands : []}
    hoveredRelationId={uiPrefs.hoveredRelationId}
    picks={inspector.picks}
    regions={visibleRegions}
    activePickId={inspector.activePickId}
    activeRegionId={inspector.activeRegionId}
    showPicks={uiPrefs.picksVisible}
  />
{/if}
