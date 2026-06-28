/**
 * EventsTab smoke tests.
 *
 * Tests the empty state UI: filter controls, pause/clear buttons,
 * empty list state, and basic filter interactions.
 */
const send = vi.hoisted(() => vi.fn());
vi.mock('../../../bridge/bridge.svelte', () => ({ bridge: { send } }));

import { describe, expect, test, afterEach, beforeEach } from 'vitest';
import { render, cleanup, fireEvent } from '@testing-library/svelte';
import EventsTab from './EventsTab.svelte';
import { backendState } from '../../../backend-state/backend-state.svelte';
import { eventInterceptor } from '../../../services/event-interceptor';

afterEach(() => {
  cleanup();
  send.mockClear();
  eventInterceptor.clear();
});

beforeEach(() => {
  backendState.inspector.picks = [];
  eventInterceptor.clear();
});

describe('EventsTab — controls bar', () => {
  test('renders the .controls container', () => {
    const { container } = render(EventsTab);
    expect(container.querySelector('.controls')).not.toBeNull();
  });

  test('renders pause button with aria-label', () => {
    const { container } = render(EventsTab);
    const pauseBtn = container.querySelector('[aria-label="pause recording"]');
    expect(pauseBtn).not.toBeNull();
  });

  test('renders clear button with aria-label', () => {
    const { container } = render(EventsTab);
    const clearBtn = container.querySelector('[aria-label="clear events"]');
    expect(clearBtn).not.toBeNull();
  });

  test('renders HUD overlay toggle button (🛡)', () => {
    const { container } = render(EventsTab);
    const shieldBtn = container.querySelector('[aria-label="show HUD events"]')
      ?? container.querySelector('[aria-label="hide HUD events"]');
    expect(shieldBtn).not.toBeNull();
  });

  test('renders picks-only filter toggle button (⌖)', () => {
    const { container } = render(EventsTab);
    const picksBtn = container.querySelector('[aria-label="show all events"]')
      ?? container.querySelector('[aria-label="filter to picked elements"]');
    expect(picksBtn).not.toBeNull();
  });

  test('renders at least 4 icon buttons in controls', () => {
    const { container } = render(EventsTab);
    const btns = container.querySelectorAll('.controls .icon-btn');
    expect(btns.length).toBeGreaterThanOrEqual(4);
  });
});

describe('EventsTab — empty state', () => {
  test('shows "Noch keine events." when no events buffered', () => {
    eventInterceptor.clear();
    const { getByText } = render(EventsTab);
    expect(getByText('Noch keine events.')).toBeTruthy();
  });

  test('shows hint to interact when no events', () => {
    const { container } = render(EventsTab);
    expect(container.querySelector('.empty')).not.toBeNull();
  });

  test('shows 0 shown · 0 buffered in stats', () => {
    const { container } = render(EventsTab);
    const stats = container.querySelector('.stats');
    expect(stats?.textContent).toContain('0 shown');
    expect(stats?.textContent).toContain('0 buffered');
  });
});

describe('EventsTab — pause / clear', () => {
  test('clicking clear button empties event buffer', () => {
    const { container } = render(EventsTab);
    const clearBtn = container.querySelector('[aria-label="clear events"]') as HTMLButtonElement;
    fireEvent.click(clearBtn);
    expect(eventInterceptor.events).toHaveLength(0);
  });

  test('clicking pause button toggles recording state', () => {
    const wasEnabled = eventInterceptor.enabled;
    const { container } = render(EventsTab);
    const pauseBtn = container.querySelector('[aria-label="pause recording"]')
      ?? container.querySelector('[aria-label="resume recording"]') as HTMLButtonElement;
    if (pauseBtn) fireEvent.click(pauseBtn);
    expect(eventInterceptor.enabled).not.toBe(wasEnabled);
    // restore
    if (pauseBtn) fireEvent.click(pauseBtn);
  });
});

describe('EventsTab — overlay filter toggle', () => {
  test('clicking 🛡 button toggles its aria-label', () => {
    const { container } = render(EventsTab);
    const shieldBtn = container.querySelector('[aria-label="show HUD events"]') as HTMLButtonElement;
    if (shieldBtn) {
      fireEvent.click(shieldBtn);
      // After toggling, the label changes to "hide HUD events"
      const after = container.querySelector('[aria-label="hide HUD events"]');
      expect(after).not.toBeNull();
      // Toggle back
      fireEvent.click(after as HTMLElement);
    }
  });

  test('HUD chrome event is filtered out by default hideOverlay=true — covers line 58 TRUE branch', () => {
    // in_fp_overlay=true, in_inspector_layer=false → isHudChrome(e)=true
    // hideOverlay=true (default) → hideOverlay && isHudChrome(e) TRUE → return false → event filtered
    eventInterceptor.events = [
      {
        seq: 5,
        type: 'click',
        timestamp_ms: Date.now(),
        target: 'div.fp-overlay',
        target_path: ['html', 'body', 'div.fp-overlay'],
        in_fp_overlay: true,         // HUD chrome event
        in_inspector_layer: false,
        default_prevented: false,
      } as any,
    ];
    const { container } = render(EventsTab);
    // HUD chrome event filtered by line 58 TRUE → filtered.length=0 → .empty
    expect(container.querySelector('.empty')).not.toBeNull();
    eventInterceptor.clear();
  });
});

