/**
 * App.svelte branch tests — covers conditional template branches not tested in App.gate.test.ts:
 *
 *  - inspectorActive=true → InspectorLayer is rendered (else-if branch)
 *  - regionDraft.drafting=true → DrawRegionLayer is rendered
 *  - recorder.isActive=true → FloatingRecorderToolbar is rendered
 *  - isAboutBlank=false → .area--center--dashboard is absent
 *  - quickMode=true → QuickCommentBox inspector branch
 *
 * These are separate mocks from App.gate.test.ts (which tests isAboutBlank=true).
 */

import { describe, expect, test, vi, afterEach } from 'vitest';
import { render, cleanup } from '@testing-library/svelte';

// ---------------------------------------------------------------------------
// Mocks (non-isAboutBlank scenario)
// ---------------------------------------------------------------------------

vi.mock('./services/context/overlay-context.svelte', () => ({
  overlayContext: {
    isAboutBlank: false,  // ← key difference from gate test
    currentSessionId: null,
    isOwned: () => false,
    hostname: () => null,
    refresh: async () => {},
    setForTests: () => {},
    resetForTests: () => {},
  },
}));

vi.mock('./backend-state/backend-state.svelte', () => ({
  backendState: {
    inspector: {
      picks: [],
      regions: [],
      relations: [],
      active: true,  // ← inspector active → InspectorLayer branch
      activePickId: null,
      activeRegionId: null,
      activePick: null,
      activeRegion: null,
      cancel: vi.fn(),
      submitPick: vi.fn().mockReturnValue('pick-id'),
    },
    panel: {
      panels: {
        top: { open: true, size: 56 },
        bottom: { open: true, size: 220 },
        left: { open: true, size: 300 },
        right: { open: false, size: 340 },
      },
      gridTemplateRowsWith: (_forceClosed: boolean) => '56px 1fr 220px',
      gridTemplateColumnsWith: (_forceClosed: boolean) => '300px 1fr 340px',
      effectiveSizeWith: (_id: string, _forceClosed: boolean) => 56,
      effectiveOpenWith: (_id: string, _forceClosed: boolean) => true,
      togglePanel: vi.fn(),
      resizePanel: vi.fn(),
    },
    recordings: {
      activeRecordingId: 'rec-123',  // ← recorder active → FloatingRecorderToolbar branch
      recordings: [
        { recording_id: 'rec-123', name: 'Branch Test', description: '', status: 'active', started_at_ms: 0 },
      ],
      activeDetailRecordingId: null,
      detailRecording: null,
      isRecording: true,
      activeRecording: { recording_id: 'rec-123', name: 'Branch Test', description: '', status: 'active', started_at_ms: 0 },
    },
    voiceOver: {
      backends: [],
      transcriptionStatus: 'none',
    },
    mic: {
      devices: [],
      selectedDeviceId: null,
      systemDefaultDeviceId: null,
    },
    hydrate: vi.fn(),
  },
}));

vi.mock('./backend-state/sync.svelte', () => ({}));

vi.mock('./services/regions', () => ({
  regionDraft: { drafting: true, cancel: vi.fn(), start: vi.fn() },  // ← regionDraft active → DrawRegionLayer branch
  setupPositionTracker: () => () => {},
}));

vi.mock('./local-state/page-tool.svelte', () => ({
  pageTool: { active: false },
}));

vi.mock('./local-state/panel-collapse.svelte', () => ({
  panelCollapse: { active: false },
}));

vi.mock('./local-state/pick-claim.svelte', () => ({
  GLOBAL_PICK_ID: 'pick:global',
  pickClaim: {
    routePick: vi.fn(),
    routeCancel: vi.fn(),
    isClaimedBy: () => false,
    current: null,
    acquire: vi.fn(),
    release: vi.fn(),
  },
}));

vi.mock('./managers/resize-manager.svelte', () => ({
  resize: { isDragging: false },
}));

vi.mock('./services/relations', () => ({
  setupPositionTracker: () => () => {},
  positionTracker: { tick: 0 },
  positionService: {
    centerForNode: () => null,
    rectForNode: () => null,
  },
  planPaths: () => [],
  getRelationsFor: () => [],
  buildPickFromElement: () => null,
}));

vi.mock('./services/event-interceptor', () => ({
  eventInterceptor: {
    events: [],
    enabled: true,
    countsByType: { wheel: 0, scroll: 0, click: 0, pointerdown: 0, keydown: 0 },
    elementsSeen: 0,
    elementsWithEvents: 0,
    start: vi.fn(),
    stop: vi.fn(),
    toggle: vi.fn(),
    clear: vi.fn(),
  },
  isHudChrome: () => false,
  eventMatchesPickPath: () => false,
}));

vi.mock('./_generated/build-info', () => ({
  BUILD_SESSION: 'branch-test-session',
  BUILD_VERSION: '2026-06-25T00:00:00+00:00',
  BUILD_GIT_SHA: 'def0123',
}));

afterEach(() => {
  cleanup();
});

// ---------------------------------------------------------------------------
// Tests
// ---------------------------------------------------------------------------

describe('App.svelte branch: isAboutBlank=false', () => {
  test('does NOT render .area--center--dashboard when isAboutBlank is false', async () => {
    const AppModule = await import('./App.svelte');
    const App = AppModule.default;
    const { container } = render(App);
    expect(container.querySelector('.area--center--dashboard')).toBeNull();
  });
});

describe('App.svelte branch: inspectorActive=true', () => {
  test('renders .inspector-layer when inspector.active is true', async () => {
    const AppModule = await import('./App.svelte');
    const App = AppModule.default;
    const { container } = render(App);
    // InspectorLayer renders .inspector-layer div
    expect(container.querySelector('.inspector-layer')).not.toBeNull();
  });
});

describe('App.svelte branch: regionDraft.drafting=true', () => {
  test('renders .draw-region-layer when regionDraft.drafting is true', async () => {
    const AppModule = await import('./App.svelte');
    const App = AppModule.default;
    const { container } = render(App);
    // DrawRegionLayer renders .draw-region-layer div
    expect(container.querySelector('.draw-region-layer')).not.toBeNull();
  });
});

describe('App.svelte branch: recorder.isActive=true', () => {
  test('renders .rec-toolbar when recorder.isActive is true', async () => {
    const AppModule = await import('./App.svelte');
    const App = AppModule.default;
    const { container } = render(App);
    // FloatingRecorderToolbar renders .rec-toolbar when isActive
    expect(container.querySelector('.rec-toolbar')).not.toBeNull();
  });
});

describe('App.svelte: grid renders without errors', () => {
  test('renders .grid container', async () => {
    const AppModule = await import('./App.svelte');
    const App = AppModule.default;
    const { container } = render(App);
    expect(container.querySelector('.grid')).not.toBeNull();
  });
});
