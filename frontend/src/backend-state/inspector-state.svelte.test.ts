/**
 * InspectorState.submitPick dedup tests.
 *
 * Regression guard for the "3 picks made, 2 taken" bug: dedup must key on the
 * positionally-unique CSS selector, not the structural fingerprint (which excludes
 * text/rect/index and so collides for structurally identical siblings).
 */
import { describe, expect, test, vi, beforeEach } from 'vitest';

// Mock the wire bridge so submitPick's optimistic-send is a no-op spy.
const send = vi.hoisted(() => vi.fn());
vi.mock('../bridge/bridge.svelte', () => ({ bridge: { send } }));

import { InspectorState } from './inspector-state.svelte';
import type { Pick } from '../_generated/state';

/**
 * Minimal Pick fixture. The `fingerprint` is deliberately IDENTICAL across the
 * helper's calls (same tag/path/parent/siblings, no attributes) so the only thing
 * distinguishing two picks is the `selector` — exactly the collision case.
 */
function makePick(selector: string, pickId: string): Pick {
  return {
    pick_id: pickId,
    url: 'https://example.com',
    timestamp_ms: 0,
    element: {
      selector,
      fingerprint: {
        tag: 'li',
        attributes: {},
        text: '',
        path: ['ul', 'li'],
        parent_name: 'ul',
        parent_attribs: {},
        siblings: ['li', 'li', 'li'],
      },
      text_snippet: '',
      rect: { x: 0, y: 0, width: 10, height: 10 },
    },
    comment: '',
  } as unknown as Pick;
}

beforeEach(() => send.mockClear());

describe('InspectorState.submitPick dedup', () => {
  test('two picks on the same selector dedup to one pick', () => {
    const ins = new InspectorState();
    const id1 = ins.submitPick(makePick('ul > li:nth-of-type(1)', 'a'));
    const id2 = ins.submitPick(makePick('ul > li:nth-of-type(1)', 'b'));
    expect(ins.picks).toHaveLength(1);
    // Second submit reuses the first pick's identity.
    expect(id2).toBe(id1);
  });

  test('structurally identical siblings with distinct selectors are all kept (regression: 3→2)', () => {
    const ins = new InspectorState();
    ins.submitPick(makePick('ul > li:nth-of-type(1)', 'a'));
    ins.submitPick(makePick('ul > li:nth-of-type(2)', 'b'));
    ins.submitPick(makePick('ul > li:nth-of-type(3)', 'c'));
    expect(ins.picks).toHaveLength(3);
  });
});
