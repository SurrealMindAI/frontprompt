/**
 * svg-renderer.test.ts — branch coverage for SvgRenderer's conditional paths.
 *
 * Covers:
 *  - showPickBorders false branch (no pick rects rendered)
 *  - Pick rects with activePickId match (selected state)
 *  - Region rects with activeRegionId match (active state)
 *  - Commands: directed vs undirected, with note vs without, hovered vs not
 *  - truncate() function branches
 *  - ownership gate for commands
 *
 * positionService.liveRectForPick is mocked to a concrete rect for all picks.
 * positionService.liveRectForRegion is mocked similarly for regions.
 */
import { afterEach, beforeEach, describe, expect, test, vi } from 'vitest';
import { render, cleanup } from '@testing-library/svelte';
import SvgRenderer from './svg-renderer.svelte';
import { positionService } from '../position-service.svelte';
import { overlayContext } from '../../context/overlay-context.svelte';
import type { Pick, Region } from '../../../_generated/state';
import type { DrawCommand } from '../path-planner';

const SESSION = 'sess-main';

afterEach(() => {
  cleanup();
  vi.restoreAllMocks();
  overlayContext.resetForTests();
});

beforeEach(() => {
  vi.spyOn(positionService, 'liveRectForPick').mockReturnValue({ x: 10, y: 20, width: 100, height: 50 });
  vi.spyOn(positionService, 'liveRectForRegion').mockReturnValue({ x: 5, y: 5, width: 200, height: 100 });
  vi.spyOn(positionService, 'liveElementForPick').mockReturnValue(document.body);
  overlayContext.setForTests({
    url: new URL('https://example.com/'),
    currentSessionId: SESSION,
  });
});

function makePick(pickId: string, colorIndex = 0): Pick {
  return {
    pick_id: pickId,
    url: 'https://example.com/',
    timestamp_ms: 0,
    element: {
      selector: 'div',
      fingerprint: { tag: 'div' },
      text_snippet: '',
      rect: { x: 0, y: 0, width: 0, height: 0 },
    },
    comment: '',
    color_index: colorIndex,
    origin_session: SESSION,
  };
}

function makeRegion(regionId: string): Region {
  return {
    region_id: regionId,
    rect: { x: 0, y: 0, width: 100, height: 50 },
    member_pick_ids: [],
    timestamp_ms: 0,
    origin_session: SESSION,
    color_index: 1,
  };
}

function makeCommand(
  opts: Partial<{
    relationId: string;
    kind: 'relates_to' | 'triggers' | 'part_of';
    isDirected: boolean;
    note: string | null;
    origin_session: string | null;
  }> = {}
): DrawCommand {
  return {
    relationId: opts.relationId ?? 'rel-1',
    kind: opts.kind ?? 'relates_to',
    isDirected: opts.isDirected ?? false,
    source: { cx: 10, cy: 10 },
    target: { cx: 100, cy: 100 },
    midpoint: { cx: 55, cy: 55 },
    pathD: 'M 10 10 Q 55 55 100 100',
    note: opts.note ?? null,
    origin_session: opts.origin_session ?? SESSION,
  };
}

describe('SvgRenderer — showPickBorders false branch', () => {
  test('showPickBorders=false renders no pick rect boxes even with picks', () => {
    const pick = makePick('p1');
    const { container } = render(SvgRenderer, {
      props: {
        commands: [],
        hoveredRelationId: null,
        picks: [pick],
        regions: [],
        showPicks: false,
      },
    });
    expect(container.querySelectorAll('.rel-picks__box')).toHaveLength(0);
  });

  test('showPickBorders=true renders pick rect boxes for owned picks', () => {
    const pick = makePick('p1');
    const { container } = render(SvgRenderer, {
      props: {
        commands: [],
        hoveredRelationId: null,
        picks: [pick],
        regions: [],
        showPicks: true,
      },
    });
    expect(container.querySelectorAll('.rel-picks__box')).toHaveLength(1);
  });
});

describe('SvgRenderer — pick selection state', () => {
  test('activePickId match adds rel-picks__box--selected class', () => {
    const pick = makePick('p-sel', 0);
    const { container } = render(SvgRenderer, {
      props: {
        commands: [],
        hoveredRelationId: null,
        picks: [pick],
        regions: [],
        showPicks: true,
        activePickId: 'p-sel',
      },
    });
    const box = container.querySelector('.rel-picks__box');
    expect(box?.classList.contains('rel-picks__box--selected')).toBe(true);
  });

  test('non-matching activePickId does NOT add selected class', () => {
    const pick = makePick('p1', 0);
    const { container } = render(SvgRenderer, {
      props: {
        commands: [],
        hoveredRelationId: null,
        picks: [pick],
        regions: [],
        showPicks: true,
        activePickId: 'other-pick',
      },
    });
    const box = container.querySelector('.rel-picks__box');
    expect(box?.classList.contains('rel-picks__box--selected')).toBe(false);
  });

  test('activePickId=null → no selected box', () => {
    const pick = makePick('p1', 0);
    const { container } = render(SvgRenderer, {
      props: {
        commands: [],
        hoveredRelationId: null,
        picks: [pick],
        regions: [],
        showPicks: true,
        activePickId: null,
      },
    });
    const box = container.querySelector('.rel-picks__box');
    expect(box?.classList.contains('rel-picks__box--selected')).toBe(false);
  });
});

