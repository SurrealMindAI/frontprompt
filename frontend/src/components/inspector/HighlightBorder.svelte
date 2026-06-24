<!--
  HighlightBorder — animated rect die das gehoverte Element umrahmt.

  position: fixed mit getBoundingClientRect()-Koordinaten. Tracking durch
  rAF-Loop im parent InspectorLayer; this component nur ein dummer renderer.
  Transition animiert das Übergleiten von Element zu Element.

  Farbe: dynamisch (task "dynamisch färben"). Die Hover-Akzentfarbe ist
  cyan-basiert, wird aber gegen das gehoverte Element lightness-adaptiert
  (`element`-prop) damit der Rahmen sich IMMER vom Element abhebt — auf
  hellen wie dunklen Flächen. Hue bleibt cyan (Affordance-Identität).

  pointer-events: none — clicks gehen "durch" zur InspectorLayer-Surface die
  das eigentliche click-handling macht.
-->

<script lang="ts">
  import { contrastingColor } from '../../services/color-contrast';

  let {
    rect,
    element = null,
  }: {
    rect: { x: number; y: number; width: number; height: number };
    /** The hovered element — its background is sampled for contrast adaptation. */
    element?: Element | null;
  } = $props();

  // Cyan affordance hue, lightness-adapted against the hovered element's bg.
  const accent = $derived(contrastingColor('hsl(197, 100%, 73%)', element));
</script>

<div
  class="highlight-border"
  style:--fp-hl={accent}
  style:left="{rect.x}px"
  style:top="{rect.y}px"
  style:width="{rect.width}px"
  style:height="{rect.height}px"
></div>

<style>
  .highlight-border {
    position: fixed;
    pointer-events: none;
    outline: 2px solid var(--fp-hl);
    outline-offset: -1px;
    box-shadow:
      0 0 0 4px color-mix(in srgb, var(--fp-hl) 22%, transparent),
      0 0 16px color-mix(in srgb, var(--fp-hl) 45%, transparent);
    border-radius: 2px;
    z-index: 2;
    transition:
      left 100ms cubic-bezier(0.2, 0.8, 0.2, 1),
      top 100ms cubic-bezier(0.2, 0.8, 0.2, 1),
      width 100ms cubic-bezier(0.2, 0.8, 0.2, 1),
      height 100ms cubic-bezier(0.2, 0.8, 0.2, 1);
  }
</style>
