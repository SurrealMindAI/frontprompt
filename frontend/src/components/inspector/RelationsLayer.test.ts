/**
 * RelationsLayer smoke tests.
 *
 * RelationsLayer renders SvgRenderer only when hasContent is true:
 *   hasContent = (relationsVisible && commands.length > 0)
 *             || (regionsVisible && regions.length > 0)
 *             || (picksVisible && picks.length > 0)
 *
 * Tests cover: hasContent=false (no SVG), hasContent=true via picks,
 * hasContent=true via regions, picksVisible derived from quickCommentMode.active.
 */
const send = vi.hoisted(() => vi.fn());
vi.mock('../../bridge/bridge.svelte', () => ({ bridge: { send } }));

// Mock positionService / planPaths so no real DOM lookups happen
vi.mock('../../services/relations', () => ({
  planPaths: () => [],
  positionService: {
    centerForNode: () => null,
    rectForNode: () => null,
    liveRectForPick: () => null,
    liveRectForRegion: () => null,
    liveElementForPick: () => null,
  },
  positionTracker: { tick: 0 },
  setupPositionTracker: () => () => {},
}));

import { describe, expect, test, afterEach, beforeEach, vi } from 'vitest';
import { render, cleanup } from '@testing-library/svelte';
import RelationsLayer from './RelationsLayer.svelte';
import { backendState } from '../../backend-state/backend-state.svelte';
import { uiPrefs } from '../../local-state/ui-prefs.svelte';
import { quickCommentMode } from '../../local-state/quick-comment-mode.svelte';

afterEach(() => {
  cleanup();
  send.mockClear();
  backendState.inspector.picks = [];
  backendState.inspector.regions = [];
  backendState.inspector.relations = [];
  // Reset uiPrefs to safe defaults
  uiPrefs.picksVisible = true;
  uiPrefs.regionsVisible = true;
  uiPrefs.relationsVisible = true;
  quickCommentMode.active = false;
});

beforeEach(() => {
  backendState.inspector.picks = [];
  backendState.inspector.regions = [];
  backendState.inspector.relations = [];
});

describe('RelationsLayer — hasContent=false (nothing to render)', () => {
  test('renders no .relations-svg when no picks, regions, or relations', () => {
    // All empty → hasContent=false → SvgRenderer not mounted
    uiPrefs.picksVisible = true;
    uiPrefs.regionsVisible = true;
    uiPrefs.relationsVisible = true;
    backendState.inspector.picks = [];
    backendState.inspector.regions = [];
    backendState.inspector.relations = [];
    const { container } = render(RelationsLayer);
    // SvgRenderer renders .relations-svg — should not be present
    expect(container.querySelector('.relations-svg')).toBeNull();
  });
});

describe('RelationsLayer — hasContent=true via picks', () => {
  test('renders .relations-svg when picks exist and picksVisible=true', () => {
    uiPrefs.picksVisible = true;
    backendState.inspector.picks = [
      {
        pick_id: 'p1',
        url: 'https://example.com',
        timestamp_ms: 0,
        element: {
          selector: 'div.main',
          fingerprint: { tag: 'div' },
          text_snippet: '',
          rect: { x: 0, y: 0, width: 100, height: 50 },
        },
        comment: '',
        color_index: 0,
        origin_session: null,
      } as any,
    ];
    const { container } = render(RelationsLayer);
    expect(container.querySelector('.relations-svg')).not.toBeNull();
  });

  test('does NOT render .relations-svg when picks exist but picksVisible=false and no regions/relations', () => {
    uiPrefs.picksVisible = false;
    uiPrefs.regionsVisible = false;
    uiPrefs.relationsVisible = false;
    backendState.inspector.picks = [
      {
        pick_id: 'p1',
        url: 'https://example.com',
        timestamp_ms: 0,
        element: {
          selector: 'div.main',
          fingerprint: { tag: 'div' },
          text_snippet: '',
          rect: { x: 0, y: 0, width: 100, height: 50 },
        },
        comment: '',
        color_index: 0,
        origin_session: null,
      } as any,
    ];
    const { container } = render(RelationsLayer);
    expect(container.querySelector('.relations-svg')).toBeNull();
  });
});

describe('RelationsLayer — hasContent=true via regions', () => {
  test('renders .relations-svg when regions exist and regionsVisible=true', () => {
    uiPrefs.picksVisible = false;
    uiPrefs.relationsVisible = false;
    uiPrefs.regionsVisible = true;
    backendState.inspector.regions = [
      {
        region_id: 'r1',
        name: 'Test Region',
        description: '',
        member_pick_ids: [],
        origin_session: null,
        color_index: 0,
      } as any,
    ];
    const { container } = render(RelationsLayer);
    expect(container.querySelector('.relations-svg')).not.toBeNull();
  });
});

describe('RelationsLayer — picksVisible derived from quickCommentMode', () => {
  test('renders .relations-svg via quickCommentMode.active=true even when picksVisible=false', () => {
    // picksVisible = uiPrefs.picksVisible || quickCommentMode.active
    // If picksVisible=false but quickCommentMode.active=true → picksVisible becomes true
    uiPrefs.picksVisible = false;
    uiPrefs.regionsVisible = false;
    uiPrefs.relationsVisible = false;
    quickCommentMode.active = true;
    backendState.inspector.picks = [
      {
        pick_id: 'p-quick',
        url: 'https://example.com',
        timestamp_ms: 0,
        element: {
          selector: 'button.cta',
          fingerprint: { tag: 'button' },
          text_snippet: '',
          rect: { x: 0, y: 0, width: 50, height: 30 },
        },
        comment: '',
        color_index: 1,
        origin_session: null,
      } as any,
    ];
    const { container } = render(RelationsLayer);
    expect(container.querySelector('.relations-svg')).not.toBeNull();
    quickCommentMode.active = false;
  });
});
