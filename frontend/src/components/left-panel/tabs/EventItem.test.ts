/**
 * EventItem component tests.
 *
 * Covers rendered output for all event types:
 * - type chip + target text
 * - wheel: Δ dx,dy extra
 * - scroll: scrollY= extra
 * - keydown: key extra
 * - other types (click, pointerdown): no extra
 * - default_prevented → ⚠ flag
 * - in_fp_overlay → 🛡 flag
 */
const send = vi.hoisted(() => vi.fn());
vi.mock('../../../bridge/bridge.svelte', () => ({ bridge: { send } }));

import { describe, expect, test, afterEach } from 'vitest';
import { render, cleanup } from '@testing-library/svelte';
import EventItem from './EventItem.svelte';
import type { InterceptedEvent } from '../../../services/event-interceptor';

afterEach(() => cleanup());

function makeEvent(overrides: Partial<InterceptedEvent> = {}): InterceptedEvent {
  return {
    type: 'click',
    target: 'button.my-btn',
    default_prevented: false,
    in_fp_overlay: false,
    ...overrides,
  } as unknown as InterceptedEvent;
}

describe('EventItem — basic rendering', () => {
  test('renders the event type chip', () => {
    const { getByText } = render(EventItem, { event: makeEvent({ type: 'click' }) });
    expect(getByText('click')).toBeTruthy();
  });

  test('renders the target string', () => {
    const { getByText } = render(EventItem, { event: makeEvent({ target: 'div#app' }) });
    expect(getByText('div#app')).toBeTruthy();
  });
});

describe('EventItem — extra field', () => {
  test('wheel event shows Δ dx,dy extra', () => {
    const { getByText } = render(EventItem, {
      event: makeEvent({ type: 'wheel', delta_x: 10, delta_y: -20 } as any),
    });
    expect(getByText('Δ 10,-20')).toBeTruthy();
  });

  test('scroll event shows scrollY= extra', () => {
    const { getByText } = render(EventItem, {
      event: makeEvent({ type: 'scroll', scroll_y: 300 } as any),
    });
    expect(getByText('scrollY=300')).toBeTruthy();
  });

  test('keydown event shows the key', () => {
    const { getByText } = render(EventItem, {
      event: makeEvent({ type: 'keydown', key: 'Enter' } as any),
    });
    expect(getByText('Enter')).toBeTruthy();
  });

  test('click event has no extra span', () => {
    const { container } = render(EventItem, { event: makeEvent({ type: 'click' }) });
    const extras = container.querySelectorAll('.extra');
    expect(extras).toHaveLength(0);
  });

  test('pointerdown event has no extra', () => {
    const { container } = render(EventItem, { event: makeEvent({ type: 'pointerdown' } as any) });
    const extras = container.querySelectorAll('.extra');
    expect(extras).toHaveLength(0);
  });

  test('wheel event with null delta_x and null delta_y shows Δ 0,0', () => {
    // Covers: delta_x ?? 0 (null → 0) and delta_y ?? 0 (null → 0)
    const { getByText } = render(EventItem, {
      event: makeEvent({ type: 'wheel', delta_x: null, delta_y: null } as any),
    });
    expect(getByText('Δ 0,0')).toBeTruthy();
  });

  test('scroll event with null scroll_y shows scrollY=?', () => {
    // Covers: scroll_y?.toFixed(0) ?? '?' (null → '?')
    const { getByText } = render(EventItem, {
      event: makeEvent({ type: 'scroll', scroll_y: null } as any),
    });
    expect(getByText('scrollY=?')).toBeTruthy();
  });

  test('keydown event with null key produces no extra span (covers event.key ?? "" null branch)', () => {
    // event.key ?? '' returns '' (empty string, falsy) → {#if extra} is false → no .extra span
    const { container } = render(EventItem, {
      event: makeEvent({ type: 'keydown', key: null } as any),
    });
    // The expression `event.key ?? ''` IS evaluated (covering the null branch),
    // but '' is falsy so the span is not rendered.
    expect(container.querySelector('.extra')).toBeNull();
  });
});

describe('EventItem — flags', () => {
  test('shows ⚠ flag when default_prevented=true', () => {
    const { getByTitle } = render(EventItem, {
      event: makeEvent({ default_prevented: true }),
    });
    expect(getByTitle('default_prevented = true beim capture')).toBeTruthy();
  });

  test('no ⚠ flag when default_prevented=false', () => {
    const { container } = render(EventItem, {
      event: makeEvent({ default_prevented: false }),
    });
    expect(container.querySelectorAll('.flag--prevented')).toHaveLength(0);
  });

  test('shows 🛡 flag when in_fp_overlay=true', () => {
    const { getByTitle } = render(EventItem, {
      event: makeEvent({ in_fp_overlay: true }),
    });
    expect(getByTitle('target ist innerhalb fp-overlay')).toBeTruthy();
  });

  test('no 🛡 flag when in_fp_overlay=false', () => {
    const { container } = render(EventItem, {
      event: makeEvent({ in_fp_overlay: false }),
    });
    expect(container.querySelectorAll('.flag--ours')).toHaveLength(0);
  });
});
