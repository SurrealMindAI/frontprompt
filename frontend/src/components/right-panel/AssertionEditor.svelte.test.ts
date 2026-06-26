/**
 * AssertionEditor component tests (vitest + jsdom + @testing-library/svelte).
 *
 * Test surface:
 *   - Renders form fields: assertion_type dropdown, target input, expected input,
 *     comparator select, description input
 *   - Submitting with assertion_type="selector_exists" sends AssertionAddedToRecordingRequested
 *     with expected=null, comparator="none"
 *   - Submitting with assertion_type="text_equals" + non-empty expected sends correct fields
 *   - After submit: form resets to empty draft state
 *   - Cancel: form clears without sending
 *   - Edit draft is localState (ADR-018: in-flight edit, not backendState)
 */

// Bridge mock — hoisted before module imports
const send = vi.hoisted(() => vi.fn());
vi.mock('../../bridge/bridge.svelte', () => ({ bridge: { send } }));

import { describe, expect, test, vi, afterEach } from 'vitest';
import { render, cleanup, fireEvent } from '@testing-library/svelte';
import AssertionEditor from './AssertionEditor.svelte';

afterEach(() => {
  cleanup();
  send.mockClear();
});

// --- Tests ------------------------------------------------------------------

describe('AssertionEditor', () => {
  test('renders assertion_type dropdown', () => {
    const { container } = render(AssertionEditor, { props: { recording_id: 'rec-001' } });
    const dropdown = container.querySelector('.assertion-type') as HTMLSelectElement;
    expect(dropdown).not.toBeNull();
  });

  test('renders target input', () => {
    const { container } = render(AssertionEditor, { props: { recording_id: 'rec-001' } });
    const targetInput = container.querySelector('.assertion-target') as HTMLInputElement;
    expect(targetInput).not.toBeNull();
  });

  test('renders comparator select', () => {
    const { container } = render(AssertionEditor, { props: { recording_id: 'rec-001' } });
    const comparator = container.querySelector('.assertion-comparator') as HTMLSelectElement;
    expect(comparator).not.toBeNull();
  });

  test('renders description input', () => {
    const { container } = render(AssertionEditor, { props: { recording_id: 'rec-001' } });
    const desc = container.querySelector('.assertion-description') as HTMLInputElement;
    expect(desc).not.toBeNull();
  });

  test('submitting with assertion_type="selector_exists" sends AssertionAddedToRecordingRequested with expected=null and comparator="none"', async () => {
    const { container } = render(AssertionEditor, { props: { recording_id: 'rec-001' } });
    const typeDropdown = container.querySelector('.assertion-type') as HTMLSelectElement;
    const targetInput = container.querySelector('.assertion-target') as HTMLInputElement;
    const submitBtn = container.querySelector('.assertion-submit') as HTMLButtonElement;

    typeDropdown.value = 'selector_exists';
    await fireEvent.change(typeDropdown);

    targetInput.value = 'button#submit';
    await fireEvent.input(targetInput);

    await fireEvent.click(submitBtn);

    expect(send).toHaveBeenCalledOnce();
    expect(send).toHaveBeenCalledWith(
      expect.objectContaining({
        kind: 'assertion_added_to_recording_requested',
        recording_id: 'rec-001',
        assertion: expect.objectContaining({
          assertion_type: 'selector_exists',
          target: 'button#submit',
          expected: null,
          comparator: 'none',
        }),
      })
    );
  });

  test('submitting with assertion_type="text_equals" sends message with correct expected', async () => {
    const { container } = render(AssertionEditor, { props: { recording_id: 'rec-002' } });
    const typeDropdown = container.querySelector('.assertion-type') as HTMLSelectElement;
    const targetInput = container.querySelector('.assertion-target') as HTMLInputElement;
    const submitBtn = container.querySelector('.assertion-submit') as HTMLButtonElement;

    // Change type first — expected input appears after re-render
    typeDropdown.value = 'text_equals';
    await fireEvent.change(typeDropdown);

    // Query expected input AFTER type change so Svelte has re-rendered
    const expectedInput = container.querySelector('.assertion-expected') as HTMLInputElement;
    expect(expectedInput).not.toBeNull();

    targetInput.value = 'h1.title';
    await fireEvent.input(targetInput);

    expectedInput.value = 'Welcome';
    await fireEvent.input(expectedInput);

    await fireEvent.click(submitBtn);

    expect(send).toHaveBeenCalledOnce();
    expect(send).toHaveBeenCalledWith(
      expect.objectContaining({
        kind: 'assertion_added_to_recording_requested',
        recording_id: 'rec-002',
        assertion: expect.objectContaining({
          assertion_type: 'text_equals',
          expected: 'Welcome',
        }),
      })
    );
  });

  test('after submit: form resets to empty draft state', async () => {
    const { container } = render(AssertionEditor, { props: { recording_id: 'rec-001' } });
    const targetInput = container.querySelector('.assertion-target') as HTMLInputElement;
    const descInput = container.querySelector('.assertion-description') as HTMLInputElement;
    const submitBtn = container.querySelector('.assertion-submit') as HTMLButtonElement;

    targetInput.value = 'div.hero';
    await fireEvent.input(targetInput);

    descInput.value = 'Hero section exists';
    await fireEvent.input(descInput);

    await fireEvent.click(submitBtn);

    // Draft should clear after submit
    expect(targetInput.value).toBe('');
    expect(descInput.value).toBe('');
  });

  test('cancel clears draft without sending', async () => {
    const { container } = render(AssertionEditor, { props: { recording_id: 'rec-001' } });
    const targetInput = container.querySelector('.assertion-target') as HTMLInputElement;
    const cancelBtn = container.querySelector('.assertion-cancel') as HTMLButtonElement;

    targetInput.value = 'span.label';
    await fireEvent.input(targetInput);

    await fireEvent.click(cancelBtn);

    expect(send).not.toHaveBeenCalled();
    expect(targetInput.value).toBe('');
  });
});
