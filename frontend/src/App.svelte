<!--
  App — Composition root als Custom Element (Shadow-DOM-isoliert).

  ``<svelte:options customElement="fp-overlay" />`` triggert Svelte 5
  customElement-Modus:
    - App wird zu einer CE-Klasse (registriert via customElements.define in main.ts)
    - Shadow DOM mit mode='open' wird automatisch erstellt
    - ALLE component styles (App + Panel + Toolbar + DebugPanel) landen im
      shadow root statt document.head
    - Host-page CSS kann NICHT in shadow root reichen ("opacity: 0.8" auf div
      etc. greift nicht durch — siehe example.com regression)

  Layout: 3 rows × 3 columns, areas top/left/center/right/bottom.
  Sizes via overlay.gridTemplateRows/Columns ($derived from panel state).
  Transitions on grid-template animate panel open/close smoothly.

  Inspector-cross-derive: wenn ``backendState.inspector.active === true``,
  rendern alle panels als Lasche (via panel-state.gridTemplate*With(forceClosed))
  + ein <InspectorLayer /> sibling überdeckt den ganzen Viewport. Beim Toggle
  off kommen die panels automatisch in ihren Original-Zustand zurück (derived).

  about:blank-cross-derive: wenn ``overlayContext.isAboutBlank === true``,
  rendert das Dashboard im center slot und alle Panels werden als Lasche
  gerendert (via gridTemplate*With forceClosed OR). Panels bleiben sichtbar
  als Lasche-Indikatoren; panels[id].open-state wird nicht berührt.

  Toolbar lebt inline im Top-Panel content area. Linkes Panel ist
  <LeftPanel /> (Tools-Strip + Picks-Tab). Rechtes Panel ist <RightPanel />
  (Empty-state oder activePick-Details + Kommentar-Editor).
-->
<svelte:options customElement="fp-overlay" />

