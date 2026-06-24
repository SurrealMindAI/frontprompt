<!--
  InspectorLayer — fullscreen capture-Surface = generic Element-Picker.

  Output-Contract (definitive): emittiert genau EIN ``Pick``-Objekt pro
  successful click (uuid4 pick_id, fingerprint, selector, rect, snippet).
  WAS damit passiert entscheidet der Mount-Caller via ``onPickCaptured``-prop.

  Default-mount (App.svelte, vom Inspector-Toggle) macht ``submitPick`` —
  fügt den Pick zur Picks-Liste hinzu + deaktiviert den Inspector. Andere
  Caller (z.B. PickPicker im RelationsTab "Inspect"-button) übergeben einen
  custom callback, der den Pick nur LOCAL konsumiert (z.B. "set as source")
  ohne Persistierung. DRY: eine Inspector-Implementation, viele Konsumenten.

  Mount-gate liegt beim Caller. Beim Unmount: $effect-cleanup räumt rAF +
  Keyboard-subscription auf.

  Filter elementsFromPoint:
    Wir skippen alles innerhalb der <fp-overlay> Shadow-DOM (sonst würden wir
    unsere eigenen Panels / Buttons highlightieren). closest('fp-overlay')
    funktioniert weil fp-overlay ein Host-Element im Light-DOM ist; alles
    in seinem shadow-tree ist mit closest() im DOM-Sinne darunter.

  Cancel-flow: wenn ``onCancel`` nicht übergeben wird, geht der Default-cancel
  zum globalen ``backendState.inspector.cancel()`` (für den main-toggle).
  PickPicker übergibt eigenen onCancel der den one-shot-mode beendet ohne
  inspector.active zu touchen.
-->

<script lang="ts">
  import { backendState } from '../../backend-state/backend-state.svelte';
  import { buildFingerprint, generateCssSelector } from '../../services/element-locator';
  import { keyboard } from '../../services/keyboard/keyboard.svelte';
  import { forwardWheel } from '../../services/scroll-router';
  import type { Pick } from '../../_generated/state';
  import HighlightBorder from './HighlightBorder.svelte';

  let {
    onPickCaptured,
    onCancel,
  }: {
    /**
     * Called with the captured Pick on click. Default: forward to
     * ``backendState.inspector.submitPick`` (legacy add-to-list behavior).
     * Callers can supply a custom handler to redirect the pick — e.g.
     * the PickPicker's inspect-button uses this to set a relation-source.
     */
    onPickCaptured?: (pick: Pick) => void;
    /**
     * Called when the user cancels (ESC, click on nothing). Default: forward
     * to ``backendState.inspector.cancel()``. PickPicker overrides to exit
     * its one-shot mode without touching the inspector-active toggle.
     */
    onCancel?: () => void;
  } = $props();

  const handlePick = $derived(
    onPickCaptured ?? ((pick: Pick) => backendState.inspector.submitPick(pick))
  );
  const handleCancel = $derived(onCancel ?? (() => backendState.inspector.cancel()));

  let hoveredEl = $state<Element | null>(null);
  let rect = $state<{ x: number; y: number; width: number; height: number } | null>(null);

  let rafHandle: number | null = null;

  function startTracking(): void {
    if (rafHandle !== null) return;
    function loop(): void {
      if (hoveredEl) {
        const r = hoveredEl.getBoundingClientRect();
        rect = { x: r.x, y: r.y, width: r.width, height: r.height };
      }
      rafHandle = requestAnimationFrame(loop);
    }
    rafHandle = requestAnimationFrame(loop);
  }

  function stopTracking(): void {
    if (rafHandle !== null) {
      cancelAnimationFrame(rafHandle);
      rafHandle = null;
    }
  }

  function findTarget(x: number, y: number): Element | null {
    const els = document.elementsFromPoint(x, y);
    for (const el of els) {
      // Skip unsere eigene Shadow-DOM HUD (fp-overlay custom element ist im Light DOM
      // als sibling, alles drinnen ist via .closest('fp-overlay') erreichbar).
      if (el.closest('fp-overlay')) continue;
      // Skip die InspectorLayer-Surface selbst.
      if (el.classList && el.classList.contains('inspector-layer')) continue;
      return el;
    }
    return null;
  }

  function onPointerMove(e: PointerEvent): void {
    const target = findTarget(e.clientX, e.clientY);
    if (target !== hoveredEl) {
      hoveredEl = target;
      if (target) {
        // Initial rect-paint sofort (sonst gibt's einen 1-Frame-Flicker bevor rAF zuschlägt).
        const r = target.getBoundingClientRect();
        rect = { x: r.x, y: r.y, width: r.width, height: r.height };
        startTracking();
      } else {
        rect = null;
        stopTracking();
      }
    }
  }

  function buildPick(target: Element): Pick {
    const fingerprint = buildFingerprint(target);
    const selector = generateCssSelector(target);
    const r = target.getBoundingClientRect();
    const textSnippet = (target.textContent ?? '').trim().slice(0, 120);
    return {
      pick_id: crypto.randomUUID(),
      url: window.location.href,
      timestamp_ms: Date.now(),
      element: {
        selector,
        fingerprint,
        text_snippet: textSnippet,
        rect: { x: r.x, y: r.y, width: r.width, height: r.height },
      },
      comment: '',
    };
  }

  function onClick(e: MouseEvent): void {
    e.preventDefault();
    e.stopPropagation();
    if (!hoveredEl) {
      handleCancel();
      return;
    }
    handlePick(buildPick(hoveredEl));
  }

  /**
   * Wheel-forwarding via scroll-router service. Delegiert die "find scrollable
   * ancestor + scroll"-logik an :mod:`services/scroll-router/` — testbar, reusable
   * für zukünftige overlay-features die scroll-passthrough brauchen.
   *
   * rAF-loop trackt das hovered-element via getBoundingClientRect() — border
   * folgt dem element pixel-genau durch den scroll.
   */
  function onWheel(e: WheelEvent): void {
    forwardWheel(e);
  }

  $effect(() => {
    const unsubEsc = keyboard.subscribe('Escape', () => {
      backendState.inspector.cancel();
    });
    return () => {
      stopTracking();
      unsubEsc();
    };
  });
</script>

<!-- svelte-ignore a11y_click_events_have_key_events a11y_no_static_element_interactions -->
<div class="inspector-layer" onpointermove={onPointerMove} onclick={onClick} onwheel={onWheel}>
  {#if rect}
    <HighlightBorder {rect} element={hoveredEl} />
  {/if}
</div>

<style>
  .inspector-layer {
    position: fixed;
    inset: 0;
    z-index: 1;
    pointer-events: auto;
    cursor: crosshair;
    /* Kein background — wir wollen die Page sehen. */
  }
</style>
