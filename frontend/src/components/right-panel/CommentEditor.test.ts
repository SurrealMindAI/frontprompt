/**
 * CommentEditor tests.
 *
 * Tests: initial render, dirty state tracking, save, discard, edge cases.
 */
const send = vi.hoisted(() => vi.fn());
vi.mock('../../bridge/bridge.svelte', () => ({ bridge: { send } }));

import { describe, expect, test, afterEach } from 'vitest';
import { render, cleanup, fireEvent } from '@testing-library/svelte';
import CommentEditor from './CommentEditor.svelte';

afterEach(() => {
  cleanup();
  send.mockClear();
});

describe('CommentEditor — initial state', () => {
  test('renders textarea with initial comment value', () => {
    const { container } = render(CommentEditor, {
      pickId: 'pick-001',
      initialComment: 'hello world',
    });
    const ta = container.querySelector('textarea') as HTMLTextAreaElement;
    expect(ta.value).toBe('hello world');
  });

  test('renders label "notiz"', () => {
    const { getByText } = render(CommentEditor, {
      pickId: 'pick-001',
      initialComment: '',
    });
    expect(getByText('notiz')).toBeTruthy();
  });

  test('save button disabled when not dirty', () => {
    const { container } = render(CommentEditor, {
      pickId: 'pick-001',
      initialComment: 'original',
    });
    const saveBtn = container.querySelector('.editor__save') as HTMLButtonElement;
    expect(saveBtn.disabled).toBe(true);
  });

  test('discard button disabled when not dirty', () => {
    const { container } = render(CommentEditor, {
      pickId: 'pick-001',
      initialComment: 'original',
    });
    const discardBtn = container.querySelector('.editor__discard') as HTMLButtonElement;
    expect(discardBtn.disabled).toBe(true);
  });

  test('save button shows "Gespeichert" when clean', () => {
    const { container } = render(CommentEditor, {
      pickId: 'pick-001',
      initialComment: 'text',
    });
    const saveBtn = container.querySelector('.editor__save') as HTMLButtonElement;
    expect(saveBtn.textContent).toContain('Gespeichert');
  });
});

describe('CommentEditor — dirty state', () => {
  test('save button becomes enabled after editing', async () => {
    const { container } = render(CommentEditor, {
      pickId: 'pick-001',
      initialComment: 'original',
    });
    const ta = container.querySelector('textarea') as HTMLTextAreaElement;
    ta.value = 'modified';
    await fireEvent.input(ta);
    const saveBtn = container.querySelector('.editor__save') as HTMLButtonElement;
    expect(saveBtn.disabled).toBe(false);
  });

  test('discard button becomes enabled after editing', async () => {
    const { container } = render(CommentEditor, {
      pickId: 'pick-001',
      initialComment: 'original',
    });
    const ta = container.querySelector('textarea') as HTMLTextAreaElement;
    ta.value = 'changed';
    await fireEvent.input(ta);
    const discardBtn = container.querySelector('.editor__discard') as HTMLButtonElement;
    expect(discardBtn.disabled).toBe(false);
  });

  test('save button shows "Speichern *" when dirty', async () => {
    const { container } = render(CommentEditor, {
      pickId: 'pick-001',
      initialComment: 'original',
    });
    const ta = container.querySelector('textarea') as HTMLTextAreaElement;
    ta.value = 'something new';
    await fireEvent.input(ta);
    const saveBtn = container.querySelector('.editor__save') as HTMLButtonElement;
    expect(saveBtn.textContent).toContain('Speichern');
  });
});

describe('CommentEditor — save action', () => {
  test('clicking save on dirty state calls bridge.send', async () => {
    const { container } = render(CommentEditor, {
      pickId: 'pick-001',
      initialComment: 'original',
    });
    const ta = container.querySelector('textarea') as HTMLTextAreaElement;
    ta.value = 'updated comment';
    await fireEvent.input(ta);
    const saveBtn = container.querySelector('.editor__save') as HTMLButtonElement;
    await fireEvent.click(saveBtn);
    expect(send).toHaveBeenCalled();
  });

  test('clicking save on clean state does NOT call bridge.send', async () => {
    const { container } = render(CommentEditor, {
      pickId: 'pick-001',
      initialComment: 'same',
    });
    const saveBtn = container.querySelector('.editor__save') as HTMLButtonElement;
    await fireEvent.click(saveBtn);
    expect(send).not.toHaveBeenCalled();
  });

  test('save restores clean state (button disabled again)', async () => {
    const { container } = render(CommentEditor, {
      pickId: 'pick-001',
      initialComment: 'original',
    });
    const ta = container.querySelector('textarea') as HTMLTextAreaElement;
    ta.value = 'edited';
    await fireEvent.input(ta);
    const saveBtn = container.querySelector('.editor__save') as HTMLButtonElement;
    await fireEvent.click(saveBtn);
    // After save, baseline = editorValue, so dirty = false
    expect(saveBtn.disabled).toBe(true);
  });
});

describe('CommentEditor — discard action', () => {
  test('clicking discard reverts textarea to original value', async () => {
    const { container } = render(CommentEditor, {
      pickId: 'pick-001',
      initialComment: 'original',
    });
    const ta = container.querySelector('textarea') as HTMLTextAreaElement;
    ta.value = 'changed';
    await fireEvent.input(ta);
    const discardBtn = container.querySelector('.editor__discard') as HTMLButtonElement;
    await fireEvent.click(discardBtn);
    expect(ta.value).toBe('original');
  });

  test('clicking discard makes save button disabled again', async () => {
    const { container } = render(CommentEditor, {
      pickId: 'pick-001',
      initialComment: 'original',
    });
    const ta = container.querySelector('textarea') as HTMLTextAreaElement;
    ta.value = 'changed';
    await fireEvent.input(ta);
    const discardBtn = container.querySelector('.editor__discard') as HTMLButtonElement;
    await fireEvent.click(discardBtn);
    const saveBtn = container.querySelector('.editor__save') as HTMLButtonElement;
    expect(saveBtn.disabled).toBe(true);
  });
});
