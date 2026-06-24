<!--
  SvgRenderer — Phase-1-impl der RelationsRenderer-Interface.

  Rendert pro DrawCommand:
    - Wide-stroke glow-layer (filter:blur, opacity 0.3)
    - Main stroke: gestrichelt mit @keyframes dash → "fließende" Linie
    - Endpoint-circles: pulsierend via @keyframes pulse-endpoint
    - Arrow-marker für directed kinds (triggers, part_of); relates_to ohne
    - **Midpoint label**: kind-badge + optional note, sitzt auf der bezier-curve
      via cmd.midpoint (t=0.5)
    - **Pick-rect borders**: pro pick der in EINER Relation involved ist,
      ein gestricheltes Element-rect (zeigt wo der Pick auf der Page liegt).
      Macht die Visual-zu-DOM-Verbindung explizit.

  Color-per-kind via CSS-vars (animation-tokens). Hovered-relation bekommt
  opacity-boost + wider stroke + brighter label.

  Bundled props: ``picks`` für die rect-borders. Wir filtern hier selbst nach
  "involved in any command" — der Renderer entscheidet aus seinem context.

  Z-index 0: HINTER den HUD-panels, VOR der page. InspectorLayer (z-index 1)
  sitzt darüber wenn aktiv. Pointer-events none — Edit/Delete passiert via
  RelationsTab-Liste.
-->
<script lang="ts">
  import { colorForIndex } from '../../color-palette';
  import { contrastingColor } from '../../color-contrast';
  import { DEFAULTS, colorVarFor } from '../animation-tokens';
  import type { DrawCommand } from '../path-planner';
  import { positionService } from '../position-service.svelte';
  import { positionTracker } from '../position-tracker.svelte';
  import type { Pick, Region } from '../../../_generated/state';
  import { overlayContext } from '../../context/overlay-context.svelte';

  let {
    commands,
    hoveredRelationId,
    picks = [],
    regions = [],
    activePickId = null,
    activeRegionId = null,
    showPicks = true,
  }: {
    commands: readonly DrawCommand[];
    hoveredRelationId: string | null;
    /** Picks-list — rect-borders pro pick, via live DOM-lookup. */
    picks?: readonly Pick[];
    /** Regions-list — bounding-box border, via live member-pick-rects. */
    regions?: readonly Region[];
    /** Active pick (selection-prominency: thin solid pulsing line). */
    activePickId?: string | null;
    /** Active region (selection-prominency: thicker stroke + heavier fill). */
    activeRegionId?: string | null;
    /**
     * Sollen pick-rect-borders gerendert werden? Vorher gekoppelt an
     * "commands.length > 0" — entkoppelt, von außen gesteuert
     * via uiPrefs.picksVisible.
     */
    showPicks?: boolean;
  } = $props();

  // Live-rect-resolving — positionTracker.tick als reactive dep damit
  // window-resize / scroll-events ein re-eval triggern.
  const livePickRects = $derived.by(() => {
    void positionTracker.tick;
    return new Map(picks.map((p) => [p.pick_id, positionService.liveRectForPick(p)]));
  });
  const liveRegionRects = $derived.by(() => {
    void positionTracker.tick;
    return new Map(regions.map((r) => [r.region_id, positionService.liveRectForRegion(r, picks)]));
  });

  // Dynamic contrast (task: "dynamisch färben") — each marker's palette colour is
  // lightness-adapted against the background it actually sits over, so it always
  // stands out. Hue is preserved (color_index identity stays recognisable). Keyed
  // per id; recomputed on positionTracker.tick to follow nav/mutation (bg lookups
  // are WeakMap-cached, so per-tick cost is a map hit, not a getComputedStyle walk).
  const adaptedPickColors = $derived.by(() => {
    void positionTracker.tick;
    return new Map(
      picks.map((p) => [
        p.pick_id,
        contrastingColor(colorForIndex(p.color_index ?? 0), positionService.liveElementForPick(p)),
      ])
    );
  });
  const adaptedRegionColors = $derived.by(() => {
    void positionTracker.tick;
    return new Map(
      regions.map((r) => {
        // Regions have no element of their own — sample the first resolvable
        // member-pick's background as the region's contrast reference.
        let el: Element | null = null;
        for (const id of r.member_pick_ids ?? []) {
          const mp = picks.find((p) => p.pick_id === id);
          if (mp) el = positionService.liveElementForPick(mp);
          if (el) break;
        }
        return [r.region_id, contrastingColor(colorForIndex(r.color_index ?? 0), el)];
      })
    );
  });

  // CSS-vars als style-string für den root <svg> — token-defaults zentral.
  const styleAttr = Object.entries(DEFAULTS)
    .map(([k, v]) => `${k}: ${v}`)
    .join('; ');

  // Distinct kinds in der aktuellen command-liste — wir brauchen nur die
  // markers die tatsächlich benötigt werden (sonst sind defs spam).
  const directedKinds = $derived(
    Array.from(new Set(commands.filter((c) => c.isDirected).map((c) => c.kind)))
  );

  // Pick-rect-borders sind ein eigenes erstklassiges visual-konzept (entkoppelt
  // von der relations-existence). Sichtbarkeit kommt von außen via
  // uiPrefs.picksVisible → showPicks-prop.
  const showPickBorders = $derived(showPicks);

  // Truncate label-text damit's nicht über die Linie ausläuft.
  function truncate(s: string, max: number): string {
    return s.length <= max ? s : s.slice(0, max - 1) + '…';
  }