<script lang="ts">
  import { untrack } from 'svelte';
  import { backendState } from './backend-state/backend-state.svelte';
  import './backend-state/sync.svelte'; // side-effect: registers bridge.on('state_snapshot')
  import Dashboard from './components/dashboard/Dashboard.svelte';
  import DebugPanel from './components/DebugPanel.svelte';
  import DrawRegionLayer from './components/inspector/DrawRegionLayer.svelte';
  import InspectorLayer from './components/inspector/InspectorLayer.svelte';
  import RelationsLayer from './components/inspector/RelationsLayer.svelte';
  import { regionDraft } from './services/regions';
  import LeftPanel from './components/left-panel/LeftPanel.svelte';
  import Panel from './components/Panel.svelte';
  import RightPanel from './components/right-panel/RightPanel.svelte';
  import Toolbar from './components/Toolbar.svelte';
  import { pageTool } from './local-state/page-tool.svelte';
  import { pickClaim } from './local-state/pick-claim.svelte';
  import { quickCommentMode } from './local-state/quick-comment-mode.svelte';
  import QuickCommentBox from './components/inspector/QuickCommentBox.svelte';
  import type { Pick } from './_generated/state';
  import { resize } from './managers/resize-manager.svelte';
  import { setupPositionTracker } from './services/relations';
  import { overlayContext } from './services/context/overlay-context.svelte';

  // Während aktivem Drag disablen wir die grid-template-Transition,
  // sonst rendert jeder pointermove einen 220ms-Tween statt instant zu folgen.
  const isDragging = $derived(resize.isDragging);

  // HUD theme: a single fixed dark token-set, page-INDEPENDENT. There is no light
  // mode and no per-page adaptation. An earlier "dynamisch färben" feature derived
  // the theme from the PAGE background luminance, which made the HUD flip light/dark
  // per site (dark on Google, light on Wikipedia) and looked inconsistent — removed.
  // The tokens live unconditionally on `.grid` in the style block below.

  // about:blank-detect: reaktiv über overlayContext.isAboutBlank (refresh() nach
  // nav). Steuert das Dashboard-gate im center slot UND die forceClosed-OR für
  // panel-collapse.
  const isAboutBlank = $derived(overlayContext.isAboutBlank);

  // PageTool-cross-derive: alle panels rendern als Lasche solange ein
  // full-viewport-tool (Inspector ODER Region-Draw) ODER about:blank aktiv ist.
  // panel-state.gridTemplate*With(forceClosed) respektiert den flag,
  // user-intent in panels[id].open bleibt unberührt.
  const pageToolActive = $derived(pageTool.active);
  const inspectorActive = $derived(backendState.inspector.active);

  // Quick-comment mode (localState). When on, the whole HUD collapses to a small
  // hovering box (QuickCommentBox) and only the pick-surface stays live, so the
  // user can comment many elements very fast. Normal panels are hidden, the
  // auto-open-right-panel effect is suppressed, and the InspectorLayer mount is
  // swapped for a quick-mode one that opens an inline input on each pick.
  const quickMode = $derived(quickCommentMode.active);

  /**
   * Quick-comment pick handler: submit the pick (reusing the normal dedup +
   * append path) and immediately open the inline comment input anchored to the
   * pick's element rect. The InspectorLayer turns ``active`` off after each
   * pick (submitPick sets ``inspector.active = false``); the $effect below
   * re-activates it so the next click is captured without a re-toggle.
   */
  function onQuickPick(pick: Pick): void {
    const pickId = backendState.inspector.submitPick(pick);
    const r = pick.element.rect;
    quickCommentMode.openInput(
      pickId,
      r ? { x: r.x, y: r.y, width: r.width, height: r.height } : null
    );
  }

  // Keep the pick-surface live for the whole quick-comment session: submitPick
  // deactivates the inspector after each pick, so re-activate while the mode is
  // on (untracked on inspector.active to avoid a feedback loop). Entering the
  // mode also flips inspector.active on for the first click.
  $effect(() => {
    if (!quickCommentMode.active) return;
    untrack(() => {
      if (!backendState.inspector.active) backendState.inspector.activate();
    });
    // Re-track inspector.active so this effect re-runs after submitPick turns it
    // off, re-arming the surface for the next click.
    void backendState.inspector.active;
  });
  const gridTemplateRows = $derived(
    backendState.panel.gridTemplateRowsWith(pageToolActive || isAboutBlank)
  );
  const gridTemplateColumns = $derived(
    backendState.panel.gridTemplateColumnsWith(pageToolActive || isAboutBlank)
  );

  // Fade-in nach mount: initial opacity 0 → 1 via rAF-getriggerter class.
  // Eliminates "pop in" beim ersten paint nach cross-origin nav. Panels haben
  // ihre eigene opacity (default 0.7, hover 1.0) — die wirkt multiplikativ
  // über diese root-transition.
  let mounted = $state(false);
  $effect(() => {
    const handle = requestAnimationFrame(() => {
      mounted = true;
    });
    return () => cancelAnimationFrame(handle);
  });

  /**
   * Cross-store-reactivity: wenn ein Pick aktiv wird (von null → id ODER id-
   * wechsel), öffne das right-panel — das ist die "details ansicht". Gilt für
   * ALLE Pfade die activePickId setzen: PickItem-click, InspectorLayer-submit,
   * PickPicker-callback, PickDetails-Relations-row-click, RelationItem-endpoint-
   * click. DRY: ein effect statt boilerplate pro caller.
   *
   * Wichtig: nur ``activePickId`` ist als tracked dependency — den
   * ``panels.right.open``-read + togglePanel-write packen wir in untrack().
   * Sonst würde manuelles Schließen des right-panels den effect re-triggern und
   * wieder öffnen → user kann es nie schließen solange ein pick aktiv ist.
   */
  $effect(() => {
    const currentPick = backendState.inspector.activePickId;
    const currentRegion = backendState.inspector.activeRegionId;
    if (currentPick === null && currentRegion === null) return;
    // In quick-comment mode the right panel must stay closed — picks flow into
    // the inline input + hovering box, not the details view. (Tracked read of
    // quickCommentMode.active so the guard re-evaluates on mode toggle.)
    if (quickCommentMode.active) return;
    untrack(() => {
      if (!backendState.panel.panels.right.open) {
        backendState.panel.togglePanel('right');
      }
    });
  });

  /*
   * Position-tracker: registriert window-resize + scroll-listener die den
   * shared ``positionTracker.tick`` bumpen — alle $derived die live-rects
   * berechnen (svg-renderer, RelationsLayer) re-evaluieren dann sauber.
   * Setup einmal beim app-mount, cleanup beim unmount.
   */
  $effect(() => setupPositionTracker());
