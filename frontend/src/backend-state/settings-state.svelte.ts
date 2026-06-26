/**
 * SettingsState — overlay-mirror für backend-authoritative settings_state.
 *
 * backendState category: Python's StateManager ist single-writer.
 * Overlay hält reactive mirror. Intents (SetTranscriptionBackendRequested,
 * TriggerModelDownloadRequested) werden via bridge.send gesendet — Settings-Tab
 * importiert diese Klasse für state-lesen und sendet Intents selbst.
 *
 * Lifecycle:
 *   1. User wählt Einstellung in Settings-Tab → Intent via bridge
 *   2. Python persistiert + broadcastet snapshot mit settings_state
 *   3. hydrate(settings_state) aktualisiert mirror
 *
 * ADR-018: kein localState hier — alle Felder sind mirror von backendState.
 * PIT-037: kein duplicate $state parallel zu einem mirror.
 */
import type { SettingsState as SettingsView } from '../_generated/state';

export class SettingsState {
  /** Mirror: Voice-Over-Feature aktiviert (User-Opt-In). */
  voiceOverEnabled = $state<boolean>(false);

  /** Mirror: Gewähltes Transkriptions-Backend (null = Auto — erstes 'ready'-Backend). */
  selectedTranscriptionBackendId = $state<string | null>(null);

  /**
   * Hydrate mirror from authoritative backend snapshot settings_state field.
   * Called by backend-state/sync — ausschließlich via backendState.hydrate().
   *
   * Tolerant gegen fehlende Felder (forward-compat mit älteren Snapshots).
   */
  hydrate(view: Partial<SettingsView>): void {
    if (view.voice_over_enabled !== undefined) this.voiceOverEnabled = view.voice_over_enabled;
    if (view.selected_transcription_backend_id !== undefined)
      this.selectedTranscriptionBackendId = view.selected_transcription_backend_id ?? null;
  }
}
