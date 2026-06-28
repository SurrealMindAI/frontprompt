/**
 * UiPrefs — tests covering all tab-switching, toggle, and hover methods.
 *
 * uiPrefs is a singleton; each test resets relevant fields in beforeEach
 * to ensure isolation. No bridge needed — pure local state.
 */
import { describe, expect, test, beforeEach } from 'vitest';
import { uiPrefs } from './ui-prefs.svelte';

beforeEach(() => {
  // Reset to known initial state between tests
  uiPrefs.leftPanelTab = 'picks';
  uiPrefs.relationsVisible = true;
  uiPrefs.regionsVisible = true;
  uiPrefs.picksVisible = true;
  uiPrefs.hoveredRelationId = null;
  uiPrefs.activeDetailReplayId = null;
});

// ---------------------------------------------------------------------------
// Initial state
// ---------------------------------------------------------------------------

describe('uiPrefs initial state', () => {
  test('leftPanelTab defaults to picks', () => {
    expect(uiPrefs.leftPanelTab).toBe('picks');
  });

  test('relationsVisible defaults to true', () => {
    expect(uiPrefs.relationsVisible).toBe(true);
  });

  test('regionsVisible defaults to true', () => {
    expect(uiPrefs.regionsVisible).toBe(true);
  });

  test('picksVisible defaults to true', () => {
    expect(uiPrefs.picksVisible).toBe(true);
  });

  test('hoveredRelationId defaults to null', () => {
    expect(uiPrefs.hoveredRelationId).toBeNull();
  });

  test('activeDetailReplayId defaults to null', () => {
    expect(uiPrefs.activeDetailReplayId).toBeNull();
  });
});

// ---------------------------------------------------------------------------
// Tab switching helpers
// ---------------------------------------------------------------------------

describe('uiPrefs tab switching', () => {
  test('showEventsTab sets leftPanelTab to events', () => {
    uiPrefs.showEventsTab();
    expect(uiPrefs.leftPanelTab).toBe('events');
  });

  test('showPicksTab sets leftPanelTab to picks', () => {
    uiPrefs.leftPanelTab = 'events';
    uiPrefs.showPicksTab();
    expect(uiPrefs.leftPanelTab).toBe('picks');
  });

  test('showRelationsTab sets leftPanelTab to relations', () => {
    uiPrefs.showRelationsTab();
    expect(uiPrefs.leftPanelTab).toBe('relations');
  });

  test('showRegionsTab sets leftPanelTab to regions', () => {
    uiPrefs.showRegionsTab();
    expect(uiPrefs.leftPanelTab).toBe('regions');
  });

  test('showRecordingsTab sets leftPanelTab to recordings', () => {
    uiPrefs.showRecordingsTab();
    expect(uiPrefs.leftPanelTab).toBe('recordings');
  });

  test('showSettingsTab sets leftPanelTab to settings', () => {
    uiPrefs.showSettingsTab();
    expect(uiPrefs.leftPanelTab).toBe('settings');
  });
});

// ---------------------------------------------------------------------------
// Toggle visibility helpers
// ---------------------------------------------------------------------------

describe('uiPrefs visibility toggles', () => {
  test('toggleRelationsVisible flips relationsVisible', () => {
    uiPrefs.relationsVisible = true;
    uiPrefs.toggleRelationsVisible();
    expect(uiPrefs.relationsVisible).toBe(false);
    uiPrefs.toggleRelationsVisible();
    expect(uiPrefs.relationsVisible).toBe(true);
  });

  test('toggleRegionsVisible flips regionsVisible', () => {
    uiPrefs.regionsVisible = true;
    uiPrefs.toggleRegionsVisible();
    expect(uiPrefs.regionsVisible).toBe(false);
  });

  test('togglePicksVisible flips picksVisible', () => {
    uiPrefs.picksVisible = true;
    uiPrefs.togglePicksVisible();
    expect(uiPrefs.picksVisible).toBe(false);
  });
});

// ---------------------------------------------------------------------------
// hoverRelation
// ---------------------------------------------------------------------------

describe('uiPrefs.hoverRelation', () => {
  test('sets hoveredRelationId to a relation id', () => {
    uiPrefs.hoverRelation('rel-abc');
    expect(uiPrefs.hoveredRelationId).toBe('rel-abc');
  });

  test('clears hoveredRelationId when passed null', () => {
    uiPrefs.hoverRelation('rel-abc');
    uiPrefs.hoverRelation(null);
    expect(uiPrefs.hoveredRelationId).toBeNull();
  });
});

// ---------------------------------------------------------------------------
// showDetailReplay
// ---------------------------------------------------------------------------

describe('uiPrefs.showDetailReplay', () => {
  test('sets activeDetailReplayId to a replay id', () => {
    uiPrefs.showDetailReplay('replay-001');
    expect(uiPrefs.activeDetailReplayId).toBe('replay-001');
  });

  test('clears activeDetailReplayId when passed null', () => {
    uiPrefs.showDetailReplay('replay-001');
    uiPrefs.showDetailReplay(null);
    expect(uiPrefs.activeDetailReplayId).toBeNull();
  });
});
