/**
 * Record split-button tests — TDD for sub-plan 03.
 *
 * Tests three concerns:
 *   1. recorder.startWithVoiceOver() sends recording_start_requested with
 *      with_voice_over=true via bridge.send()
 *   2. recorder.start() still sends with_voice_over=false (no regression)
 *   3. LeftPanelTools splits rec into mic-off and mic-on buttons:
 *      - mic-on disabled + tooltip when no ready transcription backend
 *      - mic-on enabled when at least one backend is ready
 *      - clicking mic-on calls recorder.startWithVoiceOver() (sends with_voice_over=true)
 *      - clicking mic-off calls recorder.start() (sends with_voice_over=false)
 *
 * Uses same mocking pattern as LeftPanelTools.svelte.test.ts (bridge spy).
 */

// Mock bridge so bridge.send() is a spy (no window.__fp needed in tests).
const send = vi.hoisted(() => vi.fn());
vi.mock('../bridge/bridge.svelte', () => ({ bridge: { send } }));

import { describe, expect, test, vi, beforeEach, afterEach } from 'vitest';
import { render, cleanup, fireEvent } from '@testing-library/svelte';
import { tick } from 'svelte';
import LeftPanelTools from '../components/left-panel/LeftPanelTools.svelte';
import { recorder } from '../local-state/recorder.svelte';
import { backendState } from '../backend-state/backend-state.svelte';

beforeEach(() => {
  send.mockClear();
  // Reset backend mirror to known initial state.
  backendState.recordings.activeRecordingId = null;
  backendState.voiceOver.backends = [];
});

afterEach(() => {
  cleanup();
});

// ---------------------------------------------------------------------------
// Helpers
// ---------------------------------------------------------------------------

/**
 * Find the mic-off (normal record) button in LeftPanelTools.
 * Kept narrow: matches aria-label="Start recording" OR "Stop recording".
 */
function micOffButton(container: HTMLElement): HTMLButtonElement {
  const btn = container.querySelector<HTMLButtonElement>(
    'button[aria-label="Start recording"], button[aria-label="Stop recording"]'
  );
  if (!btn) throw new Error('mic-off (normal record) button not found');
  return btn;
}

/**
 * Find the mic-on (voice-over record) button in LeftPanelTools.
 * Matches aria-label="Start voice-over recording".
 */
function micOnButton(container: HTMLElement): HTMLButtonElement {
  const btn = container.querySelector<HTMLButtonElement>(
    'button[aria-label="Start voice-over recording"]'
  );
  if (!btn) throw new Error('mic-on (voice-over record) button not found');
  return btn;
}

// ---------------------------------------------------------------------------
// Unit: recorder.startWithVoiceOver() and recorder.start()
// ---------------------------------------------------------------------------

describe('recorder.startWithVoiceOver() — sends with_voice_over=true', () => {
  test('startWithVoiceOver() sends recording_start_requested with with_voice_over: true', () => {
    recorder.startWithVoiceOver();
    expect(send).toHaveBeenCalledOnce();
    expect(send).toHaveBeenCalledWith(
      expect.objectContaining({
        kind: 'recording_start_requested',
        with_voice_over: true,
      })
    );
  });

  test('startWithVoiceOver(name, description) forwards custom name + description', () => {
    recorder.startWithVoiceOver('My Voice Session', 'spoken notes');
    expect(send).toHaveBeenCalledWith(
      expect.objectContaining({
        kind: 'recording_start_requested',
        with_voice_over: true,
        name: 'My Voice Session',
        description: 'spoken notes',
      })
    );
  });
});

describe('recorder.start() — with_voice_over stays false (no regression)', () => {
  test('start() sends recording_start_requested without with_voice_over=true', () => {
    recorder.start();
    expect(send).toHaveBeenCalledOnce();
    const call = send.mock.calls[0]![0];
    // Either with_voice_over is absent or explicitly false — never true
    expect(call.kind).toBe('recording_start_requested');
    expect(call.with_voice_over).not.toBe(true);
  });
});

// ---------------------------------------------------------------------------
// Component: split button renders in LeftPanelTools
// ---------------------------------------------------------------------------

