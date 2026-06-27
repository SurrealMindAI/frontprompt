/**
 * panelCollapse — derived flag "the HUD panels should retract to minimal Laschen".
 *
 * Single source of truth for the panel-collapse concern, consumed by
 * ``Panel.svelte`` + ``PanelTab.svelte`` (``effectiveOpenWith``) and ``App.svelte``
 * (``gridTemplate*With``). Aggregates two distinct reasons to get the overlay out
 * of the way:
 *
 *   - ``pageTool.active`` — a full-viewport tool (Inspector / Region-Draw) owns the
 *     viewport and would collide with the HUD panels.
 *   - ``recorder.isActive`` — a recording is in progress; the overlay collapses to a
 *     minimal HUD + the floating recorder toolbar (BUG 3), exactly like
 *     quick-comment mode steps aside, and restores on stop.
 *
 * Why a separate module instead of extending ``pageTool``: ``pageTool`` means
 * specifically "a full-viewport tool is active" (pointer-capture semantics). The
 * recorder's floating toolbar is NOT full-viewport, so it must not be a pageTool —
 * but it SHOULD still collapse the panels. Keeping the two concerns separate but
 * OR-ing them here is the DRY way to feed every collapse-consumer one predicate.
 *
 * localState (ADR-018): pure UI-coordination aggregation, holds no own state.
 */
import { pageTool } from './page-tool.svelte';
import { recorder } from './recorder.svelte';

class PanelCollapse {
  /** True when the HUD panels should render as Laschen (collapsed). */
  active = $derived(pageTool.active || recorder.isActive);
}

export const panelCollapse = new PanelCollapse();
