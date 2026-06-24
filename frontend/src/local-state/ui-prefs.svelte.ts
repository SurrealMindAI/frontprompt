/**
 * UI preferences — ephemerale UI-only state, lebt im local-state-bereich.
 *
 * NICHT backendState (das wäre Python-authoritative). Reine
 * UI-prefs wie "welcher tab ist aktiv im left panel" oder "rendere ich gerade
 * den relations-overlay" bleiben lokal — gehen mit cross-origin-nav verloren,
 * was OK ist (visual sugar ist ephemeral by design).
 *
 * Phase 1 scope: leftPanelTab + relationsVisible + hoveredRelationId.
 * Kandidaten für Phase 2:
 *   - filter-states (eventsTab type-filter, picks-search)
 *   - dark/light theme
 *   - debug-panel collapsed-state
 *   - relationsVisible nach localStorage (survives reload, bleibt frontend)
 */

export type LeftPanelTabId = 'picks' | 'events' | 'relations' | 'regions';

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
}

export const uiPrefs = new UiPrefs();