describe('EventsTab — picks-only filter toggle', () => {
  test('clicking ⌖ button when showing all events changes label to "filter to picked elements"', () => {
    const { container } = render(EventsTab);
    // Default state: onPicksOnly=true → aria-label is "show all events" (button turns off picks filter)
    const picksBtn = container.querySelector('[aria-label="show all events"]') as HTMLButtonElement;
    expect(picksBtn).not.toBeNull();
    fireEvent.click(picksBtn!);
    // After toggle: onPicksOnly=false → aria-label becomes "filter to picked elements"
    expect(container.querySelector('[aria-label="filter to picked elements"]')).not.toBeNull();
  });

  test('clicking ⌖ again re-activates picks filter', () => {
    const { container } = render(EventsTab);
    const btn1 = container.querySelector('[aria-label="show all events"]') as HTMLButtonElement;
    if (btn1) fireEvent.click(btn1);
    const btn2 = container.querySelector('[aria-label="filter to picked elements"]') as HTMLButtonElement;
    if (btn2) fireEvent.click(btn2);
    expect(container.querySelector('[aria-label="show all events"]')).not.toBeNull();
  });

  test('helper text shows "Pick-filter active but no picks" when picks list is empty and filter on', () => {
    backendState.inspector.picks = [];
    const { getByText } = render(EventsTab);
    // Default: onPicksOnly=true, hasPicks=false → "Pick-filter active but no picks captured yet"
    expect(getByText(/Pick-filter active but no picks captured yet/)).toBeTruthy();
  });

  test('helper text shows all-events message when picks filter is off', () => {
    const { container, getByText } = render(EventsTab);
    const picksBtn = container.querySelector('[aria-label="show all events"]') as HTMLButtonElement;
    if (picksBtn) fireEvent.click(picksBtn);
    expect(getByText(/Showing all events/)).toBeTruthy();
  });

  test('helper text uses plural "elements" when picks.length > 1 — covers line 73 FALSE branch', () => {
    // With 2 picks: pickFilterActive=true, picks.length=2 → picks.length===1 ? '' : 's' FALSE → 'elements'
    backendState.inspector.picks = [
      {
        pick_id: 'p-plural-1', url: 'https://example.com', timestamp_ms: 0,
        element: { selector: 'a', fingerprint: { tag: 'a', path: ['html', 'body', 'a'] }, text_snippet: '', rect: { x: 0, y: 0, width: 10, height: 10 } },
        comment: '', color_index: 0, origin_session: null,
      } as any,
      {
        pick_id: 'p-plural-2', url: 'https://example.com', timestamp_ms: 0,
        element: { selector: 'b', fingerprint: { tag: 'b', path: ['html', 'body', 'b'] }, text_snippet: '', rect: { x: 0, y: 0, width: 10, height: 10 } },
        comment: '', color_index: 0, origin_session: null,
      } as any,
    ];
    const { getByText } = render(EventsTab);
    // onPicksOnly=true (default) + hasPicks=true → pickFilterActive=true → line 73 TRUE branch
    // picks.length=2 → 2 === 1 is FALSE → plural 's' → "2 picked elements"
    expect(getByText(/Showing events on 2 picked elements/)).toBeTruthy();
  });
});

describe('EventsTab — event list rendering', () => {
  test('shows .list container (not .empty) when events exist in interceptor buffer', () => {
    // Inject a synthetic event into the interceptor's state
    eventInterceptor.events = [
      {
        seq: 1,
        type: 'click',
        timestamp_ms: Date.now(),
        target: 'button#submit',
        target_path: ['html', 'body', 'form', 'button'],
        in_fp_overlay: false,
        in_inspector_layer: false,
        default_prevented: false,
      } as any,
    ];
    const { container } = render(EventsTab);
    expect(container.querySelector('.list')).not.toBeNull();
    expect(container.querySelector('.empty')).toBeNull();
    eventInterceptor.clear();
  });
});

// ---------------------------------------------------------------------------
// Pick filter branches — covers lines 36 (path ?? []) and 63-64 (matchesAny)
// ---------------------------------------------------------------------------

