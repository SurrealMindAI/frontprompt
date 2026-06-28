/**
 * LeftPanelTools tests.
 *
 * Tests: button rendering, pick toggle, region toggle, quick toggle,
 * hide-all toggle, recorder start/stop, keyboard shortcut (R).
 */
const send = vi.hoisted(() => vi.fn());
vi.mock('../../bridge/bridge.svelte', () => ({ bridge: { send } }));

import { describe, expect, test, afterEach } from 'vitest';
import { render, cleanup, fireEvent } from '@testing-library/svelte';
import LeftPanelTools from './LeftPanelTools.svelte';
import { backendState } from '../../backend-state/backend-state.svelte';
import { pickClaim } from '../../local-state/pick-claim.svelte';
import { regionDraft } from '../../services/regions';
import { quickCommentMode } from '../../local-state/quick-comment-mode.svelte';

afterEach(() => {
  cleanup();
  send.mockClear();
  // Release all claims
  pickClaim.release();
  regionDraft.cancel();
  // Exit quick mode if active
  if (quickCommentMode.active) quickCommentMode.exit();
  // Reset recorder state directly (isActive is $derived, set underlying state)
  backendState.recordings.activeRecordingId = null;
  // Reset panels to open
  backendState.panel.panels.left.open = true;
  backendState.panel.panels.right.open = true;
  backendState.panel.panels.top.open = true;
  backendState.panel.panels.bottom.open = true;
});

describe('LeftPanelTools — rendering', () => {
  test('renders .tools container', () => {
    const { container } = render(LeftPanelTools);
    expect(container.querySelector('.tools')).not.toBeNull();
  });

  test('renders region button', () => {
    const { container } = render(LeftPanelTools);
    const regionBtn = container.querySelector('[aria-label="region"]');
    expect(regionBtn).not.toBeNull();
  });

  test('renders quick button', () => {
    const { container } = render(LeftPanelTools);
    // quick button has aria-label "enter quick-comment mode" when inactive
    const quickBtn = container.querySelector('[aria-label="enter quick-comment mode"]');
    expect(quickBtn).not.toBeNull();
  });

  test('renders hide-all button', () => {
    const { container } = render(LeftPanelTools);
    const hideBtn = container.querySelector('[aria-label="hide all panels"]');
    expect(hideBtn).not.toBeNull();
  });

  test('renders recorder button (Start recording)', () => {
    const { container } = render(LeftPanelTools);
    const recBtn = container.querySelector('[aria-label="Start recording"]');
    expect(recBtn).not.toBeNull();
  });

  test('renders voice-over button', () => {
    const { container } = render(LeftPanelTools);
    const voiceBtn = container.querySelector('[aria-label="Start voice-over recording"]');
    expect(voiceBtn).not.toBeNull();
  });
});

describe('LeftPanelTools — region toggle', () => {
  test('clicking region button starts regionDraft', async () => {
    const { container } = render(LeftPanelTools);
    const regionBtn = container.querySelector('[aria-label="region"]') as HTMLButtonElement;
    expect(regionDraft.drafting).toBe(false);
    await fireEvent.click(regionBtn);
    expect(regionDraft.drafting).toBe(true);
  });

  test('clicking region button again cancels regionDraft', async () => {
    const { container } = render(LeftPanelTools);
    const regionBtn = container.querySelector('[aria-label="region"]') as HTMLButtonElement;
    await fireEvent.click(regionBtn);
    expect(regionDraft.drafting).toBe(true);
    await fireEvent.click(regionBtn);
    expect(regionDraft.drafting).toBe(false);
  });

  test('region button shows tool-btn--active class when region draft active', async () => {
    const { container } = render(LeftPanelTools);
    const regionBtn = container.querySelector('[aria-label="region"]') as HTMLButtonElement;
    await fireEvent.click(regionBtn);
    expect(regionBtn.classList.contains('tool-btn--active')).toBe(true);
  });
});

