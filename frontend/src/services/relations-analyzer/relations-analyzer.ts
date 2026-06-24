/**
 * RelationsAnalyzer — DOM-Post-Processing-Service.
 *
 * Eingabe: Liste von ``{ pickId, element }`` (typisch nach einem region-scan)
 *          + die bereits existierenden Relations (für dedup).
 * Ausgabe: Liste neuer ``Relation``-Objekte die aus DOM-Beziehungen abgeleitet
 *          wurden. Caller (region-draft.commit) feuert pro derived edge
 *          ``backendState.inspector.submitRelation``.
 *
 * Algo (Phase 1, klassisches LCA + Tree-Edit-Distance):
 *   - ``a.contains(b)``  → directed ``part_of``: b ist Teil von a (b → a)
 *   - sonst: Lowest Common Ancestor (LCA) ermitteln.
 *       totalDistance = depth(a, lca) + depth(b, lca)
 *       Falls totalDistance ≤ TREE_DISTANCE_THRESHOLD (default 4):
 *         → symmetric ``relates_to``: a ↔ b
 *
 *   Threshold 4 deckt ab: direct siblings (1+1=2), uncle-niece (1+2=3),
 *   cousins (2+2=4). Distance > 4 = zu weit auseinander, keine relation.
 *
 * Containment-check VOR LCA-check — wenn a contains b sind sie kein
 * "lateral pair" sondern ein parent-child-pair.
 *
 * Dedup: für jedes potential pair wird gegen die bestehenden Relations
 * geprüft. Same direction + kind → skip. Bei symmetric ``relates_to`` zählt
 * auch die umgekehrte richtung (a→b ist äquivalent zu b→a).
 *
 * Pure function, no Svelte-runes, no global state. Single-purpose Service —
 * eigener folder unter services/ damit die SRP klar bleibt.
 *
 * Note re scrapling: scrapling hat ``element_to_dict`` und ``relocate()`` für
 * element-finding, aber kein DOM-relation-discovery zwischen elements — das
 * ist orthogonal. LCA + tree-distance ist der klassische graph-theoretische
 * Standard dafür.
 */
import type { Relation, RelationKind } from '../../_generated/state';

export interface PickElementRef {
  pickId: string;
  element: Element;
}

/**
 * Tree-edit-distance threshold (Anzahl edges im DOM-tree zwischen 2 picks
 * über ihren LCA). Siblings = 2, uncle-niece = 3, cousins = 4. >4 = "zu weit
 * auseinander" → keine relation.
 */
const TREE_DISTANCE_THRESHOLD = 4;

/**
 * Lowest Common Ancestor zweier DOM-elements via ancestor-set-intersection.
 * Returns null wenn sie in disjunkten trees leben (shouldn't happen im selben
 * document, aber defensive).
 */
function findLCA(a: Element, b: Element): Element | null {
  const ancestors = new Set<Element>();
  for (let cur: Element | null = a; cur; cur = cur.parentElement) {
    ancestors.add(cur);
  }
  for (let cur: Element | null = b; cur; cur = cur.parentElement) {
    if (ancestors.has(cur)) return cur;
  }
  return null;
}

/**
 * Distanz (in edges) zwischen ``el`` und einem bekannten ancestor.
 * Direct child → 1, grandchild → 2, etc. Returns -1 wenn ancestor nicht
 * gefunden wird (defensive — sollte bei korrekter LCA-nutzung nie passieren).
 */
function depthTo(el: Element, ancestor: Element): number {
  let d = 0;
  for (let cur: Element | null = el; cur; cur = cur.parentElement) {
    if (cur === ancestor) return d;
    d += 1;
  }
  return -1;
}

interface MakeRelationArgs {
  source: string;
  target: string;
  kind: RelationKind;
}

function makeRelation({ source, target, kind }: MakeRelationArgs): Relation {
  return {
    relation_id: crypto.randomUUID(),
    source_id: source,
    source_kind: 'pick',
    target_id: target,
    target_kind: 'pick',
    kind,
    note: null,
    timestamp_ms: Date.now(),
  };
}

/**
 * Build dedup-key für (source, target, kind). Bei symmetric kinds (relates_to)
 * sortieren wir source+target damit a→b und b→a denselben key kriegen.
 */
function relationKey(source: string, target: string, kind: RelationKind): string {
  if (kind === 'relates_to') {
    const [lo, hi] = source < target ? [source, target] : [target, source];
    return `relates_to::${lo}::${hi}`;
  }
  return `${kind}::${source}::${target}`;
}

/**
 * Analyzes DOM-relations zwischen den picks und derives ``Relation``-objekte.
 *
 * @param picks       Pick-Element-Pairs (typisch aus scanRegion-output).
 * @param existing    Bereits existierende Relations (gegen die dedupplicat
 *                    wird). Default: leer = alles wird emittiert.
 * @returns           Neue Relations, ready-to-submit über
 *                    ``backendState.inspector.submitRelation``.
 */
export function analyzeDomRelations(
  picks: readonly PickElementRef[],
  existing: readonly Relation[] = []
): Relation[] {
  const existingKeys = new Set(existing.map((r) => relationKey(r.source_id, r.target_id, r.kind)));
  // Emit-Set verhindert dass wir innerhalb DIESES analyzer-runs Duplikate
  // produzieren (z.B. zwei parallel-siblings würden symmetric relates_to
  // sonst doppelt anbieten).
  const emittedKeys = new Set<string>();
  const out: Relation[] = [];

  function tryEmit(args: MakeRelationArgs): void {
    const key = relationKey(args.source, args.target, args.kind);
    if (existingKeys.has(key) || emittedKeys.has(key)) return;
    emittedKeys.add(key);
    out.push(makeRelation(args));
  }

  for (let i = 0; i < picks.length; i++) {
    for (let j = i + 1; j < picks.length; j++) {
      const a = picks[i]!;
      const b = picks[j]!;
      if (a.element === b.element) continue;

      // Containment? → part_of (child → parent).
      if (a.element.contains(b.element)) {
        tryEmit({ source: b.pickId, target: a.pickId, kind: 'part_of' });
        continue;
      }
      if (b.element.contains(a.element)) {
        tryEmit({ source: a.pickId, target: b.pickId, kind: 'part_of' });
        continue;
      }

      // Lateral: LCA + tree-distance. Findet auch nested-siblings
      // (h1 + a→p→div wo h1's parent das div ist) — distance h1↔a = 1+2 = 3.
      const lca = findLCA(a.element, b.element);
      if (lca && lca !== a.element && lca !== b.element) {
        const dist = depthTo(a.element, lca) + depthTo(b.element, lca);
        if (dist > 0 && dist <= TREE_DISTANCE_THRESHOLD) {
          tryEmit({ source: a.pickId, target: b.pickId, kind: 'relates_to' });
        }
      }
    }
  }

  return out;
}
