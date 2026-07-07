/**
 * panelCollapse aggregator tests.
 *
 * panelCollapse.active is the single "HUD panels should retract to minimal
 * Laschen" predicate consumed by Panel.svelte / PanelTab.svelte / App.svelte.
 * Its ONLY source is pageTool.active (a full-viewport tool — Inspector or
 * Region-Draw — owns the viewport).
 *
 * Recording is DELIBERATELY NOT a collapse reason (regression-pin for the
 * "pick/region dead during recording" bug): recording is an orthogonal axis, so
 * an active recording must NOT retract the LEFT panel that hosts the pick/region
 * tools — otherwise .content--collapsed{pointer-events:none} swallows every click
 * on those tools. The recording-specific chrome is the FloatingRecorderToolbar
 * (gated on recorder.isActive separately), not a HUD collapse.
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

  test('is true when a full-viewport tool (inspector) is active', () => {
    backendState.inspector.active = true;
    expect(panelCollapse.active).toBe(true);
  });

  test('is true when region-draw is active', () => {
    regionDraft.drafting = true;
    expect(panelCollapse.active).toBe(true);
  });

  // ── Regression pin: recording must NOT collapse the HUD ──────────────────
  // Folding recorder.isActive into this boolean retracted the LEFT tool panel
  // during recording, killing pick/region clicks (content--collapsed →
  // pointer-events:none). The tools must stay reachable while recording.
  test('a recording alone does NOT collapse the HUD (tool strip stays reachable)', () => {
    backendState.recordings.activeRecordingId = 'rec-123';
    expect(recorder.isActive).toBe(true);
    expect(panelCollapse.active).toBe(false);
  });

  test('recording does not contribute — active follows pageTool only', () => {
    // inspector active → collapsed
    backendState.inspector.active = true;
    backendState.recordings.activeRecordingId = 'rec-123';
    expect(panelCollapse.active).toBe(true);
    // inspector off → NOT collapsed even though the recording is still running
    backendState.inspector.active = false;
    expect(recorder.isActive).toBe(true);
    expect(panelCollapse.active).toBe(false);
  });
});
