/**
 * panelCollapse — derived flag "the HUD panels should retract to minimal Laschen".
 *
 * Single source of truth for the panel-collapse concern, consumed by
 * ``Panel.svelte`` + ``PanelTab.svelte`` (``effectiveOpenWith``) and ``App.svelte``
 * (``gridTemplate*With``). It tracks exactly ONE reason to get the overlay out of
 * the way:
 *
 *   - ``pageTool.active`` — a full-viewport tool (Inspector / Region-Draw) owns the
 *     viewport (pointer-capture) and would collide with the HUD panels.
 *
 * Recording is DELIBERATELY NOT a collapse reason. Recording is an ORTHOGONAL axis
 * (you can record AND pick/region at the same time), so the pick/region flow must
 * be IDENTICAL whether or not a recording is in progress. Folding
 * ``recorder.isActive`` in here used to retract the LEFT panel — which hosts the
 * pick/region tools — and ``Panel.svelte``'s ``.content--collapsed{pointer-events:none}``
 * then swallowed every click on those tools, making pick/region impossible during a
 * recording (the "pick/region dead during recording" bug). The recording-specific
 * chrome is the ``FloatingRecorderToolbar`` (gated on ``recorder.isActive``
 * separately in ``App.svelte``), not a HUD collapse.
 *
 * localState (ADR-018): pure UI-coordination aggregation, holds no own state.
 */
import { pageTool } from './page-tool.svelte';

class PanelCollapse {
  /** True when the HUD panels should render as Laschen (collapsed). */
  active = $derived(pageTool.active);
}

export const panelCollapse = new PanelCollapse();
