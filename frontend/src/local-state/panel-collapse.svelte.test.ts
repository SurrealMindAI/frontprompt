/**
 * panelCollapse aggregator tests (BUG 3).
 *
 * panelCollapse.active is the single "HUD panels should retract to minimal
 * Laschen" predicate consumed by Panel.svelte / PanelTab.svelte / App.svelte.
 * Sources: pageTool.active (full-viewport tools) OR recorder.isActive (an active
 * recording — the overlay gets out of the way like quick-comment mode does).
 *
 * We drive the REAL reactive sources (backendState + regionDraft) so $derived
 * propagation is exercised, mirroring recorder.svelte.test.ts.
 */

// Mock the bridge so backend-state intents don't need window.__fp.
const send = vi.hoisted(() => vi.fn());
vi.mock('../bridge/bridge.svelte', () => ({ bridge: { send } }));

import { describe, expect, test, vi, beforeEach } from 'vitest';
import { panelCollapse } from './panel-collapse.svelte';
import { recorder } from './recorder.svelte';
import { backendState } from '../backend-state/backend-state.svelte';
import { regionDraft } from '../services/regions';

beforeEach(() => {
  send.mockClear();
  backendState.recordings.activeRecordingId = null;
  backendState.inspector.active = false;
  regionDraft.drafting = false;
});

describe('panelCollapse.active', () => {
  test('is false when nothing is active', () => {
    expect(panelCollapse.active).toBe(false);
  });

  test('is true when a recording is active (collapse-on-record)', () => {
    backendState.recordings.activeRecordingId = 'rec-123';
    expect(recorder.isActive).toBe(true);
    expect(panelCollapse.active).toBe(true);
  });

  test('restores to false when the recording stops', () => {
    backendState.recordings.activeRecordingId = 'rec-123';
    expect(panelCollapse.active).toBe(true);
    backendState.recordings.activeRecordingId = null;
    expect(panelCollapse.active).toBe(false);
  });

  test('is true when a full-viewport tool (inspector) is active', () => {
    backendState.inspector.active = true;
    expect(panelCollapse.active).toBe(true);
  });

  test('stays true while either source is active (OR semantics)', () => {
    backendState.inspector.active = true;
    backendState.recordings.activeRecordingId = 'rec-123';
    expect(panelCollapse.active).toBe(true);
    backendState.inspector.active = false;
    // recording still active → still collapsed
    expect(panelCollapse.active).toBe(true);
  });
});
