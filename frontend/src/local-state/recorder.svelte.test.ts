/**
 * Recorder state machine tests.
 *
 * The recorder is a localState singleton (dies-with-the-page, UI-coordination).
 * isActive is derived from backendState.recordings.activeRecordingId (Python SSoT,
 * PIT-037: no duplicate $state).
 *
 * floatingToolbarPosition + activeDragHandle are pure localState (ADR-018).
 */

// Mock the bridge so bridge.send() is a spy (no window.__fp needed).
const send = vi.hoisted(() => vi.fn());
vi.mock('../bridge/bridge.svelte', () => ({ bridge: { send } }));

import { describe, expect, test, vi, beforeEach } from 'vitest';
import { recorder } from './recorder.svelte';
import { backendState } from '../backend-state/backend-state.svelte';

beforeEach(() => {
  send.mockClear();
  // Reset floatingToolbarPosition + activeDragHandle to known initial values.
  recorder.moveToolbar({ x: 16, y: 120 });
  recorder.activeDragHandle = null;
  // Reset recordings backend-state mirror so each test starts with no active recording.
  backendState.recordings.activeRecordingId = null;
});

describe('recorder.isActive (derived from backendState)', () => {
  test('isActive is false when activeRecordingId is null', () => {
    backendState.recordings.activeRecordingId = null;
    expect(recorder.isActive).toBe(false);
  });

  test('isActive is true when activeRecordingId is set to any string', () => {
    backendState.recordings.activeRecordingId = 'rec-abc-123';
    expect(recorder.isActive).toBe(true);
  });

  test('isActive flips back to false when activeRecordingId is cleared', () => {
    backendState.recordings.activeRecordingId = 'rec-abc-123';
    backendState.recordings.activeRecordingId = null;
    expect(recorder.isActive).toBe(false);
  });
});

describe('recorder.start() — delegates to backendState.recordings.startRecording()', () => {
  test('start() with defaults sends recording_start_requested via bridge', () => {
    recorder.start();
    expect(send).toHaveBeenCalledOnce();
    expect(send).toHaveBeenCalledWith(
      expect.objectContaining({
        kind: 'recording_start_requested',
        name: 'New Recording',
        description: '',
      })
    );
  });

  test('start(name, description) forwards custom name + description', () => {
    recorder.start('My Session', 'describing it');
    expect(send).toHaveBeenCalledWith(
      expect.objectContaining({
        kind: 'recording_start_requested',
        name: 'My Session',
        description: 'describing it',
      })
    );
  });
});

describe('recorder.stop() — delegates to backendState.recordings.stopRecording()', () => {
  test('stop() is a no-op when no active recording (does not send)', () => {
    backendState.recordings.activeRecordingId = null;
    recorder.stop();
    expect(send).not.toHaveBeenCalled();
  });

  test('stop() sends recording_stop_requested with current activeRecordingId', () => {
    backendState.recordings.activeRecordingId = 'rec-xyz-456';
    recorder.stop();
    expect(send).toHaveBeenCalledOnce();
    expect(send).toHaveBeenCalledWith(
      expect.objectContaining({
        kind: 'recording_stop_requested',
        recording_id: 'rec-xyz-456',
      })
    );
  });
});

describe('recorder.floatingToolbarPosition (localState)', () => {
  test('floatingToolbarPosition starts at sensible default {x:16, y:120}', () => {
    // Fresh state set in beforeEach.
    expect(recorder.floatingToolbarPosition).toEqual({ x: 16, y: 120 });
  });

  test('moveToolbar({x, y}) updates position (pure localState — no bridge roundtrip)', () => {
    recorder.moveToolbar({ x: 200, y: 350 });
    expect(recorder.floatingToolbarPosition).toEqual({ x: 200, y: 350 });
    expect(send).not.toHaveBeenCalled();
  });

  test('moveToolbar can be called multiple times and last write wins', () => {
    recorder.moveToolbar({ x: 100, y: 200 });
    recorder.moveToolbar({ x: 42, y: 99 });
    expect(recorder.floatingToolbarPosition).toEqual({ x: 42, y: 99 });
  });
});

describe('recorder.activeDragHandle (localState)', () => {
  test('activeDragHandle is null by default', () => {
    expect(recorder.activeDragHandle).toBeNull();
  });

  test('activeDragHandle can be set to a non-null value during drag', () => {
    recorder.activeDragHandle = 'toolbar-drag';
    expect(recorder.activeDragHandle).toBe('toolbar-drag');
  });

  test('activeDragHandle can be cleared back to null after drag', () => {
    recorder.activeDragHandle = 'toolbar-drag';
    recorder.activeDragHandle = null;
    expect(recorder.activeDragHandle).toBeNull();
  });
});

describe('recorder.isActive is read-only (derived)', () => {
  test('isActive reflects backend state — mutations only via start()/stop()', () => {
    // isActive is derived, not writable. Verify that only the backend SSoT
    // (activeRecordingId) controls it, and recorder methods delegate there.
    expect(recorder.isActive).toBe(false);
    backendState.recordings.activeRecordingId = 'rec-test';
    expect(recorder.isActive).toBe(true);
    backendState.recordings.activeRecordingId = null;
    expect(recorder.isActive).toBe(false);
  });
});
