/**
 * BackendState aggregator — hydrate dispatcher tests.
 *
 * Covers the hydrate() dispatch to sub-stores and forward-compat
 * tolerance for missing snapshot fields.
 */
const send = vi.hoisted(() => vi.fn());
vi.mock('../bridge/bridge.svelte', () => ({ bridge: { send } }));

import { describe, expect, test } from 'vitest';
import { backendState } from './backend-state.svelte';

describe('BackendState.hydrate — dispatch to sub-stores', () => {
  test('hydrate dispatches panel_state to panel sub-store', () => {
    backendState.hydrate({
      panel_state: {
        top: { open: false, size: 28 },
        bottom: { open: true, size: 220 },
        left: { open: true, size: 300 },
        right: { open: true, size: 340 },
      },
    } as never);
    expect(backendState.panel.panels.top.open).toBe(false);
  });

  test('hydrate dispatches inspector_state to inspector sub-store', () => {
    backendState.hydrate({
      inspector_state: {
        active: true,
        picks: [],
        relations: [],
        regions: [],
        active_pick_id: null,
        active_region_id: null,
      },
    } as never);
    expect(backendState.inspector.active).toBe(true);
  });

  test('hydrate dispatches recordings_state to recordings sub-store', () => {
    backendState.hydrate({
      recordings_state: {
        recordings: [],
        active_recording_id: 'rec-snapshot-001',
        active_detail_recording_id: null,
        detail_recording: null,
        active_replay_progress: null,
      },
    } as never);
    expect(backendState.recordings.activeRecordingId).toBe('rec-snapshot-001');
  });

  test('hydrate dispatches recordings_state to voiceOver sub-store', () => {
    backendState.hydrate({
      recordings_state: {
        recordings: [
          {
            recording_id: 'v-rec',
            name: 'Voice',
            status: 'stopped',
            started_at_ms: 1000,
            entry_count: 0,
            has_voice_over: true,
            transcription_status: 'done',
          },
        ],
        active_recording_id: null,
        active_detail_recording_id: null,
        detail_recording: null,
        active_replay_progress: null,
      },
    } as never);
    expect(backendState.voiceOver.voiceOverRecordings).toHaveLength(1);
  });

  test('hydrate dispatches transcription_state to voiceOver sub-store', () => {
    backendState.hydrate({
      transcription_state: {
        backends: [
          {
            backend_id: 'mlx_whisper',
            display_name: 'mlx-whisper',
            status: 'ready',
            available_models: [],
            selected_model_id: null,
          },
        ],
      },
    } as never);
    expect(backendState.voiceOver.backends).toHaveLength(1);
  });

  test('hydrate dispatches microphone_state to mic sub-store', () => {
    backendState.hydrate({
      microphone_state: {
        devices: [{ device_id: 0, name: 'Built-in Mic', channels: 1, default_sample_rate: 44100 }],
        selected_device_id: null,
        system_default_device_id: 0,
      },
    } as never);
    expect(backendState.mic.devices).toHaveLength(1);
  });

  test('hydrate dispatches settings_state to settings sub-store', () => {
    backendState.hydrate({
      settings_state: {
        voice_over_enabled: true,
        selected_transcription_backend_id: 'mlx_whisper',
        mlx_whisper_model_id: null,
      },
    } as never);
    expect(backendState.settings.voiceOverEnabled).toBe(true);
  });

  test('hydrate with empty snapshot (all fields missing) is tolerant', () => {
    // Should not throw
    backendState.hydrate({} as never);
  });
});
