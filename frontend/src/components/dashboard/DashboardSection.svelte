<!--
  DashboardSection — labeled card/group wrapper for Dashboard.svelte.

  Props:
    title: string — section heading

  Renders a titled card with consistent dark-palette padding and border.
  No interactivity, no onclick, no animations.
  Dashboard-scoped: not added to any global component index.

  All styles live in the <style> block (shadow DOM).
-->
<script lang="ts">
  let { title, children }: { title: string; children?: import('svelte').Snippet } = $props();
</script>

<section class="section">
  <h3 class="section__title">{title}</h3>
  <div class="section__body">
    {@render children?.()}
  </div>
</section>

<style>
  .section {
    display: flex;
    flex-direction: column;
    background: var(--fp-color-surface-secondary);
    border: 1px solid var(--fp-color-border);
    border-radius: 14px;
    padding: 18px 20px;
    box-shadow: 0 1px 2px rgba(0, 0, 0, 0.04), 0 8px 24px rgba(0, 0, 0, 0.06);
  }

  .section__title {
    font-family: -apple-system, system-ui, sans-serif;
    font-size: 12px;
    font-weight: 700;
    text-transform: uppercase;
    letter-spacing: 0.1em;
    color: var(--fp-color-accent);
    margin: 0 0 14px 0;
    padding-bottom: 10px;
    border-bottom: 1px solid var(--fp-color-border-subtle);
  }

  .section__body {
    display: flex;
    flex-direction: column;
    gap: 2px;
  }
</style>
