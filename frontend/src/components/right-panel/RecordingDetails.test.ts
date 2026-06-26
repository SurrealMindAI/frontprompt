/**
 * RecordingDetails component tests (vitest + jsdom + @testing-library/svelte).
 *
 * Test surface:
 *   - Shows recording name in editable input (.details-name)
 *   - Shows recording description in editable textarea (.details-description)
 *   - Save calls renameRecording(id, name, description) via bridge
 *   - Save button disabled when form is not dirty
 *   - Cancel reverts to last saved values without calling bridge
 *   - started_at shown as read-only metadata (.details-started-at)
 *   - ended_at shows "recording…" when recording is active (ended_at_ms null)
 */

// Bridge mock — hoisted before module imports
const send = vi.hoisted(() => vi.fn());
vi.mock('../../bridge/bridge.svelte', () => ({ bridge: { send } }));

import { describe, expect, test, vi, afterEach } from 'vitest';
import { render, cleanup, fireEvent } from '@testing-library/svelte';
import RecordingDetails from './RecordingDetails.svelte';
import type { Recording } from '../../_generated/state';

afterEach(() => {
  cleanup();
  send.mockClear();
});

// --- Fixtures ---------------------------------------------------------------

function makeRecording(overrides: Partial<Recording> = {}): Recording {
  return {
    recording_id: 'rec-detail-001',
    name: 'My Recording',
    description: 'A test recording',
    status: 'stopped',
    started_at_ms: 1700000000000,
    ended_at_ms: 1700000010000,
    entries: [],
    ...overrides,
  } as unknown as Recording;
}

// --- Tests ------------------------------------------------------------------

describe('RecordingDetails', () => {
  test('shows recording name in .details-name input', () => {
    const recording = makeRecording({ name: 'Session Alpha' });
    const { container } = render(RecordingDetails, { props: { recording } });
    const nameInput = container.querySelector('.details-name') as HTMLInputElement;
    expect(nameInput).not.toBeNull();
    expect(nameInput.value).toBe('Session Alpha');
  });

  test('shows recording description in .details-description textarea', () => {
    const recording = makeRecording({ description: 'Describing my session' });
    const { container } = render(RecordingDetails, { props: { recording } });
    const descInput = container.querySelector('.details-description') as HTMLTextAreaElement;
    expect(descInput).not.toBeNull();
    expect(descInput.value).toBe('Describing my session');
  });

  test('Save button is disabled when form is not dirty', () => {
    const recording = makeRecording();
    const { container } = render(RecordingDetails, { props: { recording } });
    const saveBtn = container.querySelector('.details-save') as HTMLButtonElement;
    expect(saveBtn).not.toBeNull();
    expect(saveBtn.disabled).toBe(true);
  });

  test('Save button calls renameRecording with updated name via bridge', async () => {
    const recording = makeRecording({ recording_id: 'rec-001', name: 'Old Name', description: 'Old Desc' });
    const { container } = render(RecordingDetails, { props: { recording } });
    const nameInput = container.querySelector('.details-name') as HTMLInputElement;
    const saveBtn = container.querySelector('.details-save') as HTMLButtonElement;

    // Simulate user typing a new name
    nameInput.value = 'New Name';
    await fireEvent.input(nameInput);

    // Save should now be enabled
    expect(saveBtn.disabled).toBe(false);

    await fireEvent.click(saveBtn);

    expect(send).toHaveBeenCalledWith(
      expect.objectContaining({
        kind: 'recording_rename_requested',
        recording_id: 'rec-001',
        name: 'New Name',
      })
    );
  });

  test('Cancel reverts name to last saved value without calling bridge', async () => {
    const recording = makeRecording({ name: 'Original Name' });
    const { container } = render(RecordingDetails, { props: { recording } });
    const nameInput = container.querySelector('.details-name') as HTMLInputElement;
    const cancelBtn = container.querySelector('.details-cancel') as HTMLButtonElement;

    nameInput.value = 'Temporary Name';
    await fireEvent.input(nameInput);

    await fireEvent.click(cancelBtn);

    // Bridge must NOT have been called
    expect(send).not.toHaveBeenCalled();
    // Input reverts to original
    expect(nameInput.value).toBe('Original Name');
  });

  test('shows started_at as read-only metadata element', () => {
    const recording = makeRecording({ started_at_ms: 1700000000000 });
    const { container } = render(RecordingDetails, { props: { recording } });
    expect(container.querySelector('.details-started-at')).not.toBeNull();
  });

  test('shows "recording…" for ended_at when recording is active', () => {
    const recording = makeRecording({ status: 'active', ended_at_ms: null });
    const { container } = render(RecordingDetails, { props: { recording } });
    expect(container.textContent).toContain('recording…');
  });
});
