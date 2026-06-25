<!--
  PanelTab — die "Lasche" jedes Panels.
  Immer sichtbar (auch wenn Panel open).
  Click → toggle open/collapsed via backendState.panel.togglePanel(id).

  Position innerhalb des Panel-Containers (per flex order in Panel.svelte):
    left-panel:   tab is at RIGHT inner edge (next to center)
    right-panel:  tab is at LEFT inner edge
    top-panel:    tab is at BOTTOM inner edge
    bottom-panel: tab is at TOP inner edge

  Form (collapsed):
    top/bottom:  50px breit × 20px hoch (50px parallel zum viewport-rand,
                 20px "hereinragend" in den page-content)
    left/right:  20px breit × 50px hoch

  Rounded-corners-Logik: nur an der INNER edge (zur page hin), flat an der
  outer-edge (zum viewport-rand) — sieht aus wie eine echte Lasche die aus
  dem viewport-rand kommt.

  Icon-Mapping:
    left → ⚒ tools, right → ⓘ details, top → ▤ statistics, bottom → ⌬ debug
-->
<script lang="ts">
  import { backendState } from '../backend-state/backend-state.svelte';
  import type { PanelId } from '../backend-state/panel-state.svelte';
  import { PANEL_CONFIGS } from '../backend-state/panel-state.svelte';
  import { pageTool } from '../local-state/page-tool.svelte';

  let { id, label }: { id: PanelId; label: string } = $props();

  /*
    EffectiveOpenWith respektiert den cross-store override (pageTool.active=true
    → panels rendern als Lasche). Panel.svelte nutzt dieselbe Logik — so kommt
    Tab + Panel-container immer aus derselben source-of-truth, kein visual
    mismatch (e.g. tab denkt "open", panel denkt "collapsed").
  */
  const isOpen = $derived(backendState.panel.effectiveOpenWith(id, pageTool.active));
  const config = $derived(PANEL_CONFIGS[id]);
  const isHorizontal = $derived(config.axis === 'horizontal');

  function toggle() {
    backendState.panel.togglePanel(id);
  }

  /**
   * Icon-Mapping pro Panel — semantisch passend zum Panel-Inhalt:
   *   - left (tools): inspector-toggle + picks/relations management → ⚒
   *   - right (details): active-pick + relations details → ⓘ
   *   - top (statistics): stat-pills + toolbar → ▤ (bars)
   *   - bottom (debug): state-snapshot dump, logs → ⌬
   * ``label`` bleibt als a11y-name + tooltip-text.
   */
  const ICONS: Record<PanelId, string> = {
    left: '⚒',
    right: 'ⓘ',
    top: '▤',
    bottom: 'Debug',
  };
  const icon = $derived(ICONS[id]);

  // Arrow zeigt INWARDS wenn open (= "click to collapse"),
  //         OUTWARDS wenn collapsed (= "click to expand").
  const arrow = $derived.by(() => {
    if (isOpen) {
      if (id === 'left') return '◀';
      if (id === 'right') return '▶';
      if (id === 'top') return '▲';
      return '▼';
    } else {
      if (id === 'left') return '▶';
      if (id === 'right') return '◀';
      if (id === 'top') return '▼';
      return '▲';
    }
  });
</script>

<button
  type="button"
  class="tab tab--{id}"
  class:tab--horizontal={isHorizontal}
  class:tab--vertical={!isHorizontal}
  class:tab--open={isOpen}
  onclick={toggle}
  aria-label="toggle {label} panel"
  aria-expanded={isOpen}
  title={`${isOpen ? 'Collapse' : 'Expand'} ${label}`}