describe('EventsTab — pick filter active (line 63-64)', () => {
  test('event matching pick path passes pick filter (shows in list)', () => {
    // Set up a pick with a path — pickFilterActive becomes true (hasPicks=true, onPicksOnly=true)
    backendState.inspector.picks = [
      {
        pick_id: 'p1',
        url: 'https://example.com',
        timestamp_ms: 0,
        element: {
          selector: 'button#submit',
          fingerprint: { tag: 'button', path: ['html', 'body', 'form'] },
          text_snippet: '',
          rect: { x: 0, y: 0, width: 10, height: 10 },
        },
        comment: '',
        color_index: 0,
        origin_session: null,
      } as any,
    ];
    // Add event whose target_path starts with the pick's path → matchesAny=true
    eventInterceptor.events = [
      {
        seq: 1,
        type: 'click',
        timestamp_ms: Date.now(),
        target: 'button#submit',
        target_path: ['html', 'body', 'form', 'button#submit'],
        in_fp_overlay: false,
        in_inspector_layer: false,
        default_prevented: false,
      } as any,
    ];
    const { container } = render(EventsTab);
    // Pick filter active + matching event → list shown (not empty)
    expect(container.querySelector('.list')).not.toBeNull();
    eventInterceptor.clear();
  });

  test('event NOT matching pick path is filtered out when pick filter active', () => {
    // Pick with path that does NOT match the event's target_path
    backendState.inspector.picks = [
      {
        pick_id: 'p2',
        url: 'https://example.com',
        timestamp_ms: 0,
        element: {
          selector: 'h1.title',
          fingerprint: { tag: 'h1', path: ['html', 'body', 'header', 'h1'] },
          text_snippet: '',
          rect: { x: 0, y: 0, width: 10, height: 10 },
        },
        comment: '',
        color_index: 0,
        origin_session: null,
      } as any,
    ];
    // Event on a completely different element — won't match the pick path
    eventInterceptor.events = [
      {
        seq: 2,
        type: 'click',
        timestamp_ms: Date.now(),
        target: 'button#footer-btn',
        target_path: ['html', 'body', 'footer', 'button'],
        in_fp_overlay: false,
        in_inspector_layer: false,
        default_prevented: false,
      } as any,
    ];
    const { container } = render(EventsTab);
    // Pick filter active but no match → filtered out → empty state shown
    expect(container.querySelector('.empty')).not.toBeNull();
    eventInterceptor.clear();
  });

  test('pick with null fingerprint.path does not crash filter (covers ?? [] branch)', () => {
    // path = null triggers the `?? []` branch (returns [] as pickPath)
    backendState.inspector.picks = [
      {
        pick_id: 'p3',
        url: 'https://example.com',
        timestamp_ms: 0,
        element: {
          selector: 'div.hero',
          fingerprint: { tag: 'div', path: null },
          text_snippet: '',
          rect: { x: 0, y: 0, width: 10, height: 10 },
        },
        comment: '',
        color_index: 0,
        origin_session: null,
      } as any,
    ];
    eventInterceptor.events = [
      {
        seq: 3,
        type: 'click',
        timestamp_ms: Date.now(),
        target: 'div.hero',
        target_path: ['html', 'body', 'div'],
        in_fp_overlay: false,
        in_inspector_layer: false,
        default_prevented: false,
      } as any,
    ];
    // eventMatchesPickPath returns false when pickPath.length === 0 → no match → empty
    const { container } = render(EventsTab);
    expect(container).toBeTruthy(); // just no crash
    eventInterceptor.clear();
  });
});

// ---------------------------------------------------------------------------
// Dropdown filter type change — covers line 121 (onChange handler)
// ---------------------------------------------------------------------------

describe('EventsTab — filter type dropdown onChange', () => {
  test('changing the filter dropdown value updates typeFilter (line 121 coverage)', () => {
    // Populate with a wheel event so filtering by type is meaningful
    eventInterceptor.events = [
      {
        seq: 10,
        type: 'wheel',
        timestamp_ms: Date.now(),
        target: 'div.scroll-area',
        target_path: ['html', 'body', 'div'],
        in_fp_overlay: false,
        in_inspector_layer: false,
        default_prevented: false,
        delta_x: 0,
        delta_y: 100,
      } as any,
    ];
    const { container } = render(EventsTab);
    // Dropdown is a CUSTOM component — no native <select>. Interaction:
    // 1. click .dropdown__trigger to open the panel
    // 2. click a .dropdown__option button to fire onChange((v) => typeFilter = v)
    const trigger = container.querySelector('.dropdown__trigger') as HTMLButtonElement;
    expect(trigger).not.toBeNull();
    fireEvent.click(trigger); // opens panel
    // Find the 'wheel' option (matches label text containing 'wheel')
    const options = container.querySelectorAll('.dropdown__option');
    const wheelOption = Array.from(options).find((o) =>
      o.textContent?.includes('wheel')
    ) as HTMLButtonElement;
    expect(wheelOption).not.toBeNull();
    fireEvent.click(wheelOption); // calls onChange('wheel') → typeFilter = 'wheel'
    // After selecting 'wheel', the typeFilter is now 'wheel' — the wheel event should still show
    expect(container.querySelector('.list')).not.toBeNull();
    eventInterceptor.clear();
  });
});
