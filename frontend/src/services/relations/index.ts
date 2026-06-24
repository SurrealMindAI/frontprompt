/**
 * Relations service-layer — public API barrel.
 *
 * Re-exportiert die fünf Services + animation-tokens. UI-components importieren
 * ausschließlich von hier (`from '../../services/relations'`) — interne
 * Service-files bleiben Implementation-detail.
 *
 * Plus: `RelationKind` als type re-exported — der echte SSoT kommt direkt aus
 * `_generated/state.ts` (pydantic-zod-codegen >=3e6bbf2a emittiert top-level
 * Literal-aliases). Wir re-exportieren nur für Import-bequemlichkeit aus dem
 * services-barrel.
 */
export type { RelationKind, RelationEndpointKind } from '../../_generated/state';

export { positionService, PositionService, detectLayoutDrift } from './position-service.svelte';
export type { RectCenter } from './position-service.svelte';

export { positionTracker, setupPositionTracker } from './position-tracker.svelte';

export { planPaths, quadraticBezier } from './path-planner';
export type { DrawCommand } from './path-planner';

export { lookupService } from './lookup-service.svelte';
export type { NodeRelations } from './lookup-service.svelte';

export { relationDraft } from './relation-draft.svelte';
export type { EndpointRef } from './relation-draft.svelte';

export { TOKEN, DEFAULTS, colorVarFor, applyTokenDefaults } from './animation-tokens';

export type { RelationsRenderer } from './renderer/renderer';