describe('SvgRenderer — region rect borders', () => {
  test('renders region rect when liveRectForRegion returns a value', () => {
    const region = makeRegion('r1');
    const { container } = render(SvgRenderer, {
      props: {
        commands: [],
        hoveredRelationId: null,
        picks: [],
        regions: [region],
      },
    });
    expect(container.querySelectorAll('.rel-regions__box')).toHaveLength(1);
  });

  test('activeRegionId match adds rel-regions__box--active class', () => {
    const region = makeRegion('r-active');
    const { container } = render(SvgRenderer, {
      props: {
        commands: [],
        hoveredRelationId: null,
        picks: [],
        regions: [region],
        activeRegionId: 'r-active',
      },
    });
    const box = container.querySelector('.rel-regions__box');
    expect(box?.classList.contains('rel-regions__box--active')).toBe(true);
  });

  test('non-matching activeRegionId does NOT add active class', () => {
    const region = makeRegion('r1');
    const { container } = render(SvgRenderer, {
      props: {
        commands: [],
        hoveredRelationId: null,
        picks: [],
        regions: [region],
        activeRegionId: 'other-region',
      },
    });
    const box = container.querySelector('.rel-regions__box');
    expect(box?.classList.contains('rel-regions__box--active')).toBe(false);
  });

  test('no region box when liveRectForRegion returns null', () => {
    vi.spyOn(positionService, 'liveRectForRegion').mockReturnValue(null);
    const region = makeRegion('r-no-rect');
    const { container } = render(SvgRenderer, {
      props: {
        commands: [],
        hoveredRelationId: null,
        picks: [],
        regions: [region],
      },
    });
    expect(container.querySelectorAll('.rel-regions__box')).toHaveLength(0);
  });
});

describe('SvgRenderer — command rendering', () => {
  test('renders .rel group for each owned command', () => {
    const cmd = makeCommand({ relationId: 'rel-1' });
    const { container } = render(SvgRenderer, {
      props: {
        commands: [cmd],
        hoveredRelationId: null,
      },
    });
    expect(container.querySelectorAll('.rel')).toHaveLength(1);
  });

  test('directed command (triggers) renders arrow marker-end on path', () => {
    const cmd = makeCommand({ kind: 'triggers', isDirected: true });
    const { container } = render(SvgRenderer, {
      props: {
        commands: [cmd],
        hoveredRelationId: null,
      },
    });
    const mainPath = container.querySelector('.rel__main');
    expect(mainPath?.getAttribute('marker-end')).toContain('arrow-triggers');
  });

  test('undirected command (relates_to) has no marker-end on path', () => {
    const cmd = makeCommand({ kind: 'relates_to', isDirected: false });
    const { container } = render(SvgRenderer, {
      props: {
        commands: [cmd],
        hoveredRelationId: null,
      },
    });
    const mainPath = container.querySelector('.rel__main');
    // relates_to is undirected → no marker-end
    expect(mainPath?.getAttribute('marker-end')).toBeFalsy();
  });

  test('command with note shows note in label text', () => {
    const cmd = makeCommand({ note: 'triggers checkout' });
    const { container } = render(SvgRenderer, {
      props: {
        commands: [cmd],
        hoveredRelationId: null,
      },
    });
    const labelText = container.querySelector('.rel__label-text');
    expect(labelText?.textContent).toContain('triggers checkout');
  });

  test('command without note shows only kind in label', () => {
    const cmd = makeCommand({ kind: 'relates_to', note: null });
    const { container } = render(SvgRenderer, {
      props: {
        commands: [cmd],
        hoveredRelationId: null,
      },
    });
    const labelText = container.querySelector('.rel__label-text');
    expect(labelText?.textContent?.trim()).toBe('relates_to');
  });

  test('hovered command adds rel--hovered class', () => {
    const cmd = makeCommand({ relationId: 'rel-hov' });
    const { container } = render(SvgRenderer, {
      props: {
        commands: [cmd],
        hoveredRelationId: 'rel-hov',
      },
    });
    const relGroup = container.querySelector('.rel');
    expect(relGroup?.classList.contains('rel--hovered')).toBe(true);
  });

  test('non-hovered command does NOT add rel--hovered class', () => {
    const cmd = makeCommand({ relationId: 'rel-1' });
    const { container } = render(SvgRenderer, {
      props: {
        commands: [cmd],
        hoveredRelationId: 'other-rel',
      },
    });
    const relGroup = container.querySelector('.rel');
    expect(relGroup?.classList.contains('rel--hovered')).toBe(false);
  });

  test('foreign-session command is not rendered', () => {
    const cmd = makeCommand({ origin_session: 'foreign-sess' });
    const { container } = render(SvgRenderer, {
      props: {
        commands: [cmd],
        hoveredRelationId: null,
      },
    });
    // Owned session is 'sess-main', foreign command should be gated out
    expect(container.querySelectorAll('.rel')).toHaveLength(0);
  });
});

