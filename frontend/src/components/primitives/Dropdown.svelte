<!--
  Dropdown — searchable single-select primitive.

  Reusable für jede selection: type-filter, view-modes, target-pickers, etc.
  Controlled-component pattern (value + onChange), search-filter via lowercase
  substring contains.

  See script-JSDoc for full API + usage example.
-->

<script module lang="ts">
  /** Single option in the dropdown. Generic über value-type. */
  export interface DropdownOption<V extends string> {
    value: V;
    label: string;
  }
</script>

<script lang="ts" generics="T extends string">
  /**
   * Dropdown — single-select mit search-filter.
   *
   * @example
   * ```svelte
   * <Dropdown
   *   options={[
   *     { value: 'all', label: 'all types' },
   *     { value: 'wheel', label: 'wheel (123)' },
   *   ]}
   *   value={selected}
   *   onChange={(v) => selected = v}
   *   placeholder="Filter..."
   * />
   * ```
   *
   * Filter-semantik: ``lowercase substring contains`` über ``label``.
   * Keyboard: ↓/↑ navigates, Enter selects, Escape closes.
   */
  import { onDestroy } from 'svelte';

  let {
    options,
    value,
    onChange,
    placeholder = 'Search...',
    ariaLabel,
  }: {
    options: readonly DropdownOption<T>[];
    value: T;
    onChange: (value: T) => void;
    placeholder?: string;
    ariaLabel?: string;
  } = $props();

  let open = $state(false);
  let query = $state('');
  let highlightIdx = $state(0);
  let triggerEl: HTMLButtonElement | undefined = $state();
  let panelEl: HTMLDivElement | undefined = $state();
  let inputEl: HTMLInputElement | undefined = $state();

  const selectedLabel = $derived(options.find((o) => o.value === value)?.label ?? value);

  const filtered = $derived(
    query.trim() === ''
      ? options
      : options.filter((o) => o.label.toLowerCase().includes(query.toLowerCase().trim()))
  );

  // Reset highlight when filter changes
  $effect(() => {
    void filtered;
    highlightIdx = 0;
  });

  function openPanel(): void {
    open = true;
    query = '';
    highlightIdx = 0;
    // Autofocus input nach mount (next tick)
    queueMicrotask(() => inputEl?.focus());
  }

  function closePanel(): void {
    open = false;
    triggerEl?.focus();
  }

  function selectOption(opt: DropdownOption<T>): void {
    onChange(opt.value);
    closePanel();
  }

  function onTriggerClick(): void {
    if (open) closePanel();
    else openPanel();
  }

  function onInputKeydown(e: KeyboardEvent): void {
    if (e.key === 'ArrowDown') {
      e.preventDefault();
      highlightIdx = Math.min(highlightIdx + 1, filtered.length - 1);
    } else if (e.key === 'ArrowUp') {
      e.preventDefault();
      highlightIdx = Math.max(highlightIdx - 1, 0);
    } else if (e.key === 'Enter') {
      e.preventDefault();
      const opt = filtered[highlightIdx];
      if (opt) selectOption(opt);
    } else if (e.key === 'Escape') {
      e.preventDefault();
      closePanel();
    }
  }

  // Outside-click close (capture-phase damit page-handlers nicht stören)
  function onDocClick(e: MouseEvent): void {
    if (!open) return;
    const target = e.target as Node | null;
    if (!target) return;
    if (triggerEl?.contains(target)) return;
    if (panelEl?.contains(target)) return;
    closePanel();
  }

  $effect(() => {
    if (!open) return undefined;
    document.addEventListener('click', onDocClick, { capture: true });
    return () => {
      document.removeEventListener('click', onDocClick, { capture: true });
    };
  });

  onDestroy(() => {
    document.removeEventListener('click', onDocClick, { capture: true });
  });
</script>

