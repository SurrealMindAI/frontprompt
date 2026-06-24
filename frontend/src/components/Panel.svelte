<!--
  Panel — generischer Panel-Container, parameterisiert per `id`.

  Composition: PanelTab (always) + PanelContent + PanelResizer (when open).

  Layout-Order (per id, via flex direction + child order):
    left:   [content] [resizer] [tab]      (flex-direction: row,    tab right)
    right:  [tab]     [resizer] [content]  (flex-direction: row,    tab left)
    top:    [content] [resizer] [tab]      (flex-direction: column, tab bottom)
    bottom: [tab]     [resizer] [content]  (flex-direction: column, tab top)

  Wenn collapsed: only [tab] visible (content + resizer hidden via flex-shrink).
-->

<script lang="ts">
  import type { Snippet } from 'svelte';
  import { backendState } from '../backend-state/backend-state.svelte';
  import type { PanelId } from '../backend-state/panel-state.svelte';
  import { PANEL_CONFIGS } from '../backend-state/panel-state.svelte';
  import { pageTool } from '../local-state/page-tool.svelte';
  import PanelResizer from './PanelResizer.svelte';
  import PanelTab from './PanelTab.svelte';

  let {
    id,
    label,
    children,
  }: {
    id: PanelId;
    label: string;
    children?: Snippet;
  } = $props();

  const config = $derived(PANEL_CONFIGS[id]);
  // Cross-derive auf pageTool.active: wenn irgendein full-viewport-tool
  // (Inspector ODER Region-Draw) aktiv ist, panels rendern als Lasche
  // (user-intent in panels[id].open bleibt unangetastet).
  const isOpen = $derived(backendState.panel.effectiveOpenWith(id, pageTool.active));
  const isHorizontal = $derived(config.axis === 'horizontal');
  const tabAtEnd = $derived(id === 'left' || id === 'top');
</script>

<aside
  class="panel panel--{id}"
  class:panel--horizontal={isHorizontal}
  class:panel--vertical={!isHorizontal}
  class:panel--open={isOpen}
  class:panel--collapsed={!isOpen}
>
  <!--
    Order-Invariant: resizer sitzt IMMER zwischen content und tab
    (=between content and INNER edge). Sonst landet er am screen-edge und
    ist nicht greifbar.

    tabAtEnd=true  (left/top):  [content][resizer][tab]   tab am inner-edge (right/bottom)
    tabAtEnd=false (right/bot): [tab][resizer][content]   tab am inner-edge (left/top)
  -->

  <!--
    Content + Resizer bleiben IMMER im DOM (nicht via {#if isOpen} unmounted).
    Grid-cell-shrink + content-opacity-fade ergeben den "morph"-effect: das
    panel "klappt sich in die Lasche zusammen", statt instant zu verschwinden.
    CSS-toggle via .content--collapsed / .resizer-wrap--collapsed.
  -->

  {#if !tabAtEnd}
    <PanelTab {id} {label} />
    <div class="resizer-wrap" class:resizer-wrap--collapsed={!isOpen}>
      <PanelResizer {id} />
    </div>
  {/if}

  <div class="content" class:content--collapsed={!isOpen} aria-hidden={!isOpen}>
    {@render children?.()}
  </div>

  {#if tabAtEnd}
    <div class="resizer-wrap" class:resizer-wrap--collapsed={!isOpen}>
      <PanelResizer {id} />
    </div>
    <PanelTab {id} {label} />
  {/if}
</aside>

<style>
  .panel {
    background: var(--fp-color-surface-primary);
    box-sizing: border-box;
    overflow: hidden;
    /* pointer-events nur auf den Kind-elementen (PanelTab/content), NICHT
       auf dem grid-cell-bg — wenn collapsed soll page-clicks durch den
       grid-cell-area durchgehen. Page-content-area + PanelTab haben eigene
       pointer-events: auto. */
    pointer-events: none;
    display: flex;
    color: var(--fp-color-text-primary);
    /* opacity (statt background-alpha) damit alle child-elements + text +
       borders + custom backgrounds UNIFORM mitfaden. background-alpha allein
       würde nested rgba-children-bgs (log-header, tab, versions) mit eigener
       Opacity stehen lassen → flaky look mit dunklen Streifen. */
    opacity: 0.7;
    transition: opacity 160ms ease;
  }

  /* Wenn collapsed: panel-bg transparent — nur die kompakte 50×50 Lasche
     soll sichtbar sein, der Rest des grid-cells lässt page durch. */
  .panel--collapsed {
    background: transparent;
    border: none;
  }

  /* Hover: voll opaque. Shadow DOM (customElement mode) isoliert uns von
     host-page CSS wie example.com's `div { opacity: 0.8 }`. */
  .panel:hover {
    opacity: 1;
  }

  .panel--horizontal {
    flex-direction: row;
    width: 100%;
    height: 100%;
  }

  .panel--vertical {
    flex-direction: column;
    width: 100%;
    height: 100%;
  }

  .panel--top {
    border-bottom: 1px solid var(--fp-color-border-subtle);
  }
  .panel--bottom {
    border-top: 1px solid var(--fp-color-border-subtle);
  }
  .panel--left {
    border-right: 1px solid var(--fp-color-border-subtle);
  }
  .panel--right {
    border-left: 1px solid var(--fp-color-border-subtle);
  }

  .content {
    flex: 1 1 auto;
    min-width: 0;
    min-height: 0;
    overflow: auto;
    padding: 10px 14px;
    font-size: 12px;
    line-height: 1.45;
    color: var(--fp-color-text-primary);
    /* content nimmt clicks (panel-host hat pointer-events: none — siehe oben). */
    pointer-events: auto;
    /*
      Fade + flex-collapse beim Schließen — die grid-cell shrinkt animated (in
      App.svelte gridTemplateRows/Cols), content innendrin shrinkt mit, opacity
      blendet visuell aus. Flex-basis transition macht das clean ohne overflow-
      streifen.
    */
    transition:
      opacity 180ms ease,
      flex-grow 220ms cubic-bezier(0.4, 0, 0.2, 1),
      flex-basis 220ms cubic-bezier(0.4, 0, 0.2, 1),
      padding 220ms cubic-bezier(0.4, 0, 0.2, 1);
  }

  .content--collapsed {
    /*
      Flex-collapse: 0 grow / 0 shrink / 0 basis → content nimmt 0 space.
      Plus opacity:0 + pointer-events:none + padding:0 + overflow:hidden.
      Tab (PanelTab) ist flex-shrink:0 in seiner CSS → behält seine Größe
      und kann nicht squished werden vom content.
    */
    flex: 0 0 0;
    opacity: 0;
    pointer-events: none;
    padding: 0;
    overflow: hidden;
  }

  .resizer-wrap {
    display: contents;
  }

  /* Resizer ist nur sinnvoll wenn panel open — wenn collapsed verstecken
     wir ihn (sonst sitzt der drag-handle inmitten der Lasche). */
  .resizer-wrap--collapsed {
    display: none;
  }
</style>