</script>

<div
  class="grid"
  class:grid--dragging={isDragging}
  class:grid--mounted={mounted}
  class:grid--quick={quickMode}
  style:grid-template-rows={gridTemplateRows}
  style:grid-template-columns={gridTemplateColumns}
>
  <div class="area area--top">
    <Panel id="top" label="top">
      <Toolbar />
    </Panel>
  </div>

  <div class="area area--left">
    <Panel id="left" label="left">
      <LeftPanel />
    </Panel>
  </div>

  <div class="area area--center">
    {#if isAboutBlank}
      <!--
        Dashboard: renders when page is about:blank. Inner wrapper restores
        pointer-events:auto (outer area--center is pointer-events:none).
        Scroll + centering handled by area--center--dashboard.
      -->
      <div class="area--center--dashboard">
        <Dashboard />
      </div>
    {/if}
  </div>

  <div class="area area--right">
    <Panel id="right" label="right">
      <RightPanel />
    </Panel>
  </div>

  <div class="area area--bottom">
    <Panel id="bottom" label="bottom">
      <DebugPanel />
    </Panel>
  </div>

  <!--
    QuickCommentBox lives INSIDE .grid so it inherits the --fp-color-* theme
    tokens (defined on .grid). Its own .qc-box/.qc-input
    are position:fixed so they escape the grid layout entirely; .grid--quick hides
    the panel .area children so only this box shows.
  -->
  <QuickCommentBox />
</div>

{#if quickMode}
  <!--
    Quick-comment mount: each captured pick is submitted AND opens an inline
    comment input near the element. ESC-on-empty exits the mode (handled inside
    QuickCommentBox via the keyboard service); onCancel here is a no-op so a
    click-on-nothing doesn't tear down the pick-surface mid-session.
  -->
  <InspectorLayer onPickCaptured={onQuickPick} onCancel={() => {}} />
{:else if inspectorActive}
  <!--
    InspectorLayer-callbacks gehen via pickClaim: routePick respects the current
    claim-callback (default-toggle: submitPick; PickPicker: setValue). Single
    mount-point, multiple consumers. Siehe local-state/pick-claim.svelte.ts.
  -->
  <InspectorLayer
    onPickCaptured={(pick) => pickClaim.routePick(pick)}
    onCancel={() => pickClaim.routeCancel()}
  />
{/if}

{#if regionDraft.drafting}
  <!--
    DrawRegionLayer: pointer-overlay für drag-rect-to-region. Liest/setzt
    regionDraft singleton state. Mutex mit Pick-mode via LeftPanelTools
    (button disabled wenn die andere mode aktiv ist).
  -->
  <DrawRegionLayer />
{/if}

<!--
  RelationsLayer: SVG-overlay zwischen page und HUD. Liest visibility intern
  aus uiPrefs.relationsVisible (kein conditional hier nötig — die Komponente
  rendered selber leer wenn off). Sibling zu InspectorLayer, kein z-index-Streit
  weil InspectorLayer pointer-events-on ist und RelationsLayer pointer-events-none.
-->
<RelationsLayer />

<style>
  /* ── HUD theme tokens ──────────────────────────────────────────────────
     Single source of truth for panel colours — one fixed dark set, page-
     independent (no light mode, no per-page adaptation). Components consume
     these via var(--fp-color-*). Custom properties inherit across the shadow
     boundary, so defining them on .grid reaches every panel + nested component.
     Values are inlined (not via the primitive scale) to stay self-contained
     inside the injected bundle. */
  .grid {
    --fp-color-surface-primary: rgb(18, 18, 26);
    --fp-color-surface-secondary: rgba(42, 42, 56, 0.92);
    --fp-color-surface-overlay: rgba(28, 28, 38, 0.96);
    --fp-color-text-primary: #e6e6f0;
    --fp-color-text-secondary: rgba(230, 230, 240, 0.72);
    --fp-color-text-muted: rgba(230, 230, 240, 0.45);
    --fp-color-border: rgba(255, 255, 255, 0.12);
    --fp-color-border-strong: rgba(255, 255, 255, 0.24);
    --fp-color-border-subtle: rgba(255, 255, 255, 0.06);
    --fp-color-accent: #6ea8fe;
    --fp-color-accent-text: #0b1220;
    --fp-color-error: #ff6b6b;
    --fp-color-hover-bg: rgba(255, 255, 255, 0.08);
  }

  .grid {
    display: grid;
    grid-template-areas:
      'top top top'
      'left center right'
      'bottom bottom bottom';
    height: 100%;
    width: 100%;
    font-family: -apple-system, system-ui, sans-serif;
    color: var(--fp-color-text-primary);
    /* Initial: transparent + invisible — wird via .grid--mounted nach rAF
       eingeblendet. Verhindert pop-in flash beim ersten paint. */
    opacity: 0;
    transition:
      grid-template-rows 220ms cubic-bezier(0.4, 0, 0.2, 1),
      grid-template-columns 220ms cubic-bezier(0.4, 0, 0.2, 1),
      opacity 280ms ease;
  }

  /* Erst nach erstem rAF-tick: in default-opacity eingehen.
     Multiplikativ mit panel-opacity (0.7 default, 1.0 hover) → smooth fade. */
  .grid--mounted {
    opacity: 1;
  }

  /* Beim Resize-Drag: keine transition für grid-template — pointermove updates
     sollen instant rendern. Opacity-transition bleibt weil sie nicht mit drag interferiert. */
  .grid--dragging {
    transition: opacity 280ms ease;
  }

  /* Quick-comment mode: hide every panel area — only the QuickCommentBox (a
     position:fixed child, unaffected by this) remains. The .grid container is
     kept (not display:none) so the box still inherits the theme tokens and so
     its fixed positioning resolves against the viewport. */
  .grid--quick .area {
    display: none;
  }

  .area {
    overflow: hidden; /* clip panel content during transition */
    display: flex; /* let the Panel inside flex naturally */
    /* Stacking-context: Panels MÜSSEN über dem RelationsLayer-SVG liegen
       (z-index 0). InspectorLayer (z-index 1) ist zwischen Panels (10) und
       SVG. Ohne explizites z-index wären die panels position:static und
       würden gegen position:fixed-siblings (Inspector/Relations) verlieren. */
    position: relative;
    z-index: 10;
  }

  .area--top {
    grid-area: top;
  }
  .area--bottom {
    grid-area: bottom;
  }
  .area--left {
    grid-area: left;
  }
  .area--right {
    grid-area: right;
  }
  .area--center {
    grid-area: center;
    pointer-events: none; /* page click-through */
  }

  /* Dashboard wrapper: restores pointer-events:auto inside the pointer-events:none
     center area. Provides scroll + centered layout for the Dashboard on about:blank. */
  .area--center--dashboard {
    pointer-events: auto;
    display: flex;
    justify-content: center;
    align-items: flex-start;
    padding: 24px 16px;
    overflow-y: auto;
    height: 100%;
    box-sizing: border-box;
  }
</style>
