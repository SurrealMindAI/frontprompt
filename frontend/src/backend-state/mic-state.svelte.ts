/**
 * MicState — overlay-mirror für backend-authoritative microphone_state.
 *
 * backendState category: Python's StateManager ist single-writer.
 * Overlay hält reactive mirror. Intents (SetMicDeviceRequested) werden via
 * bridge.send gesendet — Settings-Tab importiert diese Klasse für state-lesen
 * und sendet Intents selbst.
 *
 * Lifecycle:
 *   1. Mic-Watcher-Task (Python-Backend) enumeriert sounddevice-Geräte
 *      → topology-hash-Änderung → StateManager.update_microphone_state() → broadcast
 *   2. hydrate(microphone_state) aktualisiert devices + selected/system-default
 *
 * ADR-018: kein localState hier — alle Felder sind mirror von backendState.
 * PIT-037: kein duplicate $state parallel zu einem mirror.
 */
import type { MicrophoneDevice, MicrophoneState } from '../_generated/state';

export class MicState {
  /** Mirror: Alle verfügbaren Eingangsgeräte (leer bis erster Watcher-Cycle). */
  devices = $state<MicrophoneDevice[]>([]);

  /** Mirror: User-gewähltes Gerät (None = System-Default). Durable. */
  selectedDeviceId = $state<number | null>(null);

  /** Mirror: Aktuelles System-Default-Gerät von sounddevice. Nicht durable. */
  systemDefaultDeviceId = $state<number | null>(null);

  /**
   * Hydrate mirror from authoritative backend snapshot microphone_state field.
   * Called by backend-state/sync — ausschließlich via backendState.hydrate().
   *
   * Tolerant gegen fehlende Felder (forward-compat mit älteren Snapshots).
   */
  hydrate(view: Partial<MicrophoneState>): void {
    if (view.devices !== undefined) this.devices = view.devices;
    if (view.selected_device_id !== undefined) this.selectedDeviceId = view.selected_device_id ?? null;
    if (view.system_default_device_id !== undefined)
      this.systemDefaultDeviceId = view.system_default_device_id ?? null;
  }
}
