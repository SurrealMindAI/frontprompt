/**
 * settings-mic-dropdown.test.ts — TDD for BUG 1 (blank mic dropdown / clear-on-select).
 *
 * The live overlay symptom: the microphone <select> renders no device <option>s
 * even though the backend snapshot carries 5 devices and a persisted
 * selected_device_id. Because the bound value (selectedDeviceId=4) has no
 * matching <option>, the control appears "cleared".
 *
 * Two distinct paths are exercised:
 *   A. Aggregator hydrate → initial render. `backendState.hydrate(snapshot)` is the
 *      SINGLE entry-point both the pre-mount seed (main.ts) and the live
 *      state_snapshot broadcast (backend-state/sync) funnel through. A snapshot
 *      with 5 devices + selected_device_id:4 must yield 5 device <option>s and a
 *      selected value of "4".
 *   B. POST-render reactivity (the real-overlay timing). In production the mic
 *      device list is EMPTY at mount (the MicrophoneWatcher task starts only
 *      AFTER the seed + OverlayReady re-hydration) and arrives later via a
 *      state_snapshot broadcast. The dropdown must re-render when
 *      `backendState.hydrate(snapshot)` is called AFTER SettingsTab has mounted.
 *
 * Bridge is mocked so bridge.send() is a spy (no window.__fp needed in tests).
 */

// Mock bridge so bridge.send() is a spy (no window.__fp needed in tests).
const send = vi.hoisted(() => vi.fn());
vi.mock('../bridge/bridge.svelte', () => ({ bridge: { send } }));

import { describe, expect, test, vi, beforeEach, afterEach } from 'vitest';
import { render, cleanup } from '@testing-library/svelte';
import { tick } from 'svelte';
import SettingsTab from '../components/left-panel/tabs/SettingsTab.svelte';
import { backendState } from '../backend-state/backend-state.svelte';
import type { StateSnapshot } from '../_generated/state';

// ---------------------------------------------------------------------------
// Fixtures
// ---------------------------------------------------------------------------

/** Five real-world input devices mirroring the user's live snapshot. */
const FIVE_DEVICES = [
  { device_id: 4, name: 'MacBook Pro Microphone', channels: 1, default_sample_rate: 48000 },
  { device_id: 1, name: 'iPhone Microphone', channels: 1, default_sample_rate: 48000 },
  { device_id: 2, name: 'BlackHole 2ch', channels: 2, default_sample_rate: 48000 },
  { device_id: 3, name: 'Q9-1', channels: 2, default_sample_rate: 44100 },
  { device_id: 5, name: 'FL Studio ASIO', channels: 2, default_sample_rate: 44100 },
];

/** Build a StateSnapshot whose microphone_state carries the 5 devices + selection. */
function snapshotWithMics(selectedDeviceId: number | null = 4): StateSnapshot {
  return {
    microphone_state: {
      devices: FIVE_DEVICES,
      selected_device_id: selectedDeviceId,
      system_default_device_id: 4,
    },
  } as StateSnapshot;
}

/** Find the mic-select dropdown in the rendered SettingsTab. */
function micSelect(container: HTMLElement): HTMLSelectElement | null {
  return container.querySelector<HTMLSelectElement>('select.mic-select');
}

/** Count the device <option>s (excludes the always-present "System default"). */
function deviceOptions(select: HTMLSelectElement): HTMLOptionElement[] {
  return Array.from(select.querySelectorAll<HTMLOptionElement>('option')).filter(
    (o) => o.value !== ''
  );
}

// ---------------------------------------------------------------------------
// Setup / teardown
// ---------------------------------------------------------------------------

beforeEach(() => {
  send.mockClear();
  backendState.voiceOver.backends = [];
  backendState.mic.devices = [];
  backendState.mic.selectedDeviceId = null;
  backendState.mic.systemDefaultDeviceId = null;
});

afterEach(() => {
  cleanup();
});

// ---------------------------------------------------------------------------
// Path A — aggregator hydrate → initial render
// ---------------------------------------------------------------------------

describe('mic dropdown — hydrate via backendState.hydrate (seed/broadcast entry-point)', () => {
  test('test_mic_dropdown_renders_all_devices_from_snapshot', async () => {
    backendState.hydrate(snapshotWithMics(4));
    const { container } = render(SettingsTab);
    await tick();

    const select = micSelect(container);
    expect(select).not.toBeNull();
    expect(deviceOptions(select!)).toHaveLength(5);
  });

  test('test_mic_dropdown_selected_option_matches_persisted_device_id', async () => {
    backendState.hydrate(snapshotWithMics(4));
    const { container } = render(SettingsTab);
    await tick();

    const select = micSelect(container);
    expect(select).not.toBeNull();
    // The persisted selection (4) must resolve to a real <option>, not appear cleared.
    expect(select!.value).toBe('4');
  });

  test('test_mic_dropdown_device_names_render', async () => {
    backendState.hydrate(snapshotWithMics(4));
    const { container } = render(SettingsTab);
    await tick();

    const select = micSelect(container);
    const labels = deviceOptions(select!).map((o) => o.textContent?.trim());
    expect(labels).toContain('MacBook Pro Microphone');
    expect(labels).toContain('BlackHole 2ch');
  });
});

// ---------------------------------------------------------------------------
// Path B — POST-render reactivity (real-overlay watcher timing)
// ---------------------------------------------------------------------------

describe('mic dropdown — reactive to a post-mount snapshot broadcast', () => {
  test('test_mic_dropdown_populates_after_late_hydrate', async () => {
    // Mount with an empty device list (the state at the moment the overlay mounts,
    // before the MicrophoneWatcher task has run its first enumeration).
    const { container } = render(SettingsTab);
    await tick();

    const select = micSelect(container);
    expect(select).not.toBeNull();
    expect(deviceOptions(select!)).toHaveLength(0);

    // The watcher fires later: a state_snapshot broadcast arrives and is applied
    // through the SAME aggregator entry-point the sync handler uses.
    backendState.hydrate(snapshotWithMics(4));
    await tick();

    expect(deviceOptions(select!)).toHaveLength(5);
    expect(select!.value).toBe('4');
  });
});
