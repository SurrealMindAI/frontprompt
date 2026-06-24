/**
 * scroll-router — wheel-event-forwarding zu echten page-scrollern.
 *
 * Service-zweck: in viewport-fixed overlays (z.B. InspectorLayer) fangen
 * pointer-events:auto-elements alle wheel-events ab → page würde nicht
 * scrollen weil das overlay nicht scrollbar ist. Service findet den
 * scrollable ancestor des elements unter dem cursor + scrollt DEN.
 *
 * Handles moderne SPA-scroll-architekturen (Gmail/Google/Discord/Slack-style)
 * wo der "page-scroller" nicht ``<html>`` oder ``<body>`` ist sondern ein
 * custom container mit ``overflow:auto``.
 */
export { findScrollableAncestor, isScrollable } from './find-scrollable-ancestor';
export { forwardWheel, type ForwardWheelOptions } from './forward-wheel';
