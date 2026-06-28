/**
 * SettingsTab component tests (vitest + jsdom + @testing-library/svelte).
 *
 * Test surface:
 *   - Empty/loading state: renders without error when micState.devices is empty
 *   - Mic picker: renders a <select> with device options
 *   - Mic picker: selecting a device triggers SetMicDeviceRequested via bridge
 *   - Backend list: renders "mlx-whisper (Apple Silicon)" with status badge
 *   - Backend "needs_download": Download button visible, triggers TriggerModelDownloadRequested
 *   - Backend "downloading": progress bar visible with correct fraction
 *   - Backend select action: clicking a backend row triggers SetTranscriptionBackendRequested
 */

// Bridge mock — hoisted before module imports
const send = vi.hoisted(() => vi.fn());
vi.mock('../../../bridge/bridge.svelte', () => ({ bridge: { send } }));

import { describe, expect, test, vi, afterEach } from 'vitest';
import { render, cleanup, fireEvent } from '@testing-library/svelte';
import SettingsTab from './SettingsTab.svelte';
import { backendState } from '../../../backend-state/backend-state.svelte';
import type { MicrophoneDevice, TranscriptionBackendInfo } from '../../../_generated/state';

afterEach(() => {
  cleanup();
  send.mockClear();
  backendState.mic.devices = [];
  backendState.mic.selectedDeviceId = null;
  backendState.voiceOver.backends = [];
  backendState.settings.voiceOverEnabled = false;
  backendState.settings.selectedTranscriptionBackendId = null;
});

// --- Fixtures ---------------------------------------------------------------

function makeMicDevice(overrides: Partial<MicrophoneDevice> = {}): MicrophoneDevice {
  return {
    device_id: 1,
    name: 'Built-in Microphone',
    channels: 1,
    default_sample_rate: 44100,
    ...overrides,
  };
}

function makeBackendInfo(overrides: Partial<TranscriptionBackendInfo> = {}): TranscriptionBackendInfo {
  return {
    backend_id: 'mlx_whisper',
    display_name: 'mlx-whisper (Apple Silicon)',
    status: 'ready',
    download_progress: null,
    error_message: null,
    ...overrides,
  };
}

// --- Tests: loading state ---------------------------------------------------

describe('SettingsTab — loading state', () => {
  test('renders without error when micState.devices is empty', () => {
    backendState.mic.devices = [];
    backendState.voiceOver.backends = [];
    // Should not throw; basic structure is present
    const { container } = render(SettingsTab, {});
    expect(container).toBeTruthy();
  });
});

// --- Tests: mic picker ------------------------------------------------------

describe('SettingsTab — mic picker', () => {
  test('renders a select with mic device options when devices has entries', () => {
    backendState.mic.devices = [
      makeMicDevice({ device_id: 1, name: 'Built-in Mic' }),
      makeMicDevice({ device_id: 2, name: 'External USB Mic' }),
    ];
    const { container } = render(SettingsTab, {});
    const select = container.querySelector('select.mic-select');
    expect(select).not.toBeNull();
    const options = select!.querySelectorAll('option');
    // Should contain both devices (plus possibly a default option)
    expect(options.length).toBeGreaterThanOrEqual(2);
    const texts = Array.from(options).map((o) => o.textContent ?? '');
    expect(texts.some((t) => t.includes('Built-in Mic'))).toBe(true);
    expect(texts.some((t) => t.includes('External USB Mic'))).toBe(true);
  });

  test('selecting a mic device triggers bridge send with SetMicDeviceRequested', async () => {
    backendState.mic.devices = [
      makeMicDevice({ device_id: 3, name: 'USB Condenser' }),
    ];
    const { container } = render(SettingsTab, {});
    const select = container.querySelector('select.mic-select') as HTMLSelectElement;
    expect(select).not.toBeNull();
    // Simulate selecting device 3
    await fireEvent.change(select, { target: { value: '3' } });
    expect(send).toHaveBeenCalledWith(
      expect.objectContaining({
        kind: 'set_mic_device_requested',
        mic_device_id: 3,
      })
    );
  });
});

// --- Tests: backend list ----------------------------------------------------