describe('LeftPanelTools — quick-comment toggle', () => {
  test('clicking quick enters quick-comment mode', async () => {
    const { container } = render(LeftPanelTools);
    const quickBtn = container.querySelector('[aria-label="enter quick-comment mode"]') as HTMLButtonElement;
    expect(quickCommentMode.active).toBe(false);
    await fireEvent.click(quickBtn);
    expect(quickCommentMode.active).toBe(true);
  });

  test('clicking quick again exits quick-comment mode', async () => {
    const { container } = render(LeftPanelTools);
    const quickBtn = container.querySelector('[aria-label="enter quick-comment mode"]') as HTMLButtonElement;
    await fireEvent.click(quickBtn);
    // Now it's in quick mode, label changes
    const exitBtn = container.querySelector('[aria-label="exit quick-comment mode"]') as HTMLButtonElement;
    await fireEvent.click(exitBtn);
    expect(quickCommentMode.active).toBe(false);
  });
});

describe('LeftPanelTools — hide-all toggle', () => {
  test('clicking hide-all closes all panels', async () => {
    const { container } = render(LeftPanelTools);
    const hideBtn = container.querySelector('[aria-label="hide all panels"]') as HTMLButtonElement;
    await fireEvent.click(hideBtn);
    expect(backendState.panel.allHidden).toBe(true);
  });

  test('clicking show-all when hidden opens all panels', async () => {
    // First hide all manually
    backendState.panel.panels.left.open = false;
    backendState.panel.panels.right.open = false;
    backendState.panel.panels.top.open = false;
    backendState.panel.panels.bottom.open = false;
    const { container } = render(LeftPanelTools);
    const showBtn = container.querySelector('[aria-label="show all panels"]') as HTMLButtonElement;
    await fireEvent.click(showBtn);
    expect(backendState.panel.allHidden).toBe(false);
  });
});

describe('LeftPanelTools — recorder toggle', () => {
  test('clicking Start recording sends bridge message (startRecording intent)', async () => {
    const { container } = render(LeftPanelTools);
    const recBtn = container.querySelector('[aria-label="Start recording"]') as HTMLButtonElement;
    await fireEvent.click(recBtn);
    // recorder.start() → backendState.recordings.startRecording() → bridge.send(...)
    expect(send).toHaveBeenCalled();
  });

  test('recorder button changes to Stop recording when activeRecordingId is set', async () => {
    // Simulate backend ack: set activeRecordingId directly (normally Python sets this)
    backendState.recordings.activeRecordingId = 'rec-test-001';
    const { container } = render(LeftPanelTools);
    const stopBtn = container.querySelector('[aria-label="Stop recording"]');
    expect(stopBtn).not.toBeNull();
  });

  test('clicking Stop recording sends bridge message (stopRecording intent)', async () => {
    backendState.recordings.activeRecordingId = 'rec-test-001';
    const { container } = render(LeftPanelTools);
    const stopBtn = container.querySelector('[aria-label="Stop recording"]') as HTMLButtonElement;
    await fireEvent.click(stopBtn);
    expect(send).toHaveBeenCalled();
  });
});

describe('LeftPanelTools — keyboard shortcut R', () => {
  test('pressing uppercase R sends bridge message (toggleRecorder → startRecording)', async () => {
    render(LeftPanelTools);
    send.mockClear();
    await fireEvent.keyDown(window, { key: 'R' });
    // handleKeyDown → toggleRecorder() → recorder.start() → bridge.send(...)
    expect(send).toHaveBeenCalled();
  });

  test('pressing R with Ctrl modifier does NOT trigger recorder', async () => {
    render(LeftPanelTools);
    send.mockClear();
    await fireEvent.keyDown(window, { key: 'R', ctrlKey: true });
    expect(send).not.toHaveBeenCalled();
  });

  test('pressing lowercase r does NOT trigger recorder', async () => {
    render(LeftPanelTools);
    send.mockClear();
    await fireEvent.keyDown(window, { key: 'r' });
    expect(send).not.toHaveBeenCalled();
  });
});
