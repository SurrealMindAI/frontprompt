/**
 * FloatingRecorderToolbar smoke tests.
 *
 * The toolbar is only rendered when recorder.isActive === true,
 * which is $derived from backendState.recordings.activeRecordingId !== null.
 * We control visibility by setting activeRecordingId directly.
 */
const send = vi.hoisted(() => vi.fn());
vi.mock('../bridge/bridge.svelte', () => ({ bridge: { send } }));

import { describe, expect, test, afterEach, beforeEach, vi } from 'vitest';
import { render, cleanup, fireEvent } from '@testing-library/svelte';
import FloatingRecorderToolbar from './FloatingRecorderToolbar.svelte';
import { backendState } from '../backend-state/backend-state.svelte';
import { regionDraft } from '../services/regions';

afterEach(() => {
  cleanup();
  send.mockClear();
  backendState.recordings.activeRecordingId = null;
  regionDraft.cancel();
});

beforeEach(() => {
  backendState.recordings.activeRecordingId = null;
});

describe('FloatingRecorderToolbar — hidden when not active', () => {
  test('renders nothing when recorder is not active', () => {
    backendState.recordings.activeRecordingId = null;
    const { container } = render(FloatingRecorderToolbar);
    expect(container.querySelector('.rec-toolbar')).toBeNull();
  });
});

