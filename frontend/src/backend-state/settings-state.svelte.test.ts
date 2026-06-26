/**
 * SettingsState hydration smoke tests (sub-plan 02).
 *
 * Verifies that the settings state mirror hydrates correctly from StateSnapshot
 * settings_state field.
 */
import { describe, expect, test } from 'vitest';

import { SettingsState } from './settings-state.svelte';

describe('SettingsState hydration', () => {
  test('initial state: voice-over disabled, no selected backend', () => {
    const state = new SettingsState();
    expect(state.voiceOverEnabled).toBe(false);
    expect(state.selectedTranscriptionBackendId).toBeNull();
  });

  test('hydrate with voice_over_enabled=true', () => {
    const state = new SettingsState();
    state.hydrate({ voice_over_enabled: true, selected_transcription_backend_id: null });
    expect(state.voiceOverEnabled).toBe(true);
    expect(state.selectedTranscriptionBackendId).toBeNull();
  });

  test('hydrate with selected_transcription_backend_id set', () => {
    const state = new SettingsState();
    state.hydrate({
      voice_over_enabled: true,
      selected_transcription_backend_id: 'mlx_whisper',
    });
    expect(state.voiceOverEnabled).toBe(true);
    expect(state.selectedTranscriptionBackendId).toBe('mlx_whisper');
  });

  test('hydrate with selected_transcription_backend_id=null means auto', () => {
    const state = new SettingsState();
    state.hydrate({
      voice_over_enabled: false,
      selected_transcription_backend_id: null,
    });
    expect(state.selectedTranscriptionBackendId).toBeNull();
  });

  test('hydrate updates existing state', () => {
    const state = new SettingsState();
    state.hydrate({ voice_over_enabled: true, selected_transcription_backend_id: 'mlx_whisper' });
    // Update to disable voice-over and clear backend
    state.hydrate({ voice_over_enabled: false, selected_transcription_backend_id: null });
    expect(state.voiceOverEnabled).toBe(false);
    expect(state.selectedTranscriptionBackendId).toBeNull();
  });

  test('hydrate with undefined fields is tolerant (missing fields from older snapshots)', () => {
    const state = new SettingsState();
    // Should not throw when settings_state fields are missing
    state.hydrate({});
    expect(state.voiceOverEnabled).toBe(false);
    expect(state.selectedTranscriptionBackendId).toBeNull();
  });
});
