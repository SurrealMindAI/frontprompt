/**
 * NodePicker unit tests (vitest + jsdom + @testing-library/svelte).
 *
 * Test-Surface:
 *   - Renders with root .node-picker class
 *   - Shows chip with region note when a region endpoint is selected
 *   - Shows chip with region fallback label when note is absent
 *   - Shows chip with pick info when a pick endpoint is selected
 */
import { describe, expect, test, vi, afterEach } from 'vitest';
import { render, cleanup } from '@testing-library/svelte';
import NodePicker from './NodePicker.svelte';
import type { EndpointRef } from '../../services/relations/relation-draft.svelte';

// ---------------------------------------------------------------------------
// Mocks
// ---------------------------------------------------------------------------

// Mock backendState so we control picks + regions in tests
vi.mock('../../backend-state/backend-state.svelte', () => ({
  backendState: {
    inspector: {
      picks: [
        {
          pick_id: 'pick-001',
          element: {
            selector: '#btn',
            fingerprint: {
              tag: 'button',
              attributes: {},
              text: '',
              path: [],
              parent_name: null,
              parent_attribs: {},
              parent_text: '',
              siblings: [],
              children: [],
            },
            text_snippet: '',
            rect: { x: 0, y: 0, width: 0, height: 0 },
          },
          url: 'https://example.com',
          timestamp_ms: 0,
          comment: '',
          color_index: 0,
        },
        {
          pick_id: 'pick-002',
          element: {
            selector: '#header',
            fingerprint: {
              tag: 'h1',
              attributes: {},
              text: '',
              path: [],
              parent_name: null,
              parent_attribs: {},
              parent_text: '',
              siblings: [],
              children: [],
            },
            text_snippet: '',
            rect: { x: 0, y: 0, width: 0, height: 0 },
          },
          url: 'https://example.com',
          timestamp_ms: 0,
          comment: '',
          color_index: 1,
        },
      ],
      regions: [
        {
          region_id: 'region-abcdef',
          rect: { x: 0, y: 0, width: 100, height: 50 },
          member_pick_ids: ['pick-001'],
          timestamp_ms: 0,
          color_index: 0,
          note: 'Hero section',
          viewport_snapshot: null,
        },
        {
          region_id: 'region-no-note',
          rect: { x: 0, y: 0, width: 100, height: 50 },
          member_pick_ids: [],
          timestamp_ms: 0,
          color_index: 1,
          note: null,
          viewport_snapshot: null,
        },
      ],
    },
  },
}));

// Mock pickClaim — claim coordination is not tested here
vi.mock('../../local-state/pick-claim.svelte', () => ({
  pickClaim: {
    isClaimedBy: () => false,
    current: null,
    acquire: vi.fn(),
    release: vi.fn(),
  },
}));

afterEach(() => {
  cleanup();
});

// ---------------------------------------------------------------------------
// Tests
// ---------------------------------------------------------------------------

describe('NodePicker', () => {
  test('renders with .node-picker root class', () => {
    const onChange = vi.fn();
    const { container } = render(NodePicker, {
      props: { value: null, onChange },
    });
    expect(container.querySelector('.node-picker')).not.toBeNull();
  });

  test('shows label when provided', () => {
    const onChange = vi.fn();
    const { container } = render(NodePicker, {
      props: { value: null, onChange, label: 'Source' },
    });
    expect(container.textContent).toContain('Source');
  });

  test('shows region chip with note when a region endpoint is selected', () => {
    const regionRef: EndpointRef = { id: 'region-abcdef', kind: 'region' };
    const onChange = vi.fn();
    const { container } = render(NodePicker, {
      props: { value: regionRef, onChange, label: 'Source' },
    });
    // Chip should show "Hero section" (the region's note)
    expect(container.textContent).toContain('Hero section');
    // Chip should show the "region" kind badge
    expect(container.textContent).toContain('region');
  });

  test('shows region chip with fallback label (region:<short-id>) when note is absent', () => {
    const regionRef: EndpointRef = { id: 'region-no-note', kind: 'region' };
    const onChange = vi.fn();
    const { container } = render(NodePicker, {
      props: { value: regionRef, onChange },
    });
    // Fallback: "region:" prefix + first 6 chars of "region-no-note" = "region"
    expect(container.textContent).toContain('region:region');
  });

  test('shows pick chip with selector when a pick endpoint is selected', () => {
    const pickRef: EndpointRef = { id: 'pick-001', kind: 'pick' };
    const onChange = vi.fn();
    const { container } = render(NodePicker, {
      props: { value: pickRef, onChange, label: 'Target' },
    });
    expect(container.textContent).toContain('#btn');
    // Pick chip shows "pick" kind badge
    expect(container.textContent).toContain('pick');
  });
});
