/**
 * RelationsRenderer interface — swap-point zwischen SVG (Phase 1) und ggf.
 * Canvas (Phase 3+). Phase 1 hat nur EINE Impl (`svg-renderer.svelte`); das
 * Interface existiert, um die Swap-Möglichkeit dokumentarisch festzuhalten +
 * eine konsistente DrawCommand-Konvention zu erzwingen.
 *
 * Convention: ein Renderer rendert per ``DrawCommand[]`` deklarativ. Mounten
 * + Unmounten passiert über Svelte-Lifecycle der host-Komponente (RelationsLayer).
 */
import type { DrawCommand } from '../path-planner';

export interface RelationsRenderer {
  /** Liste der zu rendernden Edges. */
  commands: readonly DrawCommand[];
  /** Highlight-target (z.B. hovered-relation in der Liste), null = keiner. */
  hoveredRelationId: string | null;
}
