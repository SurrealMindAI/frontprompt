/**
 * VoiceOverState hydration smoke tests (sub-plan 02).
 *
 * Verifies that the voice-over mirror hydrates correctly from StateSnapshot
 * recordings_state fields. Follows the inspector-state.svelte.test.ts pattern.
 */
import { describe, expect, test } from 'vitest';

import { VoiceOverState } from './voice-over-state.svelte';

describe('VoiceOverState hydration', () => {
  test('initial state: no recordings, no transcription activity', () => {
    const state = new VoiceOverState();
    expect(state.voiceOverRecordings).toEqual([]);
    expect(state.transcribingRecordingIds).toEqual([]);
  });

  test('hydrate with recordings_state — filters recordings with voice-over', () => {
    const state = new VoiceOverState();
    state.hydrate({
      recordings: [
        {
          recording_id: 'rec-1',
          name: 'Voice Recording',
          status: 'stopped',
          started_at_ms: 1000,
          entry_count: 5,
          has_voice_over: true,
          transcription_status: 'done',
        },
        {
          recording_id: 'rec-2',
          name: 'Normal Recording',
          status: 'stopped',
          started_at_ms: 2000,
          entry_count: 3,
          has_voice_over: false,
          transcription_status: 'none',
        },
      ],
    });
    expect(state.voiceOverRecordings).toHaveLength(1);
    expect(state.voiceOverRecordings[0]!.recording_id).toBe('rec-1');
  });

  test('hydrate with recordings_state — transcribingRecordingIds includes transcribing status', () => {
    const state = new VoiceOverState();
    state.hydrate({
      recordings: [
        {
          recording_id: 'rec-1',
          name: 'Transcribing',
          status: 'active',
          started_at_ms: 1000,
          entry_count: 0,
          has_voice_over: true,
          transcription_status: 'transcribing',
        },
        {
          recording_id: 'rec-2',
          name: 'Done',
          status: 'stopped',
          started_at_ms: 2000,
          entry_count: 10,
          has_voice_over: true,
          transcription_status: 'done',
        },
      ],
    });
    expect(state.transcribingRecordingIds).toEqual(['rec-1']);
  });

  test('hydrate with empty recordings_state — clears all derived state', () => {
    const state = new VoiceOverState();
    state.hydrate({
      recordings: [
        {
          recording_id: 'rec-1',
          name: 'Voice',
          status: 'stopped',
          started_at_ms: 1000,
          entry_count: 0,
          has_voice_over: true,
          transcription_status: 'done',
        },
      ],
    });
    // Now hydrate with empty list
    state.hydrate({ recordings: [] });
    expect(state.voiceOverRecordings).toEqual([]);
    expect(state.transcribingRecordingIds).toEqual([]);
  });

  test('hydrate with undefined recordings_state fields is tolerant (missing fields)', () => {
    const state = new VoiceOverState();
    // Should not throw when recordings is missing
    state.hydrate({});
    expect(state.voiceOverRecordings).toEqual([]);
  });
});

describe('VoiceOverState transcription backend hydration (Schema 0.11.0)', () => {
  test('initial state: no backends', () => {
    const state = new VoiceOverState();
    expect(state.backends).toEqual([]);
  });

  test('hydrateTranscription populates backends with available_models + selected_model_id', () => {
    const state = new VoiceOverState();
    state.hydrateTranscription({
      backends: [
        {
          backend_id: 'mlx_whisper',
          display_name: 'mlx-whisper (Apple Silicon)',
          status: 'ready',
          available_models: [
            {
              model_id: 'whisper-base-mlx',
              display_name: 'Whisper Base',
              hf_repo_id: 'mlx-community/whisper-base-mlx',
              default: true,
            },
            {
              model_id: 'whisper-large-v3-turbo',
              display_name: 'Whisper Large V3 Turbo',
              hf_repo_id: 'mlx-community/whisper-large-v3-turbo',
              default: false,
            },
          ],
          selected_model_id: 'whisper-large-v3-turbo',
        },
      ],
    });
    expect(state.backends).toHaveLength(1);
    expect(state.availableModelsFor('mlx_whisper')).toHaveLength(2);
    expect(state.selectedModelIdFor('mlx_whisper')).toBe('whisper-large-v3-turbo');
  });

  test('availableModelsFor returns [] for unknown backend', () => {
    const state = new VoiceOverState();
    expect(state.availableModelsFor('unknown_backend')).toEqual([]);
  });

  test('selectedModelIdFor returns null for unknown backend', () => {
    const state = new VoiceOverState();
    expect(state.selectedModelIdFor('unknown_backend')).toBeNull();
  });

  test('availableModelsFor returns [] when backend has no available_models (older snapshots)', () => {
    const state = new VoiceOverState();
    state.hydrateTranscription({
      backends: [
        {
          backend_id: 'mlx_whisper',
          display_name: 'mlx-whisper (Apple Silicon)',
          status: 'ready',
        },
      ],
    });
    expect(state.availableModelsFor('mlx_whisper')).toEqual([]);
    expect(state.selectedModelIdFor('mlx_whisper')).toBeNull();
  });
});
