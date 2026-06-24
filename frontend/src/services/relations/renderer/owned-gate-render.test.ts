/**
 * owned-gate-render.test.ts — end-to-end render-gate regression for the
 * domain-scoped-visibility bug (fix/overlay-context-gating).
 *
 * Bug: foreign-session picks rendered overlay boxes (measured 96 SVG rects for
 * 1 owned pick) because the gate consulted a stale mount-time `sessionInfo`
 * snapshot that had degraded to null → render-all.
 *
 * This test mounts the real SvgRenderer with persisted FOREIGN + OWNED picks
 * and a known current session id (sourced through the OverlayContext, which is
 * how the gate now decides). It asserts:
 *   - the foreign pick renders NO box
 *   - the owned pick DOES render a box
 *
 * positionService.liveRectForPick is mocked to a concrete rect for every pick
 * so the only variable under test is the ownership gate (jsdom has no layout).
 */
import { afterEach, beforeEach, describe, expect, test, vi } from 'vitest';
import { render, cleanup } from '@testing-library/svelte';
import SvgRenderer from './svg-renderer.svelte';
import { positionService } from '../position-service.svelte';
import { overlayContext } from '../../context/overlay-context.svelte';
import type { Pick } from '../../../_generated/state';

afterEach(() => {
  cleanup();
  vi.restoreAllMocks();
  overlayContext.resetForTests();
});

beforeEach(() => {
  // Every pick resolves to a real rect — so a missing box can only be the
  // ownership gate, never a null live-rect.
  vi.spyOn(positionService, 'liveRectForPick').mockReturnValue({ x: 1, y: 2, width: 3, height: 4 });
});

function makePick(pickId: string, originSession: string | null): Pick {
  return {
    pick_id: pickId,
    url: 'https://example.com/x',
    timestamp_ms: 0,
    element: {
      selector: 'div',
      fingerprint: { tag: 'div' },
      text_snippet: '',
      rect: { x: 0, y: 0, width: 0, height: 0 },
    },
    comment: '',
    color_index: 0,
    origin_session: originSession,
  };
}

describe('SvgRenderer ownership gate', () => {
  test('foreign-session picks render NO box; owned picks DO', () => {
    const session = 'sess-current';
    overlayContext.setForTests({
      url: new URL('https://example.com/x'),
      currentSessionId: session,
    });

    const owned = makePick('owned', session);
    const foreign = makePick('foreign', 'sess-other');

    const { container } = render(SvgRenderer, {
      props: {
        commands: [],
        hoveredRelationId: null,
        picks: [owned, foreign],
        regions: [],
        showPicks: true,
      },
    });

    const boxes = container.querySelectorAll('.rel-picks__box');
    // Exactly one box: the owned pick. The foreign pick is gated out.
    expect(boxes).toHaveLength(1);
  });

  test('null current session → degrade to render all (both boxes)', () => {
    overlayContext.setForTests({ url: new URL('https://example.com/x'), currentSessionId: null });

    const a = makePick('a', 'sess-x');
    const b = makePick('b', 'sess-y');

    const { container } = render(SvgRenderer, {
      props: {
        commands: [],
        hoveredRelationId: null,
        picks: [a, b],
        regions: [],
        showPicks: true,
      },
    });

    expect(container.querySelectorAll('.rel-picks__box')).toHaveLength(2);
  });
});
