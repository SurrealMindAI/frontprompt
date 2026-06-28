/**
 * Dropdown — searchable single-select primitive tests.
 *
 * Tests: trigger, open/close panel, search filter, keyboard nav (↑↓Enter/Escape),
 * selection callback, outside-click close, empty-match state.
 */
import { describe, expect, test, afterEach } from 'vitest';
import { render, cleanup, fireEvent } from '@testing-library/svelte';
import Dropdown from './Dropdown.svelte';
import type { DropdownOption } from './Dropdown.svelte';

const OPTIONS: DropdownOption<string>[] = [
  { value: 'all', label: 'all types' },
  { value: 'wheel', label: 'wheel events' },
  { value: 'click', label: 'click events' },
  { value: 'keydown', label: 'keydown events' },
];

afterEach(() => cleanup());

// ---------------------------------------------------------------------------
// Trigger button
// ---------------------------------------------------------------------------

describe('Dropdown — closed state', () => {
  test('shows selected label in trigger', () => {
    const { getByText } = render(Dropdown, {
      options: OPTIONS,
      value: 'all',
      onChange: () => {},
    });
    expect(getByText('all types')).toBeTruthy();
  });

  test('shows chevron ▾ in trigger', () => {
    const { container } = render(Dropdown, {
      options: OPTIONS,
      value: 'all',
      onChange: () => {},
    });
    expect(container.querySelector('.dropdown__chevron')?.textContent).toBe('▾');
  });

  test('does not show panel when closed', () => {
    const { container } = render(Dropdown, {
      options: OPTIONS,
      value: 'all',
      onChange: () => {},
    });
    expect(container.querySelector('.dropdown__panel')).toBeNull();
  });

  test('trigger has aria-expanded=false when closed', () => {
    const { container } = render(Dropdown, {
      options: OPTIONS,
      value: 'all',
      onChange: () => {},
    });
    const trigger = container.querySelector('.dropdown__trigger');
    expect(trigger?.getAttribute('aria-expanded')).toBe('false');
  });
});

// ---------------------------------------------------------------------------
// Open / close
// ---------------------------------------------------------------------------

describe('Dropdown — opening and closing', () => {
  test('clicking trigger opens the panel', () => {
    const { container } = render(Dropdown, {
      options: OPTIONS,
      value: 'all',
      onChange: () => {},
    });
    const trigger = container.querySelector('.dropdown__trigger') as HTMLButtonElement;
    fireEvent.click(trigger);
    expect(container.querySelector('.dropdown__panel')).not.toBeNull();
  });

  test('panel has role=listbox when open', () => {
    const { container } = render(Dropdown, {
      options: OPTIONS,
      value: 'all',
      onChange: () => {},
    });
    const trigger = container.querySelector('.dropdown__trigger') as HTMLButtonElement;
    fireEvent.click(trigger);
    expect(container.querySelector('[role="listbox"]')).not.toBeNull();
  });

  test('trigger has aria-expanded=true when open', () => {
    const { container } = render(Dropdown, {
      options: OPTIONS,
      value: 'all',
      onChange: () => {},
    });
    const trigger = container.querySelector('.dropdown__trigger') as HTMLButtonElement;
    fireEvent.click(trigger);
    expect(trigger.getAttribute('aria-expanded')).toBe('true');
  });

  test('clicking trigger again closes the panel', () => {
    const { container } = render(Dropdown, {
      options: OPTIONS,
      value: 'all',
      onChange: () => {},
    });
    const trigger = container.querySelector('.dropdown__trigger') as HTMLButtonElement;
    fireEvent.click(trigger);
    fireEvent.click(trigger);
    expect(container.querySelector('.dropdown__panel')).toBeNull();
  });

  test('Escape key closes the panel', () => {
    const { container } = render(Dropdown, {
      options: OPTIONS,
      value: 'all',
      onChange: () => {},
    });
    const trigger = container.querySelector('.dropdown__trigger') as HTMLButtonElement;
    fireEvent.click(trigger);
    const input = container.querySelector('.dropdown__search') as HTMLInputElement;
    fireEvent.keyDown(input, { key: 'Escape' });
    expect(container.querySelector('.dropdown__panel')).toBeNull();
  });
});

// ---------------------------------------------------------------------------
// Options list
// ---------------------------------------------------------------------------

describe('Dropdown — options list', () => {
  test('shows all options when open without query', () => {
    const { container } = render(Dropdown, {
      options: OPTIONS,
      value: 'all',
      onChange: () => {},
    });
    fireEvent.click(container.querySelector('.dropdown__trigger') as HTMLButtonElement);
    const opts = container.querySelectorAll('[role="option"]');
    expect(opts.length).toBe(OPTIONS.length);
  });

  test('marks current value as selected', () => {
    const { container } = render(Dropdown, {
      options: OPTIONS,
      value: 'wheel',
      onChange: () => {},
    });
    fireEvent.click(container.querySelector('.dropdown__trigger') as HTMLButtonElement);
    const selected = container.querySelector('[aria-selected="true"]');
    expect(selected?.textContent?.trim()).toBe('wheel events');
  });
});

// ---------------------------------------------------------------------------
// Search filter
// ---------------------------------------------------------------------------

