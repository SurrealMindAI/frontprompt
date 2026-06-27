/**
 * settings-model-dropdown.test.ts — TDD for sub-plan 04.
 *
 * Tests nine concerns:
 *   1. Model dropdown hidden when no mlx_whisper backend registered
 *   2. Model dropdown visible when mlx_whisper backend present
 *   3. Model dropdown <select> disabled when available_models is empty
 *   4. Model dropdown renders exactly N options for N available models (incl. German)
 *   5. Selected option matches selected_model_id from backend state
 *   6. Null selected_model_id → option with default=true is selected
 *   7. Change event sends SetTranscriptionModelRequested via bridge
 *   8. SettingsState.hydrate() mirrors mlx_whisper_model_id correctly
 *   9. SettingsState.hydrate() mirrors null mlx_whisper_model_id as null
 *
 * Bridge is mocked so bridge.send() is a spy (no window.__fp needed in tests).
 */

// Mock bridge so bridge.send() is a spy (no window.__fp needed in tests).
const send = vi.hoisted(() => vi.fn());
vi.mock('../bridge/bridge.svelte', () => ({ bridge: { send } }));

import { describe, expect, test, vi, beforeEach, afterEach } from 'vitest';
import { render, cleanup, fireEvent } from '@testing-library/svelte';
import { tick } from 'svelte';
import SettingsTab from '../components/left-panel/tabs/SettingsTab.svelte';
import { backendState } from '../backend-state/backend-state.svelte';
import { SettingsState } from '../backend-state/settings-state.svelte';
import type { TranscriptionBackendInfo, TranscriptionModelSpec } from '../_generated/state';

// ---------------------------------------------------------------------------
// Constants
// ---------------------------------------------------------------------------

const MLX_WHISPER_BACKEND_ID = 'mlx_whisper';

/** Three-entry catalog — whisper-base (default), large-v3-turbo, German variant. */
const SAMPLE_MODELS: TranscriptionModelSpec[] = [
  {
    model_id: 'whisper-base-mlx',
    display_name: 'Whisper Base (MLX)',
    hf_repo_id: 'mlx-community/whisper-base-mlx',
    default: true,
  },
  {
    model_id: 'whisper-large-v3-turbo',
    display_name: 'Whisper Large v3 Turbo',
    hf_repo_id: 'mlx-community/whisper-large-v3-turbo',
    default: false,
  },
  {
    model_id: 'whisper-large-v3-turbo-german',
    display_name: 'Whisper Large v3 Turbo (German)',
    hf_repo_id: 'primeline/whisper-large-v3-turbo-german-mlx',
    default: false,
  },
];

// ---------------------------------------------------------------------------
// Helpers
// ---------------------------------------------------------------------------

/** Build a minimal mlx_whisper TranscriptionBackendInfo, overrides allowed. */
function mlxBackend(overrides: Partial<TranscriptionBackendInfo> = {}): TranscriptionBackendInfo {
  return {
    backend_id: MLX_WHISPER_BACKEND_ID,
    display_name: 'MLX Whisper (Apple Silicon)',
    status: 'ready',
    available_models: SAMPLE_MODELS,
    selected_model_id: null,
    ...overrides,
  };
}

/** Find the model-select dropdown in the rendered SettingsTab. */
function modelSelect(container: HTMLElement): HTMLSelectElement | null {
  return container.querySelector<HTMLSelectElement>('select.model-select');
}

// ---------------------------------------------------------------------------
// Setup / teardown
// ---------------------------------------------------------------------------

beforeEach(() => {
  send.mockClear();
  backendState.voiceOver.backends = [];
  backendState.mic.devices = [];
  backendState.mic.selectedDeviceId = null;
});

afterEach(() => {
  cleanup();
});

// ---------------------------------------------------------------------------
// Visibility tests
// ---------------------------------------------------------------------------

