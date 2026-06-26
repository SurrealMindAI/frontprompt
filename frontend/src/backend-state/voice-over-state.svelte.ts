/**
 * VoiceOverState — overlay-mirror für voice-over-relevante Felder aus recordings_state
 * und transcription_state.
 *
 * backendState category: Python's StateManager ist single-writer.
 * Overlay hält reactive mirror — voice-over-spezifische Aggregationen über
 * RecordingMeta-Einträge und Transcription-Backend-Status. Intents
 * (RecordingStartRequested mit with_voice_over=true) werden über
 * recording-state.svelte.ts gesendet (dort ist der intent-SSoT).
 *
 * Lifecycle:
 *   1. Python broadcastet StateSnapshotMessage mit recordings_state
 *      → hydrate(recordings_state) aggregiert voice-over-Felder
 *   2. voiceOverRecordings: alle RecordingMeta mit has_voice_over=true
 *   3. transcribingRecordingIds: alle recording_ids mit transcription_status='transcribing'
 *   4. Python broadcastet StateSnapshotMessage mit transcription_state
 *      → hydrateTranscription(transcription_state) aktualisiert Backend-Liste
 *   5. backends: alle registrierten TranscriptionBackendInfo (für SettingsTab)
 *
 * ADR-018: kein localState hier — alle Felder sind mirror von backendState.
 * PIT-037: kein duplicate $state parallel zu einem mirror.
 */
import type {
  RecordingMeta,
  RecordingsState,
  TranscriptionBackendInfo,
  TranscriptionState,
} from '../_generated/state';

export class VoiceOverState {
  /** Mirror: Alle Recordings mit Voice-Over (has_voice_over=true). */
  voiceOverRecordings = $state<RecordingMeta[]>([]);

  /** Mirror: recording_ids deren Transkription gerade läuft (transcription_status='transcribing'). */
  transcribingRecordingIds = $state<string[]>([]);

  /** Mirror: Alle registrierten Transcription-Backends mit ihrem Status (aus transcription_state). */
  backends = $state<TranscriptionBackendInfo[]>([]);

  /**
   * Hydrate mirror from authoritative backend snapshot recordings_state field.
   * Called by backend-state/sync — ausschließlich via backendState.hydrate().
   *
   * Tolerant gegen fehlende Felder (forward-compat mit älteren Snapshots).
   * PIT-037: mirror ist SSoT — kein paralleler lokaler state.
   */
  hydrate(view: Partial<RecordingsState>): void {
    const recordings = view.recordings ?? [];
    this.voiceOverRecordings = recordings.filter((r) => r.has_voice_over === true);
    this.transcribingRecordingIds = recordings
      .filter((r) => r.transcription_status === 'transcribing')
      .map((r) => r.recording_id);
  }

  /**
   * Hydrate transcription backend list from authoritative backend snapshot transcription_state.
   * Called by backend-state/sync after every StateSnapshotMessage.
   *
   * Tolerant gegen fehlende Felder (forward-compat mit älteren Snapshots).
   */
  hydrateTranscription(view: Partial<TranscriptionState>): void {
    if (view.backends !== undefined) this.backends = view.backends ?? [];
  }
}
