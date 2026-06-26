/**
 * backendState — Umbrella-Singleton für alle backend-mirror state stores.
 *
 * backendState category: Sub-stores spiegeln Python's authoritative
 * state, sync via :file:`./sync.svelte.ts`, mutations via wire-message intents.
 *
 * Sub-stores hier registrieren wenn neue backend-state kategorie hinzugefügt
 * wird (Phase 2+: picks, annotations, preferences).
 *
 * ``hydrate(snap)`` ist der EINZIGE entry-point für state-application — egal
 * ob pre-mount (main.ts) oder live-update (sync.svelte.ts). Skaliert auf N
 * sub-stores via single dispatch-line pro store.
 *
 * Voice-Over-Stores (Schema 0.10.0):
 * - ``voiceOver`` — mirror für recordings_state voice-over Aggregationen
 * - ``mic`` — mirror für microphone_state (device-Enumeration + Selection)
 * - ``settings`` — mirror für settings_state (User-Prefs + Backend-Selection)
 */

import type { StateSnapshot } from '../_generated/state';
import { InspectorState } from './inspector-state.svelte';
import { PanelState } from './panel-state.svelte';
import { RecordingState } from './recording-state.svelte';
import { VoiceOverState } from './voice-over-state.svelte';
import { MicState } from './mic-state.svelte';
import { SettingsState } from './settings-state.svelte';

class BackendState {
  panel = new PanelState();
  inspector = new InspectorState();
  recordings = new RecordingState();
  voiceOver = new VoiceOverState();
  mic = new MicState();
  settings = new SettingsState();
  // future: annotations = new AnnotationState();

  /**
   * Apply authoritative state snapshot from python.
   * Dispatcht zu sub-stores per snapshot-field. Tolerant gegen missing fields
   * (pre-2.x snapshot-versions hatten weniger felder).
   */
  hydrate(snap: StateSnapshot): void {
    if (snap.panel_state) this.panel.hydrate(snap.panel_state);
    if (snap.inspector_state) this.inspector.hydrate(snap.inspector_state);
    if (snap.recordings_state) this.recordings.hydrate(snap.recordings_state);
    // Voice-Over: voiceOverState liest aus recordings_state (has_voice_over + transcription_status)
    if (snap.recordings_state) this.voiceOver.hydrate(snap.recordings_state);
    if (snap.microphone_state) this.mic.hydrate(snap.microphone_state);
    if (snap.settings_state) this.settings.hydrate(snap.settings_state);
    // future: if (snap.annotations) this.annotations.hydrate(snap.annotations);
  }
}

export const backendState = new BackendState();
