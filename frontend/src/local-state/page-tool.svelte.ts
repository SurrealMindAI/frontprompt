/**
 * pageTool — derived flag "any full-viewport tool is active".
 *
 * Aktuell triggert das:
 *   - ``backendState.inspector.active`` → InspectorLayer eingeblendet
 *   - ``regionDraft.drafting`` → DrawRegionLayer eingeblendet
 *
 * Beide nehmen den ganzen viewport ein (pointer-events: auto) und kollidieren
 * visuell mit den HUD-panels. Solange irgendeines aktiv ist, retracten die
 * panels zu Laschen (Panel.svelte + PanelTab.svelte konsultieren diesen flag,
 * App.svelte gridTemplate*With(forceClosed) auch).
 *
 * Extraktion: vorher las jeder Konsument direkt
 * ``backendState.inspector.active``. Beim Hinzufügen des Region-Tools wäre
 * dieselbe condition an 4 Stellen zu erweitern — DRY-Verletzung. Stattdessen
 * lebt die OR-condition jetzt zentral hier.
 *
 * localState. Beide quellen sind selber state (inspector.active ist
 * backend-mirror, regionDraft.drafting ist UI-localState) — die *Aggregation*
 * ist pure UI-concern (panel-collapse).
 */
import { backendState } from '../backend-state/backend-state.svelte';
import { regionDraft } from '../services/regions';

class PageTool {
  /** True wenn irgendein full-viewport tool den ganzen viewport beansprucht. */
  active = $derived(backendState.inspector.active || regionDraft.drafting);
}

export const pageTool = new PageTool();
