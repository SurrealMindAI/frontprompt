/**
 * SettingsState hydration smoke tests (sub-plan 02).
 *
 * Verifies that the settings state mirror hydrates correctly from StateSnapshot
 * settings_state field. Covers new mlxWhisperModelId field (Schema 0.11.0).
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

describe('SettingsState mlxWhisperModelId hydration (Schema 0.11.0)', () => {
  test('initial state: mlxWhisperModelId is null', () => {
    const state = new SettingsState();
    expect(state.mlxWhisperModelId).toBeNull();
  });

  test('hydrate with mlx_whisper_model_id set', () => {
    const state = new SettingsState();
    state.hydrate({ mlx_whisper_model_id: 'whisper-large-v3-turbo' });
    expect(state.mlxWhisperModelId).toBe('whisper-large-v3-turbo');
  });

  test('hydrate with mlx_whisper_model_id=null means default model', () => {
    const state = new SettingsState();
    state.hydrate({ mlx_whisper_model_id: 'whisper-large-v3-turbo' });
    state.hydrate({ mlx_whisper_model_id: null });
    expect(state.mlxWhisperModelId).toBeNull();
  });

  test('hydrate without mlx_whisper_model_id is tolerant (older snapshots)', () => {
    const state = new SettingsState();
    state.hydrate({ voice_over_enabled: true });
    expect(state.mlxWhisperModelId).toBeNull();
  });
});
