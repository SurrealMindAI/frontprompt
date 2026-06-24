/**
 * LookupService — derives "Relations für Node X" + "Node mit ID Y" aus zentralen Listen.
 *
 * Wichtig (Design-Entscheidung): Relations leben NICHT
 * am Pick/Region. Beide sind clean Aggregate. Wenn UI "outgoing/incoming relations
 * für diesen Node" anzeigen will, fragt sie diesen Service — der filtert die
 * zentrale Liste. Kein embedded-field-duplication, kein Sync-Probleme.
 *
 * Schema 0.4.0: Relations sind heterogeneous — source/target können Pick ODER
 * Region sein, discriminiert via ``source_kind`` / ``target_kind``.
 *
 * Stateless, pure functions. Skaliert linear in der Relations-Anzahl — bei
 * großen Mengen (>1000) wäre eine Map-by-Node-ID effizienter, Phase-2-Detail.
 */
import type { Pick, Region, Relation, RelationEndpointKind } from '../../_generated/state';

export interface NodeRelations {
  outgoing: Relation[];
  incoming: Relation[];
}

class LookupService {
  /**
   * Returns ``{outgoing, incoming}`` für einen node (pick oder region).
   * Edges in beiden Richtungen werden separat gelistet.
   */
  relationsFor(
    nodeId: string,
    nodeKind: RelationEndpointKind,
    allRelations: readonly Relation[]
  ): NodeRelations {
    const outgoing: Relation[] = [];
    const incoming: Relation[] = [];
    for (const r of allRelations) {
      if (r.source_id === nodeId && r.source_kind === nodeKind) outgoing.push(r);
      if (r.target_id === nodeId && r.target_kind === nodeKind) incoming.push(r);
    }
    return { outgoing, incoming };
  }

  /** Convenience: pick by id, null wenn unbekannt. */
  pickById(pickId: string, allPicks: readonly Pick[]): Pick | null {
    return allPicks.find((p) => p.pick_id === pickId) ?? null;
  }

  /** Convenience: region by id, null wenn unbekannt. */
  regionById(regionId: string, allRegions: readonly Region[]): Region | null {
    return allRegions.find((r) => r.region_id === regionId) ?? null;
  }

  /** Count "relations involving this node" (für list-badges in tabs). */
  countFor(
    nodeId: string,
    nodeKind: RelationEndpointKind,
    allRelations: readonly Relation[]
  ): number {
    let n = 0;
    for (const r of allRelations) {
      if (
        (r.source_id === nodeId && r.source_kind === nodeKind) ||
        (r.target_id === nodeId && r.target_kind === nodeKind)
      ) {
        n += 1;
      }
    }
    return n;
  }
}

export const lookupService = new LookupService();
