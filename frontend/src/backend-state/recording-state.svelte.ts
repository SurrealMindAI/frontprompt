/**
 * RecordingState — overlay-mirror für backend-authoritative recordings-state.
 *
 * backendState category: Python's StateManager ist single-writer.
 * Overlay hält reactive mirror + sendet user-intents als
 * ``*Requested`` wire-messages outbound.
 *
 * Lifecycle:
 *   1. User clickt "Start Recording" im RecordingsTab
 *      → startRecording() sends recording_start_requested
 *      → Python mutiert + broadcastet snapshot
 *      → activeRecordingId wechselt zur neuen Recording-ID
 *   2. User clickt "Stop Recording"
 *      → stopRecording() sends recording_stop_requested
 *      → Python setzt status=stopped + broadcastet snapshot
 *      → activeRecordingId wird None
 *   3. User clickt eine Recording in der Liste
 *      → selectRecording() sends recording_selected_requested
 *      → Python setzt active_detail_recording_id + lädt detail_recording
 *   4. User umbenennt eine Recording
 *      → renameRecording() sends recording_rename_requested
 */
import { bridge } from '../bridge/bridge.svelte';
import type { Recording, RecordingMeta, RecordingsState } from '../_generated/state';

const SCHEMA_VERSION = '0.8.0';

export class RecordingState {
  /** Mirror: ID der laufenden Aufnahme, null = nicht aufnehmend. */
  activeRecordingId = $state<string | null>(null);

  /** Mirror: Lightweight-Zusammenfassungen aller Aufnahmen. */
  recordings = $state<RecordingMeta[]>([]);

  /** Mirror: ID der im detail-Panel angezeigten Aufnahme (oder null = keine). */
  activeDetailRecordingId = $state<string | null>(null);

  /** Mirror: Vollständige Aufnahme mit Timeline (nur wenn activeDetailRecordingId gesetzt). */
  detailRecording = $state<Recording | null>(null);

  /** Convenience: ob gerade aufgenommen wird. */
  isRecording = $derived(this.activeRecordingId !== null);

  /** Convenience: die gerade aktive Aufnahme-Meta (oder null). */
  activeRecording = $derived(
    this.recordings.find((r) => r.recording_id === this.activeRecordingId) ?? null
  );

  /**
   * Hydrate mirror from authoritative backend snapshot.
   * Called by backend-state/sync.svelte.ts auf jedem StateSnapshot-receive.
   *
   * PIT-037: kein duplicate local $state — mirror ist der SSoT, kein
   * paralleler lokaler state.
   */
  hydrate(view: RecordingsState): void {
    if (view.active_recording_id !== undefined) this.activeRecordingId = view.active_recording_id;
    if (view.recordings !== undefined) this.recordings = view.recordings;
    if (view.active_detail_recording_id !== undefined)
      this.activeDetailRecordingId = view.active_detail_recording_id;
    if (view.detail_recording !== undefined) this.detailRecording = view.detail_recording;
  }

  // ----- Intents (bridge-send) -----------------------------------------------

  /**
   * User clickt "Start Recording" — neue Aufnahme beginnen.
   * Python weist recording_id zu + broadcastet snapshot.
   */
  startRecording(name: string = 'New Recording', description: string = ''): void {
    void bridge.send({
      kind: 'recording_start_requested',
      schema_version: SCHEMA_VERSION,
      name,
      description,
    });
  }

  /**
   * User clickt "Stop Recording" — aktive Aufnahme beenden.
   * Sendet recording_stop_requested mit der aktuell aktiven recording_id.
   * No-op wenn keine aktive Aufnahme.
   */
  stopRecording(): void {
    if (this.activeRecordingId === null) return;
    void bridge.send({
      kind: 'recording_stop_requested',
      schema_version: SCHEMA_VERSION,
      recording_id: this.activeRecordingId,
    });
  }

  /**
   * User speichert neuen Namen/Beschreibung — Metadaten patchen.
   * Beide Felder reisen immer mit (kein partial-update-race).
   */
  renameRecording(id: string, name: string, description: string): void {
    void bridge.send({
      kind: 'recording_rename_requested',
      schema_version: SCHEMA_VERSION,
      recording_id: id,
      name,
      description,
    });
  }

  /**
   * User clickt eine Recording in der Liste — Detail-Ansicht öffnen.
   * id=null deselektiert (schliesst Detail-Panel).
   */
  selectRecording(id: string | null): void {
    void bridge.send({
      kind: 'recording_selected_requested',
      schema_version: SCHEMA_VERSION,
      recording_id: id,
    });
  }
}
