/**
 * Recorder — localState state machine für das Recorder-Tool.
 *
 * localState category (ADR-018): diese Instanz hält ausschliesslich
 * UI-Koordinierungs-state der im Page-Unload stirbt:
 *   - floatingToolbarPosition — ephemere Drag-Position (nicht backend-worthy)
 *   - activeDragHandle — Pointer-ID während Toolbar-Drag
 *
 * Was NICHT hier lebt:
 *   - active_recording_id / recordings / detail_recording — Python SSoT,
 *     mirror in backendState.recordings (recording-state.svelte.ts)
 *
 * PIT-037: ``isActive`` ist $derived von backendState.recordings.activeRecordingId
 * (Python SSoT) — KEIN duplicate $state hier. Mutations gehen ausschliesslich
 * via start()/stop() → backendState.recordings-Intents → bridge → Python.
 *
 * window.__fp: diese Datei erzeugt KEINE Globals mit Unterstrich-Suffix (z.B.
 * ``window.__fp.recorderState`` ist OK, neue top-level globals sind verboten).
 * Arch-test: src/__arch__/window-fp-namespace.test.ts.
 */

import { backendState } from '../backend-state/backend-state.svelte';

class Recorder {
  /**
   * Floating-Toolbar-Position: lokaler Drag-State (ADR-018: ephemere UI-Position,
   * keine backend-Persistenz). Default: linke Panel-Nähe, unterhalb des Tools-Strip.
   */
  floatingToolbarPosition = $state({ x: 16, y: 120 });

  /**
   * Aktiver Drag-Handle während die Toolbar gezogen wird (Pointer-ID-String oder
   * null = kein Drag aktiv). Gesetzt von FloatingRecorderToolbar bei pointerdown,
   * gelöscht bei pointerup/pointercancel.
   */
  activeDragHandle = $state<string | null>(null);

  /**
   * Ob gerade aufgenommen wird.
   *
   * PIT-037: Kein duplicate $state — rein $derived von Python-SSoT-Mirror.
   * Mutations nur über start()/stop(), niemals direktes Setzen.
   */
  isActive = $derived(backendState.recordings.activeRecordingId !== null);

  /**
   * Starte eine neue Aufnahme.
   * Delegiert an backendState.recordings.startRecording() → bridge.send().
   * Python weist recording_id zu + broadcastet snapshot → isActive wechselt zu true.
   */
  start(name: string = 'New Recording', description: string = ''): void {
    backendState.recordings.startRecording(name, description);
  }

  /**
   * Stoppe die aktive Aufnahme.
   * Delegiert an backendState.recordings.stopRecording() → bridge.send().
   * No-op wenn keine aktive Aufnahme.
   */
  stop(): void {
    backendState.recordings.stopRecording();
  }

  /**
   * Aktualisiere die Toolbar-Position nach einem Drag-Schritt.
   * Pure localState-Mutation — kein bridge-Roundtrip.
   */
  moveToolbar(pos: { x: number; y: number }): void {
    this.floatingToolbarPosition = pos;
  }
}

/** Module-Singleton. */
export const recorder = new Recorder();