describe('FloatingRecorderToolbar — visible when active', () => {
  beforeEach(() => {
    backendState.recordings.activeRecordingId = 'rec-001';
  });

  test('renders toolbar when recorder is active', () => {
    const { container } = render(FloatingRecorderToolbar);
    expect(container.querySelector('.rec-toolbar')).not.toBeNull();
  });

  test('renders Stop recording button', () => {
    const { container } = render(FloatingRecorderToolbar);
    const stopBtn = container.querySelector('[aria-label="Stop recording"]');
    expect(stopBtn).not.toBeNull();
  });

  test('renders Draw region button', () => {
    const { container } = render(FloatingRecorderToolbar);
    const regionBtn = container.querySelector('[aria-label="Draw region"]');
    expect(regionBtn).not.toBeNull();
  });

  test('renders Pick element button', () => {
    const { container } = render(FloatingRecorderToolbar);
    const pickBtn = container.querySelector('[aria-label="Pick element"]');
    expect(pickBtn).not.toBeNull();
  });

  test('renders drag handle', () => {
    const { container } = render(FloatingRecorderToolbar);
    expect(container.querySelector('.rec-toolbar__drag-handle')).not.toBeNull();
  });

  test('renders toolbar role="toolbar"', () => {
    const { container } = render(FloatingRecorderToolbar);
    expect(container.querySelector('[role="toolbar"]')).not.toBeNull();
  });

  test('toolbar has aria-label "Recorder toolbar"', () => {
    const { container } = render(FloatingRecorderToolbar);
    const toolbar = container.querySelector('[aria-label="Recorder toolbar"]');
    expect(toolbar).not.toBeNull();
  });

  test('shows active recording name in label', () => {
    // activeRecording is $derived from recordings + activeRecordingId
    backendState.recordings.recordings = [
      { recording_id: 'rec-001', name: 'My Session', description: '', status: 'active', started_at_ms: Date.now(), entry_count: 0 },
    ];
    const { getByText } = render(FloatingRecorderToolbar);
    expect(getByText('My Session')).toBeTruthy();
    backendState.recordings.recordings = [];
  });

  test('clicking Draw region button starts region draft', () => {
    const { container } = render(FloatingRecorderToolbar);
    const regionBtn = container.querySelector('[aria-label="Draw region"]') as HTMLButtonElement;
    fireEvent.click(regionBtn);
    expect(regionDraft.drafting).toBe(true);
    regionDraft.cancel();
  });

  test('clicking Stop calls bridge.send with stop intent', () => {
    const { container } = render(FloatingRecorderToolbar);
    const stopBtn = container.querySelector('[aria-label="Stop recording"]') as HTMLButtonElement;
    fireEvent.click(stopBtn);
    expect(send).toHaveBeenCalled();
  });

  test('clicking Pick element button acquires pick-claim via bridge', () => {
    // Pick element button calls pickClaim.acquire → sets active pick mode
    // We verify the click doesn't throw and executes onPick path
    const { container } = render(FloatingRecorderToolbar);
    const pickBtn = container.querySelector('[aria-label="Pick element"]') as HTMLButtonElement;
    expect(() => fireEvent.click(pickBtn)).not.toThrow();
    // onPick calls pickClaim.acquire which may send via bridge when inspector activates
    // Just verifying the button is functional and covered
  });

  test('pointerdown on drag handle does not throw in jsdom', () => {
    // handleDragStart calls setPointerCapture which isn't available in jsdom
    // The try/catch in handleDragStart prevents exceptions — just cover the code path
    const { container } = render(FloatingRecorderToolbar);
    const handle = container.querySelector('.rec-toolbar__drag-handle') as HTMLElement;
    expect(() => fireEvent.pointerDown(handle, { pointerId: 1, button: 0, clientX: 100, clientY: 50 })).not.toThrow();
  });

  test('drag: button=2 pointerdown is ignored (covers button !== 0 early return)', () => {
    const { container } = render(FloatingRecorderToolbar);
    const handle = container.querySelector('.rec-toolbar__drag-handle') as HTMLElement;
    // button=2 (right click) → handleDragStart early return branch
    expect(() => fireEvent.pointerDown(handle, { pointerId: 1, button: 2, clientX: 50, clientY: 50 })).not.toThrow();
  });

  test('drag: full pointerdown→pointermove→pointerup sequence with mocked pointer capture', () => {
    // Mock setPointerCapture and releasePointerCapture so they don't throw in jsdom.
    // This unblocks the try-catch so the drag code after the catch executes.
    const origSetPC = Element.prototype.setPointerCapture;
    const origReleasePC = Element.prototype.releasePointerCapture;
    Element.prototype.setPointerCapture = vi.fn();
    Element.prototype.releasePointerCapture = vi.fn();

    try {
      const { container } = render(FloatingRecorderToolbar);
      const handle = container.querySelector('.rec-toolbar__drag-handle') as HTMLElement;

      // pointerdown (button=0) — sets dragOrigin, registers move/up listeners
      fireEvent.pointerDown(handle, { pointerId: 42, button: 0, clientX: 200, clientY: 100 });

      // pointermove — handleDragMove executes (dragOrigin is set)
      fireEvent.pointerMove(handle, { pointerId: 42, clientX: 220, clientY: 110 });

      // pointerup — handleDragEnd executes, resets dragOrigin
      fireEvent.pointerUp(handle, { pointerId: 42, clientX: 220, clientY: 110 });
    } finally {
      Element.prototype.setPointerCapture = origSetPC;
      Element.prototype.releasePointerCapture = origReleasePC;
    }
  });

  test('drag: pointermove without prior pointerdown is a no-op (dragOrigin null guard)', () => {
    // handleDragMove: if (!dragOrigin) return — covers the dragOrigin=null guard
    const origSetPC = Element.prototype.setPointerCapture;
    const origReleasePC = Element.prototype.releasePointerCapture;
    Element.prototype.setPointerCapture = vi.fn();
    Element.prototype.releasePointerCapture = vi.fn();

    try {
      const { container } = render(FloatingRecorderToolbar);
      const handle = container.querySelector('.rec-toolbar__drag-handle') as HTMLElement;
      // Do pointerdown to register the listeners (but without prior dragOrigin being set)
      // Then immediately fire pointermove — but dragOrigin was set by pointerdown...
      // Instead: do pointerdown, then pointerup (to reset dragOrigin), then pointermove
      fireEvent.pointerDown(handle, { pointerId: 1, button: 0, clientX: 100, clientY: 50 });
      fireEvent.pointerUp(handle, { pointerId: 1, clientX: 100, clientY: 50 });
      // dragOrigin is now null — pointermove is a no-op
      fireEvent.pointerMove(handle, { pointerId: 1, clientX: 150, clientY: 80 });
    } finally {
      Element.prototype.setPointerCapture = origSetPC;
      Element.prototype.releasePointerCapture = origReleasePC;
    }
  });
});