describe('SvgRenderer — long note truncation (truncate() coverage)', () => {
  test('note longer than 28 chars is truncated to fit on label', () => {
    const longNote = 'this is a very very very long note that exceeds the limit';
    const cmd = makeCommand({ note: longNote });
    const { container } = render(SvgRenderer, {
      props: {
        commands: [cmd],
        hoveredRelationId: null,
      },
    });
    const labelText = container.querySelector('.rel__label-text');
    // truncate() is applied — label should not contain the full note
    expect(labelText?.textContent?.length).toBeLessThan(longNote.length + 20);
    expect(labelText?.textContent).toContain('…');
  });

  test('note of exactly 28 chars is not truncated', () => {
    const exactNote = '1234567890123456789012345678'; // 28 chars
    const cmd = makeCommand({ note: exactNote });
    const { container } = render(SvgRenderer, {
      props: {
        commands: [cmd],
        hoveredRelationId: null,
      },
    });
    const labelText = container.querySelector('.rel__label-text');
    expect(labelText?.textContent).not.toContain('…');
    expect(labelText?.textContent).toContain(exactNote);
  });
});

describe('SvgRenderer — multiple picks with different colors', () => {
  test('renders multiple owned pick boxes', () => {
    const p1 = makePick('p1', 0);
    const p2 = makePick('p2', 5);
    const { container } = render(SvgRenderer, {
      props: {
        commands: [],
        hoveredRelationId: null,
        picks: [p1, p2],
        regions: [],
        showPicks: true,
      },
    });
    expect(container.querySelectorAll('.rel-picks__box')).toHaveLength(2);
  });
});

describe('SvgRenderer — region with member_pick_ids (covers adaptedRegionColors if(mp) branch)', () => {
  test('region with member_pick_ids resolving to picks samples background from first pick', () => {
    // member_pick_ids references a pick that IS in the picks prop
    // → adaptedRegionColors iterates r.member_pick_ids, finds mp, calls liveElementForPick(mp)
    // This covers the `if (mp) el = positionService.liveElementForPick(mp)` branch (line 97)
    const pick = makePick('p-member', 2);
    const region: import('../../../_generated/state').Region = {
      region_id: 'r-with-members',
      rect: { x: 0, y: 0, width: 100, height: 50 },
      member_pick_ids: ['p-member'],  // ← references the pick
      timestamp_ms: 0,
      origin_session: SESSION,
      color_index: 0,
    };
    const { container } = render(SvgRenderer, {
      props: {
        commands: [],
        hoveredRelationId: null,
        picks: [pick],            // pick is in picks prop → mp resolves
        regions: [region],        // region references the pick
      },
    });
    // Region rect should be rendered (liveRectForRegion mock returns {x:5,y:5,...})
    expect(container.querySelectorAll('.rel-regions__box')).toHaveLength(1);
  });

  test('region with member_pick_ids not in picks prop (mp=null → no liveElementForPick call)', () => {
    // member_pick_ids references a pick NOT in the picks prop → mp=null → skips liveElementForPick
    const region: import('../../../_generated/state').Region = {
      region_id: 'r-with-missing-member',
      rect: { x: 0, y: 0, width: 100, height: 50 },
      member_pick_ids: ['nonexistent-pick-id'],
      timestamp_ms: 0,
      origin_session: SESSION,
      color_index: 1,
    };
    const { container } = render(SvgRenderer, {
      props: {
        commands: [],
        hoveredRelationId: null,
        picks: [],   // empty picks → pick lookup returns undefined (mp=null)
        regions: [region],
      },
    });
    // Region rect still renders (el=null → contrastingColor uses null el, graceful)
    expect(container.querySelectorAll('.rel-regions__box')).toHaveLength(1);
  });
});
