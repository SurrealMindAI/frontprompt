<script lang="ts">
  import type { Snippet } from 'svelte';
  import { untrack } from 'svelte';
  import { createThemeContext, type FpThemeId } from './context.svelte.js';

  interface Props {
    initialTheme?: FpThemeId;
    children: Snippet;
  }

  let { initialTheme = 'light', children }: Props = $props();

  // untrack: initialTheme is intentionally read only once (initial value semantics).
  const ctx = createThemeContext(untrack(() => initialTheme));

  // Theme-Wechsel: setzt data-fp-theme auf <html>.
  // CSS-Cascade übernimmt den Rest — kein JS-Token-Flattening nötig.
  $effect(() => {
    if (typeof document === 'undefined') return;
    document.documentElement.setAttribute('data-fp-theme', ctx.themeId);
  });
</script>

{@render children()}
