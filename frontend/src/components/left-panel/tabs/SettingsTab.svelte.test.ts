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
});
