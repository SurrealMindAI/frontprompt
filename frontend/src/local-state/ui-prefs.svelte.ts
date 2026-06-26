/**
 * UI preferences — ephemerale UI-only state, lebt im local-state-bereich.
 *
 * NICHT backendState (das wäre Python-authoritative). Reine
 * UI-prefs wie "welcher tab ist aktiv im left panel" oder "rendere ich gerade
 * den relations-overlay" bleiben lokal — gehen mit cross-origin-nav verloren,
 * was OK ist (visual sugar ist ephemeral by design).
 *
 * Phase 1 scope: leftPanelTab + relationsVisible + hoveredRelationId.
 * Phase 2 additions:
 *   - activeDetailReplayId: which ReplayReport is expanded in RecordingDetails (recorder-replay sub-plan 06)
 * Kandidaten für spätere Phase:
 *   - filter-states (eventsTab type-filter, picks-search)
 *   - dark/light theme
 *   - debug-panel collapsed-state
 *   - relationsVisible nach localStorage (survives reload, bleibt frontend)
 */

export type LeftPanelTabId = 'picks' | 'events' | 'relations' | 'regions' | 'recordings';

class UiPrefs {
  /** Welcher tab im left panel ist aktuell selected. */
  leftPanelTab = $state<LeftPanelTabId>('picks');

  /**
   * Sichtbarkeit des SVG-Relations-Overlay-Layers über der Page. Pure visual sugar.
   * Default true: wenn keine relations existieren rendert der Layer eh nichts,
   * also kein Visual-Noise. Sobald welche existieren sieht sie der User sofort.
   */
  relationsVisible = $state(true);

  /**
   * Sichtbarkeit der Region-rect-borders im SVG-overlay. Analog zu relationsVisible,
   * aber unabhängig — User will manchmal nur Regions sehen ohne Relation-Lines
   * (oder umgekehrt).
   */
  regionsVisible = $state(true);

  /**
   * Sichtbarkeit der Pick-rect-borders im SVG-overlay. Vorher gekoppelt an
   * "es gibt mindestens 1 relation" — entkoppelt weil picks ein
   * eigenes erstklassiges visual-konzept sind, unabhängig von relations.
   */
  picksVisible = $state(true);

  /**
   * Welche Relation wird grade gehovered (in RelationsTab-Liste oder PickDetails)
   * — der RelationsLayer hebt diese Edge visuell hervor (opacity-boost / thicker stroke).
   * null wenn nichts gehovered.
   */
  hoveredRelationId = $state<string | null>(null);

  /**
   * Welcher ReplayReport ist im RecordingDetails-Panel expandiert?
   * localState (ADR-018: ephemeral UI-Selektion, nicht backendState).
   * null wenn kein Report expanded ist.
   */
  activeDetailReplayId = $state<string | null>(null);

  /** Imperative helper: open events-tab. Used vom Toolbar-status-click. */
  showEventsTab(): void {
    this.leftPanelTab = 'events';
  }

  /** Imperative helper: open picks-tab. */
  showPicksTab(): void {
    this.leftPanelTab = 'picks';
  }

  /** Imperative helper: open relations-tab. */
  showRelationsTab(): void {
    this.leftPanelTab = 'relations';
  }

  /** Imperative helper: open regions-tab (Schema 0.4.0). */
  showRegionsTab(): void {
    this.leftPanelTab = 'regions';
  }

  /** Imperative helper: open recordings-tab (recorder feature). */
  showRecordingsTab(): void {
    this.leftPanelTab = 'recordings';
  }

  /** Toggle relations-overlay visibility. Bound to Toolbar-button. */
  toggleRelationsVisible(): void {
    this.relationsVisible = !this.relationsVisible;
  }

  /** Toggle regions-overlay visibility. Bound to Toolbar-button. */
  toggleRegionsVisible(): void {
    this.regionsVisible = !this.regionsVisible;
  }

  /** Toggle picks-overlay visibility (rect-borders). Bound to Toolbar-button. */
  togglePicksVisible(): void {
    this.picksVisible = !this.picksVisible;
  }

  /**
   * Set/clear hover-highlight für eine Relation. Wird von Mouseenter/leave-handlers
   * in RelationItem + PickDetails-Relation-rows aufgerufen.
   */
  hoverRelation(id: string | null): void {
    this.hoveredRelationId = id;
  }

  /**
   * Select/deselect which ReplayReport is expanded in the RecordingDetails panel.
   * null = collapse all; replay_id = expand that report.
   */
  showDetailReplay(replayId: string | null): void {
    this.activeDetailReplayId = replayId;
  }
}

export const uiPrefs = new UiPrefs();