describe('SettingsTab — backend list', () => {
  test('renders backend display_name with status badge', () => {
    backendState.voiceOver.backends = [
      makeBackendInfo({ display_name: 'mlx-whisper (Apple Silicon)', status: 'ready' }),
    ];
    const { container } = render(SettingsTab, {});
    expect(container.textContent).toContain('mlx-whisper (Apple Silicon)');
    const badge = container.querySelector('.backend-status-badge');
    expect(badge).not.toBeNull();
  });

  test('renders Download button for needs_download backend', () => {
    backendState.voiceOver.backends = [
      makeBackendInfo({ backend_id: 'mlx_whisper', status: 'needs_download' }),
    ];
    const { container } = render(SettingsTab, {});
    const downloadBtn = container.querySelector('.backend-download-btn');
    expect(downloadBtn).not.toBeNull();
  });

  test('clicking Download button triggers TriggerModelDownloadRequested', async () => {
    backendState.voiceOver.backends = [
      makeBackendInfo({ backend_id: 'mlx_whisper', status: 'needs_download' }),
    ];
    const { container } = render(SettingsTab, {});
    const downloadBtn = container.querySelector('.backend-download-btn');
    expect(downloadBtn).not.toBeNull();
    await fireEvent.click(downloadBtn!);
    expect(send).toHaveBeenCalledWith(
      expect.objectContaining({
        kind: 'trigger_model_download_requested',
        backend_id: 'mlx_whisper',
      })
    );
  });

  test('renders progress bar when backend status is downloading', () => {
    backendState.voiceOver.backends = [
      makeBackendInfo({ backend_id: 'mlx_whisper', status: 'downloading', download_progress: 0.4 }),
    ];
    const { container } = render(SettingsTab, {});
    const bar = container.querySelector('.backend-download-progress');
    expect(bar).not.toBeNull();
  });

  test('selecting a backend triggers SetTranscriptionBackendRequested', async () => {
    backendState.voiceOver.backends = [
      makeBackendInfo({ backend_id: 'mlx_whisper', display_name: 'mlx-whisper (Apple Silicon)', status: 'ready' }),
    ];
    const { container } = render(SettingsTab, {});
    const selectBtn = container.querySelector('.backend-select-btn');
    expect(selectBtn).not.toBeNull();
    await fireEvent.click(selectBtn!);
    expect(send).toHaveBeenCalledWith(
      expect.objectContaining({
        kind: 'set_transcription_backend_requested',
        backend_id: 'mlx_whisper',
      })
    );
  });

  test('backend already selected shows "Selected" on the select button', () => {
    backendState.voiceOver.backends = [
      makeBackendInfo({ backend_id: 'mlx_whisper', display_name: 'mlx-whisper (Apple Silicon)', status: 'ready' }),
    ];
    // Set as already selected
    backendState.settings.selectedTranscriptionBackendId = 'mlx_whisper';
    const { container } = render(SettingsTab, {});
    const selectBtn = container.querySelector('.backend-select-btn');
    expect(selectBtn).not.toBeNull();
    expect(selectBtn!.textContent?.trim()).toBe('Selected');
  });

  test('unselected backend shows "Select" (not "Selected") on the button', () => {
    backendState.voiceOver.backends = [
      makeBackendInfo({ backend_id: 'mlx_whisper', status: 'ready' }),
    ];
    backendState.settings.selectedTranscriptionBackendId = null;
    const { container } = render(SettingsTab, {});
    const selectBtn = container.querySelector('.backend-select-btn');
    expect(selectBtn!.textContent?.trim()).toBe('Select');
  });

  test('backend with available_models renders model select dropdown (mlx_whisper)', () => {
    backendState.voiceOver.backends = [
      makeBackendInfo({
        backend_id: 'mlx_whisper',
        status: 'ready',
        available_models: [
          { model_id: 'base', display_name: 'Whisper Base', default: true, downloaded: true },
          { model_id: 'large', display_name: 'Whisper Large', default: false, downloaded: false },
        ],
      } as any),
    ];
    const { container } = render(SettingsTab, {});
    const modelSelect = container.querySelector('.model-select');
    expect(modelSelect).not.toBeNull();
    const options = modelSelect!.querySelectorAll('option');
    expect(options.length).toBeGreaterThanOrEqual(2);
    expect(Array.from(options).some((o) => o.textContent?.includes('Whisper Base'))).toBe(true);
  });

  test('model select with selected_model_id set shows it as value', () => {
    backendState.voiceOver.backends = [
      makeBackendInfo({
        backend_id: 'mlx_whisper',
        status: 'ready',
        selected_model_id: 'large',
        available_models: [
          { model_id: 'base', display_name: 'Whisper Base', default: true, downloaded: true },
          { model_id: 'large', display_name: 'Whisper Large', default: false, downloaded: false },
        ],
      } as any),
    ];
    const { container } = render(SettingsTab, {});
    const modelSelect = container.querySelector('.model-select') as HTMLSelectElement;
    expect(modelSelect).not.toBeNull();
    // getEffectiveModelId returns selected_model_id when set
    expect(modelSelect.value).toBe('large');
  });

  test('model select with no selected_model_id falls back to default model', () => {
    backendState.voiceOver.backends = [
      makeBackendInfo({
        backend_id: 'mlx_whisper',
        status: 'ready',
        selected_model_id: null,
        available_models: [
          { model_id: 'base', display_name: 'Whisper Base', default: true, downloaded: true },
          { model_id: 'large', display_name: 'Whisper Large', default: false, downloaded: false },
        ],
      } as any),
    ];
    const { container } = render(SettingsTab, {});
    const modelSelect = container.querySelector('.model-select') as HTMLSelectElement;
    expect(modelSelect).not.toBeNull();
    // getEffectiveModelId falls back to model with default=true
    expect(modelSelect.value).toBe('base');
  });

  test('model select with no available_models shows "No models available" option', () => {
    backendState.voiceOver.backends = [
      makeBackendInfo({
        backend_id: 'mlx_whisper',
        status: 'ready',
        available_models: null,
      } as any),
    ];
    const { container } = render(SettingsTab, {});
    const modelSelect = container.querySelector('.model-select');
    expect(modelSelect).not.toBeNull();
    expect(container.textContent).toContain('No models available');
  });

  test('changing model select fires onModelChange (covers setTranscriptionModel)', async () => {
    backendState.voiceOver.backends = [
      makeBackendInfo({
        backend_id: 'mlx_whisper',
        status: 'ready',
        available_models: [
          { model_id: 'base', display_name: 'Whisper Base', default: true, downloaded: true },
          { model_id: 'large', display_name: 'Whisper Large', default: false, downloaded: false },
        ],
      } as any),
    ];
    const setModelSpy = vi.spyOn(backendState.settings, 'setTranscriptionModel').mockReturnValue(undefined as any);
    const { container } = render(SettingsTab, {});
    const modelSelect = container.querySelector('.model-select') as HTMLSelectElement;
    expect(modelSelect).not.toBeNull();
    await fireEvent.change(modelSelect, { target: { value: 'large' } });
    expect(setModelSpy).toHaveBeenCalledWith('mlx_whisper', 'large');
    setModelSpy.mockRestore();
  });

  test('backend with unrecognized status falls back to raw status string — covers STATUS_LABELS ?? branch at line 120', () => {
    // STATUS_LABELS does not contain 'custom_status' → right side of ?? fires: ?? backend.status
    backendState.voiceOver.backends = [
      makeBackendInfo({ backend_id: 'mlx_whisper', status: 'custom_status' as any }),
    ];
    const { container } = render(SettingsTab, {});
    const badge = container.querySelector('.backend-status-badge');
    expect(badge?.textContent?.trim()).toBe('custom_status');
  });

  test('mlx_whisper with non-empty available_models renders model option list — covers {#each} at line 179', () => {
    // available_models non-empty → !available_models=false, length===0=false → {:else} → {#each}
    backendState.voiceOver.backends = [
      makeBackendInfo({
        backend_id: 'mlx_whisper',
        status: 'ready',
        available_models: [
          { model_id: 'base', display_name: 'Whisper Base', default: true, downloaded: true },
          { model_id: 'turbo', display_name: 'Whisper Turbo', default: false, downloaded: false },
        ],
      } as any),
    ];
    const { container } = render(SettingsTab, {});
    const modelSelect = container.querySelector('.model-select') as HTMLSelectElement;
    expect(modelSelect).not.toBeNull();
    const options = modelSelect.querySelectorAll('option');
    // {#each available_models} renders one <option> per model
    expect(options.length).toBe(2);
    expect(Array.from(options).map((o) => o.value)).toContain('base');
    expect(Array.from(options).map((o) => o.value)).toContain('turbo');
  });

  test('renders "No backends registered." when backends list is empty', () => {
    backendState.voiceOver.backends = [];
    const { container } = render(SettingsTab, {});
    expect(container.textContent).toContain('No backends registered.');
  });

  test('backend with "downloading" status shows select button', () => {
    backendState.voiceOver.backends = [
      makeBackendInfo({ backend_id: 'mlx_whisper', status: 'downloading', download_progress: 0.6 }),
    ];
    const { container } = render(SettingsTab, {});
    // status===downloading → shows both progress bar AND select button
    expect(container.querySelector('.backend-download-progress')).not.toBeNull();
    expect(container.querySelector('.backend-select-btn')).not.toBeNull();
  });

  test('downloading backend with null download_progress shows 0% (covers ?? 0 null branch)', () => {
    // download_progress: null → (null ?? 0) = 0 → covers the right side of ?? 0
    backendState.voiceOver.backends = [
      makeBackendInfo({ backend_id: 'mlx_whisper', status: 'downloading', download_progress: null }),
    ];
    const { container } = render(SettingsTab, {});
    const bar = container.querySelector('.backend-download-progress');
    expect(bar).not.toBeNull();
    // aria-valuenow = (null ?? 0) * 100 = 0
    expect(bar!.getAttribute('aria-valuenow')).toBe('0');
  });

  test('non-mlx backend does not render model select section (covers backend_id !== MLX_WHISPER false branch)', () => {
    // When backend_id !== 'mlx_whisper', the model-select-section is NOT rendered.
    backendState.voiceOver.backends = [
      makeBackendInfo({ backend_id: 'faster_whisper', display_name: 'Faster Whisper', status: 'ready' }),
    ];
    const { container } = render(SettingsTab, {});
    // The backend renders (name shows)
    expect(container.textContent).toContain('Faster Whisper');
    // But no model-select-section (only mlx_whisper shows it)
    expect(container.querySelector('.model-select-section')).toBeNull();
  });

  test('mlx_whisper backend with empty available_models array shows "No models available" (covers length===0 branch)', () => {
    // available_models: [] (empty, not null) → !available_models=false, length===0=true → disabled option
    backendState.voiceOver.backends = [
      makeBackendInfo({
        backend_id: 'mlx_whisper',
        status: 'ready',
        available_models: [],
      } as any),
    ];
    const { container } = render(SettingsTab, {});
    expect(container.querySelector('.model-select')).not.toBeNull();
    expect(container.textContent).toContain('No models available');
  });
});
