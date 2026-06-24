/**
 * tab-integration.test.ts — drives the exact data path the LeftPanel tabs use.
 *
 * Pure-logic assertion of the composition each tab wires (Task 5): build
 * inspector arrays with one own pick on the current hostname and one foreign
 * pick on the same hostname, set `sessionInfo`, and assert that
 * `visibleGroups(picks, { currentSessionId, currentHostname, domainOf })`
 * yields one group with two items, the foreign one `isOwned:false`.
 *
 * Full Svelte component mounting is not set up here; this asserts the same
 * `visibleGroups` + `pickDomain` composition the tabs compute in `$derived`.
 */
import { afterEach, describe, expect, test } from 'vitest';
import { visibleGroups } from './visible-groups';
import { pickDomain } from './hostname';
import { overlayContext } from '../context/overlay-context.svelte';
import type { Pick } from '../../_generated/state';

function makePick(pickId: string, url: string, originSession: string | null): Pick {
  return {
    pick_id: pickId,
    url,
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

describe('tab-integration: PicksTab data path', () => {
  afterEach(() => {
    overlayContext.resetForTests();
  });

  test('own + foreign pick on current hostname → one group, two items, foreign isOwned:false', () => {
    const session = 'sess-current';
    overlayContext.setForTests({ url: new URL('https://example.com/'), currentSessionId: session });

    const own = makePick('own', 'https://example.com/a', session);
    const foreign = makePick('foreign', 'https://example.com/b', 'sess-other');
    const picks: Pick[] = [own, foreign];

    const groups = visibleGroups(picks, {
      currentSessionId: overlayContext.currentSessionId,
      currentHostname: overlayContext.hostname() ?? '',
      domainOf: (p) => pickDomain(p),
    });

    expect(groups).toHaveLength(1);
    const group = groups[0];
    if (!group) throw new Error('missing group[0] in test result');
    expect(group.hostname).toBe('example.com');
    expect(group.items).toHaveLength(2);

    const ownItem = group.items.find((i) => i.entity.pick_id === 'own');
    const foreignItem = group.items.find((i) => i.entity.pick_id === 'foreign');

    expect(ownItem).toBeDefined();
    expect(foreignItem).toBeDefined();
    if (!ownItem || !foreignItem) return;
    expect(ownItem.isOwned).toBe(true);
    expect(foreignItem.isOwned).toBe(false);
  });
});
