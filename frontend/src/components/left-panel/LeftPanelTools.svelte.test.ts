/**
 * LeftPanelTools tests (vitest + jsdom + @testing-library/svelte).
 *
 * The left tools strip is the single home for all action tools: pick · region ·
 * quick · hide-all · record. These tests cover the quick-comment toggle (moved here
 * from the top Toolbar) and the new recorder button + keyboard shortcut.
 */

// Mock bridge so bridge.send() is a spy (no window.__fp needed in tests).
const send = vi.hoisted(() => vi.fn());
vi.mock('../../bridge/bridge.svelte', () => ({ bridge: { send } }));

import { describe, expect, test, vi, beforeEach, afterEach } from 'vitest';
import { render, cleanup, fireEvent } from '@testing-library/svelte';
import { tick } from 'svelte';
import LeftPanelTools from './LeftPanelTools.svelte';
import { quickCommentMode } from '../../local-state/quick-comment-mode.svelte';
import { backendState } from '../../backend-state/backend-state.svelte';

beforeEach(() => {
  send.mockClear();
  quickCommentMode.exit();
  // Reset recorder backend-mirror so each test starts with no active recording.
  backendState.recordings.activeRecordingId = null;
});

afterEach(() => {
  cleanup();
});

// ---------------------------------------------------------------------------
// Helpers
// ---------------------------------------------------------------------------

function quickButton(container: HTMLElement): HTMLButtonElement {
  const btn = container.querySelector<HTMLButtonElement>(
    'button[aria-label="enter quick-comment mode"], button[aria-label="exit quick-comment mode"]'
  );
  if (!btn) throw new Error('quick-comment toggle button not found');
  return btn;
}

function recorderButton(container: HTMLElement): HTMLButtonElement {
  const btn = container.querySelector<HTMLButtonElement>(
    'button[aria-label="Start recording"], button[aria-label="Stop recording"]'
  );
  if (!btn) throw new Error('recorder toggle button not found');
  return btn;
}

// ---------------------------------------------------------------------------
// Existing: quick-comment toggle
// ---------------------------------------------------------------------------

describe('LeftPanelTools quick-comment toggle', () => {
  test('renders a quick-comment toggle button (inactive by default)', () => {
    const { container } = render(LeftPanelTools);
    const btn = quickButton(container);
    expect(btn.textContent).toContain('quick');
    expect(btn.getAttribute('aria-pressed')).toBe('false');
  });

  test('quick button carries the "quick pick and comment" tooltip', () => {
    const { container } = render(LeftPanelTools);
    expect(quickButton(container).getAttribute('title')).toBe('quick pick and comment');
  });

  test('clicking enters quick-comment mode', async () => {
    const { container } = render(LeftPanelTools);
    await fireEvent.click(quickButton(container));
    expect(quickCommentMode.active).toBe(true);
  });

  test('clicking again exits quick-comment mode', async () => {
    const { container } = render(LeftPanelTools);
    await fireEvent.click(quickButton(container));
    await fireEvent.click(quickButton(container));
    expect(quickCommentMode.active).toBe(false);
  });

  test('reflects active state via aria-pressed', async () => {
    const { container } = render(LeftPanelTools);
    await fireEvent.click(quickButton(container));
    expect(quickButton(container).getAttribute('aria-pressed')).toBe('true');
  });
});

// ---------------------------------------------------------------------------
// Recorder button + keyboard shortcut
// ---------------------------------------------------------------------------

describe('LeftPanelTools recorder button', () => {
  test('recorder button is visible in toolbar', () => {
    const { container } = render(LeftPanelTools);
    const btn = recorderButton(container);
    expect(btn).toBeTruthy();
    expect(btn.textContent).toContain('rec');
  });

  test('recorder button has aria-label="Start recording" when inactive', () => {
    const { container } = render(LeftPanelTools);
    const btn = recorderButton(container);
    expect(btn.getAttribute('aria-label')).toBe('Start recording');
  });

  test('clicking recorder button when inactive calls recorder.start() (sends recording_start_requested)', async () => {
    const { container } = render(LeftPanelTools);
    await fireEvent.click(recorderButton(container));
    expect(send).toHaveBeenCalledOnce();
    expect(send).toHaveBeenCalledWith(
      expect.objectContaining({ kind: 'recording_start_requested' })
    );
  });

  test('recorder button has aria-label="Stop recording" when recording is active', async () => {
    const { container } = render(LeftPanelTools);
    // Simulate active recording by setting backend-state mirror.
    backendState.recordings.activeRecordingId = 'rec-live-001';
    await tick();
    const btn = recorderButton(container);
    expect(btn.getAttribute('aria-label')).toBe('Stop recording');
  });

  test('clicking recorder button when active calls recorder.stop() (sends recording_stop_requested)', async () => {
    const { container } = render(LeftPanelTools);
    backendState.recordings.activeRecordingId = 'rec-live-001';
    await tick();
    await fireEvent.click(recorderButton(container));
    expect(send).toHaveBeenCalledOnce();
    expect(send).toHaveBeenCalledWith(
      expect.objectContaining({
        kind: 'recording_stop_requested',
        recording_id: 'rec-live-001',
      })
    );
  });

  test('recorder button aria-pressed is false when inactive', () => {
    const { container } = render(LeftPanelTools);
    expect(recorderButton(container).getAttribute('aria-pressed')).toBe('false');
  });

  test('recorder button aria-pressed is true when active', async () => {
    const { container } = render(LeftPanelTools);
    backendState.recordings.activeRecordingId = 'rec-live-001';
    await tick();
    expect(recorderButton(container).getAttribute('aria-pressed')).toBe('true');
  });
});

describe('LeftPanelTools keyboard shortcut R', () => {
  test('pressing R on window starts recording when inactive', async () => {
    render(LeftPanelTools);
    await fireEvent.keyDown(window, { key: 'R' });
    expect(send).toHaveBeenCalledWith(
      expect.objectContaining({ kind: 'recording_start_requested' })
    );
  });

  test('pressing R on window stops recording when active', async () => {
    render(LeftPanelTools);
    backendState.recordings.activeRecordingId = 'rec-key-001';
    await tick();
    await fireEvent.keyDown(window, { key: 'R' });
    expect(send).toHaveBeenCalledWith(
      expect.objectContaining({
        kind: 'recording_stop_requested',
        recording_id: 'rec-key-001',
      })
    );
  });

  test('pressing lowercase r does not trigger recording', async () => {
    render(LeftPanelTools);
    await fireEvent.keyDown(window, { key: 'r' });
    expect(send).not.toHaveBeenCalled();
  });
});
