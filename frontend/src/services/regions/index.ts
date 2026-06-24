/**
 * Regions service-layer — public API barrel.
 *
 * Schema 0.4.0: Region als first-class node-typ neben Pick. Drei Bausteine:
 *   - region-scanner: DOM-bbox-intersection scan + Pick-building
 *   - region-draft: localState für drag-to-region UX
 *   - (Renderer/Layer kommen aus components/inspector/DrawRegionLayer.svelte)
 */
export { scanRegion, buildPickFromElement } from './region-scanner';
export type { ScannedPick, ViewportRect } from './region-scanner';

export { regionDraft } from './region-draft.svelte';