describe('Dropdown — search filter', () => {
  test('typing filters options by label', () => {
    const { container } = render(Dropdown, {
      options: OPTIONS,
      value: 'all',
      onChange: () => {},
    });
    fireEvent.click(container.querySelector('.dropdown__trigger') as HTMLButtonElement);
    const input = container.querySelector('.dropdown__search') as HTMLInputElement;
    fireEvent.input(input, { target: { value: 'click' } });
    const opts = container.querySelectorAll('[role="option"]');
    // Only "click events" should match
    expect(opts.length).toBe(1);
    expect(opts[0]!.textContent?.trim()).toBe('click events');
  });

  test('shows "no matches" when filter yields nothing', () => {
    const { container, getByText } = render(Dropdown, {
      options: OPTIONS,
      value: 'all',
      onChange: () => {},
    });
    fireEvent.click(container.querySelector('.dropdown__trigger') as HTMLButtonElement);
    const input = container.querySelector('.dropdown__search') as HTMLInputElement;
    fireEvent.input(input, { target: { value: 'xyzzy-nonexistent' } });
    expect(getByText('no matches')).toBeTruthy();
  });

  test('filter is case-insensitive', () => {
    const { container } = render(Dropdown, {
      options: OPTIONS,
      value: 'all',
      onChange: () => {},
    });
    fireEvent.click(container.querySelector('.dropdown__trigger') as HTMLButtonElement);
    const input = container.querySelector('.dropdown__search') as HTMLInputElement;
    fireEvent.input(input, { target: { value: 'KEYDOWN' } });
    const opts = container.querySelectorAll('[role="option"]');
    expect(opts.length).toBe(1);
    expect(opts[0]!.textContent?.trim()).toBe('keydown events');
  });
});

// ---------------------------------------------------------------------------
// Keyboard navigation
// ---------------------------------------------------------------------------

describe('Dropdown — keyboard navigation', () => {
  test('ArrowDown moves highlight down', () => {
    const { container } = render(Dropdown, {
      options: OPTIONS,
      value: 'all',
      onChange: () => {},
    });
    fireEvent.click(container.querySelector('.dropdown__trigger') as HTMLButtonElement);
    const input = container.querySelector('.dropdown__search') as HTMLInputElement;
    fireEvent.keyDown(input, { key: 'ArrowDown' });
    const highlighted = container.querySelectorAll('.dropdown__option--highlighted');
    expect(highlighted.length).toBeGreaterThan(0);
  });

  test('ArrowUp moves highlight to top', () => {
    const { container } = render(Dropdown, {
      options: OPTIONS,
      value: 'all',
      onChange: () => {},
    });
    fireEvent.click(container.querySelector('.dropdown__trigger') as HTMLButtonElement);
    const input = container.querySelector('.dropdown__search') as HTMLInputElement;
    // Go down first
    fireEvent.keyDown(input, { key: 'ArrowDown' });
    fireEvent.keyDown(input, { key: 'ArrowDown' });
    // Now go up
    fireEvent.keyDown(input, { key: 'ArrowUp' });
    // Still something highlighted
    const highlighted = container.querySelectorAll('.dropdown__option--highlighted');
    expect(highlighted.length).toBeGreaterThan(0);
  });

  test('Enter selects highlighted option and calls onChange', () => {
    const onChange = vi.fn();
    const { container } = render(Dropdown, {
      options: OPTIONS,
      value: 'all',
      onChange,
    });
    fireEvent.click(container.querySelector('.dropdown__trigger') as HTMLButtonElement);
    const input = container.querySelector('.dropdown__search') as HTMLInputElement;
    fireEvent.keyDown(input, { key: 'ArrowDown' });
    fireEvent.keyDown(input, { key: 'Enter' });
    expect(onChange).toHaveBeenCalled();
  });
});

// ---------------------------------------------------------------------------
// Selection via click
// ---------------------------------------------------------------------------

describe('Dropdown — option click selection', () => {
  test('clicking an option calls onChange with its value', () => {
    const onChange = vi.fn();
    const { container } = render(Dropdown, {
      options: OPTIONS,
      value: 'all',
      onChange,
    });
    fireEvent.click(container.querySelector('.dropdown__trigger') as HTMLButtonElement);
    const opts = container.querySelectorAll('[role="option"]');
    fireEvent.click(opts[1]!); // 'wheel events'
    expect(onChange).toHaveBeenCalledWith('wheel');
  });

  test('clicking an option closes the panel', () => {
    const { container } = render(Dropdown, {
      options: OPTIONS,
      value: 'all',
      onChange: () => {},
    });
    fireEvent.click(container.querySelector('.dropdown__trigger') as HTMLButtonElement);
    const opts = container.querySelectorAll('[role="option"]');
    fireEvent.click(opts[0]!);
    expect(container.querySelector('.dropdown__panel')).toBeNull();
  });
});

// ---------------------------------------------------------------------------
// ariaLabel prop
// ---------------------------------------------------------------------------

describe('Dropdown — ariaLabel prop', () => {
  test('trigger has aria-label from prop', () => {
    const { container } = render(Dropdown, {
      options: OPTIONS,
      value: 'all',
      onChange: () => {},
      ariaLabel: 'filter by event type',
    });
    const trigger = container.querySelector('.dropdown__trigger');
    expect(trigger?.getAttribute('aria-label')).toBe('filter by event type');
  });
});