</script>

<svg class="relations-svg" style={styleAttr} aria-hidden="true">
  <defs>
    {#each directedKinds as kind (kind)}
      <marker
        id={`arrow-${kind}`}
        viewBox="0 0 10 10"
        refX="8"
        refY="5"
        markerWidth="6"
        markerHeight="6"
        orient="auto-start-reverse"
      >
        <path d="M 0 0 L 10 5 L 0 10 z" fill={colorVarFor(kind)} />
      </marker>
    {/each}
  </defs>

  <!--
    Pick-rect-borders — color-coded per pick (Schema 0.5.0+).
    Stroke kommt aus der 32-Farben-Palette via color_index, position aus
    live-DOM-lookup (positionService). Selection-prominency: aktive pick
    kriegt thin solid pulsing line (via .rel-picks__box--selected).
    **Ground-truth-render**: wenn liveRect null (element nicht auf current
    page resolvable), wird NICHT gerendert — verhindert ghost-boxes nach
    cross-origin nav.
  -->
  {#if showPickBorders}
    {#each picks as pick (pick.pick_id)}
      {@const liveRect = livePickRects.get(pick.pick_id)}
      {#if liveRect && overlayContext.isOwned(pick)}
        {@const pickColor =
          adaptedPickColors.get(pick.pick_id) ?? colorForIndex(pick.color_index ?? 0)}
        {@const isSelected = activePickId === pick.pick_id}
        <rect
          class="rel-picks__box"
          class:rel-picks__box--selected={isSelected}
          x={liveRect.x}
          y={liveRect.y}
          width={liveRect.width}
          height={liveRect.height}
          style={`stroke: ${pickColor}`}
        />
      {/if}
    {/each}
  {/if}

  <!--
    Region-rect-borders — dicker, color-coded per region (Schema 0.5.0+).
    Position aus live member-pick bounding-box (positionService). Active
    region kriegt bolder + slight fill. **Ground-truth-render**: null →
    nicht rendern (kein page-absolute fallback nach nav).
  -->
  {#each regions as region (region.region_id)}
    {@const liveRect = liveRegionRects.get(region.region_id)}
    {#if liveRect && overlayContext.isOwned(region)}
      {@const regionColor =
        adaptedRegionColors.get(region.region_id) ?? colorForIndex(region.color_index ?? 0)}
      {@const isActive = activeRegionId === region.region_id}
      <rect
        class="rel-regions__box"
        class:rel-regions__box--active={isActive}
        x={liveRect.x}
        y={liveRect.y}
        width={liveRect.width}
        height={liveRect.height}
        style={`stroke: ${regionColor}; fill: ${regionColor}; fill-opacity: ${isActive ? 0.12 : 0.05};`}
      />
    {/if}
  {/each}

  {#each commands as cmd (cmd.relationId)}
    {#if overlayContext.isOwned({ origin_session: cmd.origin_session })}
      {@const stroke = colorVarFor(cmd.kind)}
      {@const isHovered = cmd.relationId === hoveredRelationId}
      {@const noteTrimmed = cmd.note ? truncate(cmd.note, 28) : null}
      {@const labelText = noteTrimmed ? `${cmd.kind} · ${noteTrimmed}` : cmd.kind}
      {@const labelW = labelText.length * 6.5 + 14}
      {@const labelH = 18}
      <g class="rel" class:rel--hovered={isHovered} data-kind={cmd.kind}>
        <!-- Glow halo (wide, blurred, semi-transparent) -->
        <path class="rel__glow" d={cmd.pathD} style={`stroke: ${stroke}`} />
        <!-- Main dashed stroke + optional arrowhead -->
        <path
          class="rel__main"
          d={cmd.pathD}
          style={`stroke: ${stroke}`}
          marker-end={cmd.isDirected ? `url(#arrow-${cmd.kind})` : undefined}
        />
        <!-- Endpoint pulses -->
        <circle
          class="rel__endpoint rel__endpoint--src"
          cx={cmd.source.cx}
          cy={cmd.source.cy}
          r="4"
          style={`fill: ${stroke}`}
        />
        <circle
          class="rel__endpoint rel__endpoint--tgt"
          cx={cmd.target.cx}
          cy={cmd.target.cy}
          r="4"
          style={`fill: ${stroke}`}
        />

        <!--
          Midpoint label — kind-badge + optional note. SVG-only (kein
          foreignObject — Shadow-DOM-vermeidung). Background-rect ist dimensions-
          derived via text-length-heuristik (~6.5px/char + padding) — gut genug
          ohne text-measurement-roundtrip.
        -->
        <g
          class="rel__label"
          transform={`translate(${cmd.midpoint.cx - labelW / 2}, ${cmd.midpoint.cy - labelH / 2})`}
        >
          <rect
            class="rel__label-bg"
            x="0"
            y="0"
            width={labelW}
            height={labelH}
            rx="9"
            ry="9"
            style={`stroke: ${stroke}`}
          />
          <text class="rel__label-text" x={labelW / 2} y={labelH / 2} style={`fill: ${stroke}`}>
            {labelText}
          </text>
        </g>
      </g>
    {/if}
  {/each}
</svg>

<style>
  .relations-svg {
    position: fixed;
    inset: 0;
    width: 100%;
    height: 100%;
    pointer-events: none;
    /* z-index 0: hinter den HUD-Panels (.area = z-index 10) aber vor der Page.
       InspectorLayer (z-index 1) sitzt zwischen SVG und Panels wenn aktiv. */
    z-index: 0;
    overflow: visible;
  }

  /* Pick-rect-borders — gestrichelt, dünn. Stroke-color kommt inline aus
     color-palette (Schema 0.5.0+). Fill: none — ein subtiler weißer Fill
     komponiert bei N überlappenden Picks zu einem milchigen Schleier über
     der Host-Seite (effektive Deckung 1 − 0.97^N; bei N≈96 ~94% weiß). Die
     sichtbare Box-Identität ist allein der dashed stroke. */
  .rel-picks__box {
    fill: none;
    stroke-width: 1.5;
    stroke-dasharray: 4 3;
    stroke-opacity: 0.65;
    pointer-events: none;
  }

  /* Pick-selection: thin solid pulsing line.
     Override: dasharray off, opacity-pulse statt size-pulse damit das rect
     beim pulse nicht "wackelt". */
  .rel-picks__box--selected {
    stroke-dasharray: none;
    stroke-width: 1.5;
    stroke-opacity: 1;
    animation: rel-pick-pulse 1.4s ease-in-out infinite;
  }

  /* Region-rect-borders — dicker, größere dashes. Stroke + fill kommen inline
     aus der color-palette (Schema 0.5.0+). Active region kriegt thicker stroke. */
  .rel-regions__box {
    stroke-width: 2;
    stroke-dasharray: 8 5;
    pointer-events: none;
  }

  .rel-regions__box--active {
    stroke-width: 3;
  }

  @keyframes rel-pick-pulse {
    0%,
    100% {
      stroke-opacity: 1;
    }
    50% {
      stroke-opacity: 0.35;
    }
  }

  .rel__glow {
    fill: none;
    stroke-width: var(--rel-glow-width);
    opacity: var(--rel-glow-opacity);
    filter: blur(var(--rel-glow-blur));
  }

  .rel__main {
    fill: none;
    stroke-width: var(--rel-stroke-width);
    stroke-dasharray: 10 5;
    stroke-linecap: round;
    animation: rel-dash var(--rel-dash-period) linear infinite;
  }

  .rel__endpoint {
    animation: rel-pulse var(--rel-pulse-period) ease-in-out infinite;
  }

  .rel__endpoint--tgt {
    animation-delay: calc(var(--rel-pulse-period) / -2);
  }

  .rel__label-bg {
    fill: rgba(15, 18, 25, 0.92);
    stroke-width: 1;
    opacity: 0.95;
  }

  .rel__label-text {
    font-family: 'SF Mono', 'JetBrains Mono', Menlo, Consolas, monospace;
    font-size: 10px;
    font-weight: 500;
    text-anchor: middle;
    dominant-baseline: central;
  }

  .rel--hovered .rel__glow {
    opacity: calc(var(--rel-glow-opacity) * 2);
    stroke-width: calc(var(--rel-glow-width) * 1.4);
  }

  .rel--hovered .rel__main {
    stroke-width: calc(var(--rel-stroke-width) * 1.5);
  }

  .rel--hovered .rel__label-bg {
    fill: rgba(20, 25, 35, 1);
    opacity: 1;
    stroke-width: 1.5;
  }

  @keyframes rel-dash {
    to {
      stroke-dashoffset: -15;
    }
  }

  @keyframes rel-pulse {
    0%,
    100% {
      r: 4;
      opacity: 1;
    }
    50% {
      r: 6;
      opacity: 0.6;
    }
  }
</style>