>
  <span class="tab__arrow">{arrow}</span>
  {#if !isOpen}
    <span class="tab__icon" aria-hidden="true">{icon}</span>
  {/if}
</button>

<style>
  .tab {
    background: var(--fp-color-surface-secondary);
    border: none;
    color: var(--fp-color-text-primary);
    font-family: inherit;
    font-size: 11px;
    font-weight: 500;
    letter-spacing: 0.02em;
    cursor: pointer;
    padding: 0;
    margin: 0;
    display: flex;
    align-items: center;
    justify-content: center;
    gap: 6px;
    box-sizing: border-box;
    user-select: none;
    /* Tab darf NICHT von flex-shrink squeezed werden — sonst gewinnt content
       (mit flex-grow:1) in collapsed-state den Platz. flex-shrink:0 + die
       fixe height/width im :not(.tab--open) garantiert dass die Lasche ihre
       volle Größe behält. */
    flex-shrink: 0;
    /* Nur Farb-Transitions — die "morph"-Animation (width/height/border-radius/
       margin tweens beim open↔collapsed) wurde bewusst entfernt: die Laschen
       sollen instant ihre Form annehmen, nicht herumwandern. */
    transition:
      background 160ms ease,
      color 160ms ease;
    pointer-events: auto;
  }

  .tab:hover {
    background: var(--fp-color-surface-secondary);
    color: var(--fp-color-text-primary);
  }

  .tab:focus-visible {
    outline: 1px solid rgba(120, 180, 255, 0.6);
    outline-offset: -1px;
  }

  /*
    Wenn Panel OPEN: Lasche ist ein schmaler 18px-strip an der inner edge —
    full-axis-länge für leichtes treffen.
    Wenn Panel COLLAPSED:
      - top/bottom (vertical-axis): full-width × 20px tief. Streifen statt
        zentriertem Quadrat — Ecken zu left/right collapsed-panels bleiben
        sauber (keine dunklen halbflächen drumherum).
      - left/right (horizontal-axis): 20px breit × 50px hoch, vertikal-
        zentriert in der 20px grid-cell. Echte schmale Lasche.
  */

  /* Horizontal-axis panels (left/right): vertical bars.
     NO writing-mode/column — that combination forced both tabs into the same
     visual order (icon-left/arrow-right) and skewed centring. Instead the icon
     + arrow sit in a plain horizontal row, centred on both axes via the base
     align-items/justify-content:center, and the per-side flex-direction below
     pins the arrow to the INNER edge (toward the page) for each side. */
  .tab--horizontal {
    width: 18px;
    height: 100%;
  }

  .tab--horizontal:not(.tab--open) {
    /* Full-height-Bar über die ganze Mittelzeile — nutzt den geclaimten Randplatz. */
    width: 100%;
    height: 100%;
    margin: 0;
  }

  /* Vertical-axis panels (top/bottom). */
  .tab--vertical {
    height: 18px;
    width: 100%;
    flex-direction: row;
    writing-mode: horizontal-tb;
  }

  .tab--vertical:not(.tab--open) {
    /* Full-width streifen statt zentriertem Quadrat — verhindert Eck-Streifen
       in den Bereichen wo top/bottom auf left/right collapsed-cells stoßen. */
    height: 100%;
    width: 100%;
    margin: 0;
    flex-direction: row;
    writing-mode: horizontal-tb;
  }

  /*
    Per-id rounded-corners — nur an der INNER edge (page-side), flat an der
    outer-edge (viewport-rand). Macht die Lasche zu einer "fortsatz-lasche"-
    silhouette die aus dem rand wächst.

    Bei left/right (kompakt 20×50) markante 6px — die Lasche steht klar
    sichtbar aus dem rand. Bei top/bottom (full-width streifen) subtle 0 —
    eine softe Kante an der inner-edge würde komisch aussehen weil die Lasche
    sich quer durchs viewport zieht.
  */
  /* DOM order is [arrow][icon]. Left tab's inner edge is the RIGHT, so we want
     icon (outer) left + arrow (inner) right → row-reverse. Right tab's inner
     edge is the LEFT, so arrow (inner) left + icon (outer) right → row. */
  .tab--left:not(.tab--open) {
    /* inner edge = right */
    flex-direction: row-reverse;
    border-radius: 0 6px 6px 0;
  }
  .tab--right:not(.tab--open) {
    /* inner edge = left */
    flex-direction: row;
    border-radius: 6px 0 0 6px;
  }
  /* top/bottom collapsed: kein border-radius — full-width streifen bleibt flat. */

  .tab__arrow {
    font-size: 12px;
    line-height: 1;
    opacity: 0.7;
    transition: opacity 120ms ease;
  }

  .tab:hover .tab__arrow {
    opacity: 1;
  }

  .tab__icon {
    font-size: 16px;
    line-height: 1;
    opacity: 0.85;
  }

  .tab:hover .tab__icon {
    opacity: 1;
  }
</style>
