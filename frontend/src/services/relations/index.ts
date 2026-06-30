/**
 * Relations service-layer — public API barrel.
 *
 * Re-exportiert die von UI-components konsumierten Services. UI-components
 * importieren ausschließlich von hier (`from '../../services/relations'`) —
 * interne Service-files (path-planner, animation-tokens, renderer) bleiben
 * Implementation-detail und werden direkt aus ihrem Modul importiert.
 *
 * Plus: `RelationKind` als type re-exported — der echte SSoT kommt direkt aus
 * `_generated/state.ts` (pydantic-zod-codegen >=3e6bbf2a emittiert top-level
 * Literal-aliases). Wir re-exportieren nur für Import-bequemlichkeit aus dem
 * services-barrel.
 */
export type { RelationKind, RelationEndpointKind } from '../../_generated/state';

export { positionService, detectLayoutDrift } from './position-service.svelte';

export { positionTracker, setupPositionTracker } from './position-tracker.svelte';

export { planPaths } from './path-planner';

export { lookupService } from './lookup-service.svelte';

export { relationDraft } from './relation-draft.svelte';
