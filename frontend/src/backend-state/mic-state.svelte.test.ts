/**
 * MicState hydration smoke tests (sub-plan 02).
 *
 * Verifies that the microphone state mirror hydrates correctly from StateSnapshot
 * microphone_state field.
 */
import { describe, expect, test } from 'vitest';

import { MicState } from './mic-state.svelte';

describe('MicState hydration', () => {
  test('initial state: no devices, no selected device', () => {
    const state = new MicState();
    expect(state.devices).toEqual([]);
    expect(state.selectedDeviceId).toBeNull();
    expect(state.systemDefaultDeviceId).toBeNull();
  });

  test('hydrate with devices list', () => {
    const state = new MicState();
    state.hydrate({
      devices: [
        { device_id: 0, name: 'Built-in Microphone', channels: 1, default_sample_rate: 44100 },
        { device_id: 1, name: 'USB Mic', channels: 2, default_sample_rate: 48000 },
      ],
      selected_device_id: null,
      system_default_device_id: 0,
    });
    expect(state.devices).toHaveLength(2);
    expect(state.devices[0]!.name).toBe('Built-in Microphone');
    expect(state.devices[1]!.device_id).toBe(1);
    expect(state.selectedDeviceId).toBeNull();
    expect(state.systemDefaultDeviceId).toBe(0);
  });

  test('hydrate with selected_device_id set', () => {
    const state = new MicState();
    state.hydrate({
      devices: [{ device_id: 2, name: 'Headset Mic', channels: 1, default_sample_rate: 44100 }],
      selected_device_id: 2,
      system_default_device_id: 0,
    });
    expect(state.selectedDeviceId).toBe(2);
  });

  test('hydrate with empty devices — clears list', () => {
    const state = new MicState();
    state.hydrate({
      devices: [{ device_id: 0, name: 'Mic', channels: 1, default_sample_rate: 44100 }],
      selected_device_id: 0,
      system_default_device_id: 0,
    });
    state.hydrate({ devices: [], selected_device_id: null, system_default_device_id: null });
    expect(state.devices).toEqual([]);
    expect(state.selectedDeviceId).toBeNull();
    expect(state.systemDefaultDeviceId).toBeNull();
  });

  test('hydrate with undefined fields is tolerant (missing fields from older snapshots)', () => {
    const state = new MicState();
    // Should not throw when microphone_state fields are missing
    state.hydrate({});
    expect(state.devices).toEqual([]);
  });
});
