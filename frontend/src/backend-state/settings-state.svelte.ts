/**
 * SettingsState — overlay-mirror für backend-authoritative settings_state.
 *
 * backendState category: Python's StateManager ist single-writer.
 * Overlay hält reactive mirror. Intents (SetTranscriptionBackendRequested,
 * TriggerModelDownloadRequested, SetTranscriptionModelRequested) werden via
 * bridge.send gesendet — Settings-Tab importiert diese Klasse für state-lesen
 * und sendet Intents selbst.
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
import { bridge } from '../bridge/bridge.svelte';
import { SCHEMA_VERSION } from '../schema-version';

export class SettingsState {
  /** Mirror: Voice-Over-Feature aktiviert (User-Opt-In). */
  voiceOverEnabled = $state<boolean>(false);

  /** Mirror: Gewähltes Transkriptions-Backend (null = Auto — erstes 'ready'-Backend). */
  selectedTranscriptionBackendId = $state<string | null>(null);

  /**
   * Mirror: Gewähltes Transkriptions-Modell für das mlx_whisper-Backend
   * (null = Default-Modell aus Katalog). Schema 0.11.0+.
   */
  mlxWhisperModelId = $state<string | null>(null);

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
    if (view.mlx_whisper_model_id !== undefined)
      this.mlxWhisperModelId = view.mlx_whisper_model_id ?? null;
  }

  /**
   * Intent: User wählte ein Transkriptions-Modell für ein Backend.
   * Sendet SetTranscriptionModelRequested über die Bridge.
   * model_id=null = Default-Modell aus Katalog verwenden.
   *
   * Nur für mlx_whisper implementiert (Schema 0.11.0). backend_id muss mit
   * einem registrierten Backend-ID übereinstimmen.
   */
  async setTranscriptionModel(backendId: string, modelId: string | null): Promise<void> {
    await bridge.send({
      kind: 'set_transcription_model_requested',
      schema_version: SCHEMA_VERSION,
      backend_id: backendId,
      model_id: modelId,
    });
  }
}