describe('LeftPanelTools split rec button — two buttons present', () => {
  test('renders mic-off (normal rec) button', () => {
    const { container } = render(LeftPanelTools);
    const btn = micOffButton(container);
    expect(btn).toBeTruthy();
    expect(btn.textContent).toContain('rec');
  });

  test('renders mic-on (voice-over rec) button', () => {
    const { container } = render(LeftPanelTools);
    const btn = micOnButton(container);
    expect(btn).toBeTruthy();
  });
});

// ---------------------------------------------------------------------------
// Component: readiness gate on mic-on button
// ---------------------------------------------------------------------------

describe('LeftPanelTools mic-on button — readiness gate', () => {
  test('mic-on button is disabled when backends is empty (no ready backend)', () => {
    backendState.voiceOver.backends = [];
    const { container } = render(LeftPanelTools);
    expect(micOnButton(container).disabled).toBe(true);
  });

  test('mic-on button tooltip includes "No transcription backend ready" when no ready backend', () => {
    backendState.voiceOver.backends = [];
    const { container } = render(LeftPanelTools);
    const btn = micOnButton(container);
    expect(btn.getAttribute('title')).toContain('No transcription backend ready');
  });

  test('mic-on button is disabled when only non-ready backends exist', async () => {
    backendState.voiceOver.backends = [
      {
        backend_id: 'mlx_whisper',
        display_name: 'MLX Whisper',
        status: 'needs_download',
      },
    ];
    const { container } = render(LeftPanelTools);
    await tick();
    expect(micOnButton(container).disabled).toBe(true);
  });

  test('mic-on button is NOT disabled when at least one backend has status=ready', async () => {
    backendState.voiceOver.backends = [
      {
        backend_id: 'mlx_whisper',
        display_name: 'MLX Whisper',
        status: 'ready',
      },
    ];
    const { container } = render(LeftPanelTools);
    await tick();
    expect(micOnButton(container).disabled).toBe(false);
  });

  test('mic-on becomes enabled reactively when backend becomes ready', async () => {
    backendState.voiceOver.backends = [];
    const { container } = render(LeftPanelTools);
    expect(micOnButton(container).disabled).toBe(true);

    backendState.voiceOver.backends = [
      {
        backend_id: 'mlx_whisper',
        display_name: 'MLX Whisper',
        status: 'ready',
      },
    ];
    await tick();
    expect(micOnButton(container).disabled).toBe(false);
  });
});

// ---------------------------------------------------------------------------
// Component: button click interactions
// ---------------------------------------------------------------------------

describe('LeftPanelTools split rec button — click interactions', () => {
  test('clicking mic-on button when enabled sends recording_start_requested with with_voice_over=true', async () => {
    backendState.voiceOver.backends = [
      {
        backend_id: 'mlx_whisper',
        display_name: 'MLX Whisper',
        status: 'ready',
      },
    ];
    const { container } = render(LeftPanelTools);
    await tick();
    await fireEvent.click(micOnButton(container));
    expect(send).toHaveBeenCalledOnce();
    expect(send).toHaveBeenCalledWith(
      expect.objectContaining({
        kind: 'recording_start_requested',
        with_voice_over: true,
      })
    );
  });

  test('clicking mic-off button sends recording_start_requested WITHOUT with_voice_over=true', async () => {
    const { container } = render(LeftPanelTools);
    await fireEvent.click(micOffButton(container));
    expect(send).toHaveBeenCalledOnce();
    const call = send.mock.calls[0]![0];
    expect(call.kind).toBe('recording_start_requested');
    expect(call.with_voice_over).not.toBe(true);
  });

  test('clicking mic-off when recording is active sends recording_stop_requested', async () => {
    const { container } = render(LeftPanelTools);
    backendState.recordings.activeRecordingId = 'rec-vo-001';
    await tick();
    await fireEvent.click(micOffButton(container));
    expect(send).toHaveBeenCalledWith(
      expect.objectContaining({
        kind: 'recording_stop_requested',
        recording_id: 'rec-vo-001',
      })
    );
  });
});