<div class="dropdown">
  <button
    type="button"
    class="dropdown__trigger"
    class:dropdown__trigger--open={open}
    onclick={onTriggerClick}
    aria-label={ariaLabel}
    aria-haspopup="listbox"
    aria-expanded={open}
    bind:this={triggerEl}
  >
    <span class="dropdown__value">{selectedLabel}</span>
    <span class="dropdown__chevron" aria-hidden="true">▾</span>
  </button>

  {#if open}
    <div class="dropdown__panel" bind:this={panelEl} role="listbox">
      <input
        type="text"
        class="dropdown__search"
        bind:value={query}
        {placeholder}
        onkeydown={onInputKeydown}
        bind:this={inputEl}
        aria-label="filter options"
      />
      <div class="dropdown__list">
        {#each filtered as opt, i (opt.value)}
          <button
            type="button"
            class="dropdown__option"
            class:dropdown__option--highlighted={i === highlightIdx}
            class:dropdown__option--selected={opt.value === value}
            role="option"
            aria-selected={opt.value === value}
            onclick={() => selectOption(opt)}
            onmouseenter={() => (highlightIdx = i)}
          >
            {opt.label}
          </button>
        {:else}
          <div class="dropdown__empty">no matches</div>
        {/each}
      </div>
    </div>
  {/if}
</div>

<style>
  .dropdown {
    position: relative;
    display: inline-block;
  }

  .dropdown__trigger {
    display: inline-flex;
    align-items: center;
    gap: 6px;
    background: var(--fp-color-surface-secondary);
    border: 1px solid var(--fp-color-border);
    color: var(--fp-color-text-primary);
    font: inherit;
    font-size: 10px;
    padding: 3px 8px;
    border-radius: 3px;
    cursor: pointer;
    transition:
      background 120ms ease,
      border-color 120ms ease;
  }

  .dropdown__trigger:hover {
    background: var(--fp-color-surface-secondary);
    border-color: rgba(120, 180, 255, 0.4);
  }

  .dropdown__trigger:focus-visible,
  .dropdown__trigger--open {
    outline: none;
    border-color: rgba(120, 180, 255, 0.7);
  }

  .dropdown__value {
    min-width: 60px;
  }

  .dropdown__chevron {
    font-size: 9px;
    opacity: 0.6;
    line-height: 1;
  }

  .dropdown__panel {
    position: absolute;
    top: calc(100% + 4px);
    left: 0;
    min-width: 100%;
    max-width: 280px;
    background: var(--fp-color-surface-secondary);
    border: 1px solid var(--fp-color-text-muted);
    border-radius: 4px;
    box-shadow: 0 4px 16px rgba(0, 0, 0, 0.4);
    z-index: 100;
    display: flex;
    flex-direction: column;
    overflow: hidden;
  }

  .dropdown__search {
    background: var(--fp-color-surface-secondary);
    border: none;
    border-bottom: 1px solid var(--fp-color-border-subtle);
    color: var(--fp-color-text-primary);
    font: inherit;
    font-size: 11px;
    padding: 6px 10px;
    outline: none;
  }

  .dropdown__search::placeholder {
    color: var(--fp-color-text-muted);
  }

  .dropdown__list {
    max-height: 240px;
    overflow-y: auto;
    display: flex;
    flex-direction: column;
  }

  .dropdown__option {
    background: transparent;
    border: none;
    color: var(--fp-color-text-primary);
    font: inherit;
    font-size: 11px;
    text-align: left;
    padding: 5px 10px;
    cursor: pointer;
    transition:
      background 80ms ease,
      color 80ms ease;
  }

  .dropdown__option--highlighted {
    background: rgba(120, 180, 255, 0.18);
    color: var(--fp-color-text-primary);
  }

  .dropdown__option--selected::before {
    content: '✓ ';
    color: rgba(140, 230, 160, 0.95);
  }

  .dropdown__empty {
    padding: 12px 10px;
    text-align: center;
    color: var(--fp-color-text-muted);
    font-size: 10px;
    font-style: italic;
  }
</style>
