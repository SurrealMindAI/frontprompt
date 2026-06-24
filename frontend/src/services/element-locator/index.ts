/**
 * element-locator — Selector-Path + Fingerprint Service.
 *
 * Pure-TS, no Svelte runes. Called at pick-time vom InspectorLayer.
 * Phase-2 Adaptive-Relocate lebt python-side (siehe state.ts: ElementFingerprint
 * docstring). Hier nur Capture.
 */
export { generateCssSelector } from './selector-path';
export type { GenerateOptions } from './selector-path';
export { buildFingerprint } from './element-fingerprint';
export { isStableId } from './stable-id';
export { fingerprintHash } from './fingerprint-hash';