describe('model dropdown — visibility', () => {
  test('test_model_dropdown_hidden_when_no_mlx_backend', async () => {
    backendState.voiceOver.backends = [];
    const { container } = render(SettingsTab);
    await tick();
    expect(modelSelect(container)).toBeNull();
  });

  test('test_model_dropdown_visible_when_mlx_backend_present', async () => {
    backendState.voiceOver.backends = [mlxBackend()];
    const { container } = render(SettingsTab);
    await tick();
    expect(modelSelect(container)).not.toBeNull();
  });
});

// ---------------------------------------------------------------------------
// Disabled-state test
// ---------------------------------------------------------------------------

describe('model dropdown — disabled when no available_models', () => {
  test('test_model_dropdown_disabled_when_no_available_models', async () => {
    backendState.voiceOver.backends = [mlxBackend({ available_models: [] })];
    const { container } = render(SettingsTab);
    await tick();
    const select = modelSelect(container);
    expect(select).not.toBeNull();
    expect(select!.disabled).toBe(true);
  });
});

// ---------------------------------------------------------------------------
// Option-rendering tests
// ---------------------------------------------------------------------------

describe('model dropdown — option rendering', () => {
  test('test_model_dropdown_renders_all_available_models', async () => {
    backendState.voiceOver.backends = [mlxBackend()];
    const { container } = render(SettingsTab);
    await tick();
    const select = modelSelect(container);
    expect(select).not.toBeNull();
    const options = select!.querySelectorAll<HTMLOptionElement>('option');
    expect(options).toHaveLength(3);
  });

  test('test_model_dropdown_selected_option_matches_selected_model_id', async () => {
    backendState.voiceOver.backends = [
      mlxBackend({ selected_model_id: 'whisper-large-v3-turbo' }),
    ];
    const { container } = render(SettingsTab);
    await tick();
    const select = modelSelect(container);
    expect(select).not.toBeNull();
    expect(select!.value).toBe('whisper-large-v3-turbo');
  });

  test('test_model_dropdown_null_selected_model_id_selects_default', async () => {
    backendState.voiceOver.backends = [mlxBackend({ selected_model_id: null })];
    const { container } = render(SettingsTab);
    await tick();
    const select = modelSelect(container);
    expect(select).not.toBeNull();
    // Default model is whisper-base-mlx (default: true in catalog)
    expect(select!.value).toBe('whisper-base-mlx');
  });
});

// ---------------------------------------------------------------------------
// Change-event test
// ---------------------------------------------------------------------------

describe('model dropdown — change event sends bridge message', () => {
  test('test_model_dropdown_change_sends_bridge_message', async () => {
    backendState.voiceOver.backends = [mlxBackend()];
    const { container } = render(SettingsTab);
    await tick();
    const select = modelSelect(container);
    expect(select).not.toBeNull();

    // Fire change event with new value
    await fireEvent.change(select!, { target: { value: 'whisper-large-v3-turbo' } });

    expect(send).toHaveBeenCalledOnce();
    expect(send).toHaveBeenCalledWith(
      expect.objectContaining({
        kind: 'set_transcription_model_requested',
        backend_id: MLX_WHISPER_BACKEND_ID,
        model_id: 'whisper-large-v3-turbo',
      })
    );
  });
});

// ---------------------------------------------------------------------------
// Unit tests — SettingsState.hydrate() mirror
// ---------------------------------------------------------------------------

describe('SettingsState — mlxWhisperModelId mirror', () => {
  test('test_settings_state_mirrors_mlx_whisper_model_id', () => {
    const state = new SettingsState();
    state.hydrate({ mlx_whisper_model_id: 'whisper-large-v3-turbo' });
    expect(state.mlxWhisperModelId).toBe('whisper-large-v3-turbo');
  });

  test('test_settings_state_null_model_id_mirrors_as_null', () => {
    const state = new SettingsState();
    state.hydrate({ mlx_whisper_model_id: null });
    expect(state.mlxWhisperModelId).toBeNull();
  });
});
