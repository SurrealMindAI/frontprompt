/**
 * RecordingState — tests covering hydrate + all intent methods.
 *
 * Covers: hydrate, isRecording derived, activeRecording derived,
 * startRecording, startRecordingWithVoiceOver, stopRecording,
 * renameRecording, selectRecording.
 */
const send = vi.hoisted(() => vi.fn());
vi.mock('../bridge/bridge.svelte', () => ({ bridge: { send } }));

import { describe, expect, test, vi, beforeEach } from 'vitest';
import { RecordingState } from './recording-state.svelte';
import type { RecordingMeta } from '../_generated/state';

beforeEach(() => send.mockClear());

function makeMeta(id: string, name = 'Recording'): RecordingMeta {
  return {
    recording_id: id,
    name,
    description: '',
    status: 'stopped',
    started_at_ms: 1000,
    entry_count: 0,
  } as unknown as RecordingMeta;
}

// ---------------------------------------------------------------------------
// hydrate
// ---------------------------------------------------------------------------

describe('RecordingState.hydrate', () => {
  test('hydrate sets activeRecordingId', () => {
    const rs = new RecordingState();
    rs.hydrate({ active_recording_id: 'rec-1', recordings: [] });
    expect(rs.activeRecordingId).toBe('rec-1');
  });

  test('hydrate sets recordings list', () => {
    const rs = new RecordingState();
    rs.hydrate({ recordings: [makeMeta('rec-1')], active_recording_id: null });
    expect(rs.recordings).toHaveLength(1);
    expect(rs.recordings[0]!.recording_id).toBe('rec-1');
  });

  test('hydrate sets activeDetailRecordingId', () => {
    const rs = new RecordingState();
    rs.hydrate({ recordings: [], active_detail_recording_id: 'rec-detail', active_recording_id: null });
    expect(rs.activeDetailRecordingId).toBe('rec-detail');
  });

  test('hydrate sets activeReplayProgress (null clears it)', () => {
    const rs = new RecordingState();
    rs.hydrate({ recordings: [], active_recording_id: null, active_replay_progress: null });
    expect(rs.activeReplayProgress).toBeNull();
  });

  test('hydrate with empty view is tolerant', () => {
    const rs = new RecordingState();
    rs.hydrate({});
    expect(rs.activeRecordingId).toBeNull();
    expect(rs.recordings).toEqual([]);
  });
});

// ---------------------------------------------------------------------------
// isRecording / activeRecording derived
// ---------------------------------------------------------------------------

describe('RecordingState derived accessors', () => {
  test('isRecording is false when activeRecordingId is null', () => {
    const rs = new RecordingState();
    rs.hydrate({ recordings: [], active_recording_id: null });
    expect(rs.isRecording).toBe(false);
  });

  test('isRecording is true when activeRecordingId is set', () => {
    const rs = new RecordingState();
    rs.hydrate({ recordings: [makeMeta('rec-1')], active_recording_id: 'rec-1' });
    expect(rs.isRecording).toBe(true);
  });

  test('activeRecording returns meta for active recording', () => {
    const rs = new RecordingState();
    const meta = makeMeta('rec-1', 'My Recording');
    rs.hydrate({ recordings: [meta], active_recording_id: 'rec-1' });
    expect(rs.activeRecording?.name).toBe('My Recording');
  });

  test('activeRecording returns null when no active recording', () => {
    const rs = new RecordingState();
    rs.hydrate({ recordings: [makeMeta('rec-1')], active_recording_id: null });
    expect(rs.activeRecording).toBeNull();
  });
});

// ---------------------------------------------------------------------------
// intent methods
// ---------------------------------------------------------------------------

describe('RecordingState.startRecording', () => {
  test('sends recording_start_requested with default name/description', () => {
    const rs = new RecordingState();
    rs.startRecording();
    expect(send).toHaveBeenCalledWith(
      expect.objectContaining({ kind: 'recording_start_requested', name: 'New Recording', description: '' })
    );
  });

  test('sends recording_start_requested with custom name/description', () => {
    const rs = new RecordingState();
    rs.startRecording('My Session', 'notes here');
    expect(send).toHaveBeenCalledWith(
      expect.objectContaining({ kind: 'recording_start_requested', name: 'My Session', description: 'notes here' })
    );
  });
});

describe('RecordingState.startRecordingWithVoiceOver', () => {
  test('sends recording_start_requested with with_voice_over=true', () => {
    const rs = new RecordingState();
    rs.startRecordingWithVoiceOver(null);
    expect(send).toHaveBeenCalledWith(
      expect.objectContaining({ kind: 'recording_start_requested', with_voice_over: true, mic_device_id: null })
    );
  });

  test('sends mic_device_id when provided', () => {
    const rs = new RecordingState();
    rs.startRecordingWithVoiceOver(2, 'Voice Session', 'voice notes');
    expect(send).toHaveBeenCalledWith(
      expect.objectContaining({
        kind: 'recording_start_requested',
        with_voice_over: true,
        mic_device_id: 2,
        name: 'Voice Session',
        description: 'voice notes',
      })
    );
  });
});

describe('RecordingState.stopRecording', () => {
  test('is a no-op when no active recording', () => {
    const rs = new RecordingState();
    rs.stopRecording();
    expect(send).not.toHaveBeenCalled();
  });

  test('sends recording_stop_requested with activeRecordingId', () => {
    const rs = new RecordingState();
    rs.hydrate({ recordings: [], active_recording_id: 'rec-live' });
    rs.stopRecording();
    expect(send).toHaveBeenCalledWith(
      expect.objectContaining({ kind: 'recording_stop_requested', recording_id: 'rec-live' })
    );
  });
});

describe('RecordingState.renameRecording', () => {
  test('sends recording_rename_requested with id, name, description', () => {
    const rs = new RecordingState();
    rs.renameRecording('rec-1', 'New Name', 'New Desc');
    expect(send).toHaveBeenCalledWith(
      expect.objectContaining({
        kind: 'recording_rename_requested',
        recording_id: 'rec-1',
        name: 'New Name',
        description: 'New Desc',
      })
    );
  });
});

describe('RecordingState.selectRecording', () => {
  test('sends recording_selected_requested with id', () => {
    const rs = new RecordingState();
    rs.selectRecording('rec-1');
    expect(send).toHaveBeenCalledWith(
      expect.objectContaining({ kind: 'recording_selected_requested', recording_id: 'rec-1' })
    );
  });

  test('sends recording_selected_requested with null to deselect', () => {
    const rs = new RecordingState();
    rs.selectRecording(null);
    expect(send).toHaveBeenCalledWith(
      expect.objectContaining({ kind: 'recording_selected_requested', recording_id: null })
    );
  });
});
