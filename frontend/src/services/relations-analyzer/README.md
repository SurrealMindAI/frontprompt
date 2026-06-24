# services/relations-analyzer

DOM-Post-Processing-Service: nimmt eine Liste gescannter Pick-Element-Pairs (typisch nach `services/regions` region-scan) und derived `Relation`-objekte aus den DOM-Beziehungen.

| Function              | Signature                         | Beschreibung                                                                                                                                                    |
| --------------------- | --------------------------------- | --------------------------------------------------------------------------------------------------------------------------------------------------------------- |
| `analyzeDomRelations` | `(picks, existing?) → Relation[]` | Hauptentry. Pair-wise scan über alle `{pickId, element}`, leitet `part_of` (containment) oder `relates_to` (LCA+distance) ab. Dedup gegen `existing` Relations. |

## Algorithmus

Pair-wise über alle picks-pairs (`i × j` mit i<j):

1. **Containment-check**: `a.contains(b)` → directed `part_of` (b → a, "b ist Teil von a"). Analog für `b.contains(a)`.
2. **Lateral / LCA + Tree-Edit-Distance**: kein containment → Lowest Common Ancestor finden, tree-distance = depth(a, lca) + depth(b, lca).
   - `≤ TREE_DISTANCE_THRESHOLD` (default 4) → symmetric `relates_to`.
   - distance > 4 → keine relation (zu weit auseinander).
3. **Dedup**: vor jedem emit prüfen ob (kind, source, target) bereits in `existing` ist. Bei symmetric `relates_to` zählt auch reverse-direction (sorted key).

Threshold 4 deckt ab:

- direct siblings (1+1=2) ✓
- uncle-niece / aunt-nephew (1+2=3) ✓
- cousins (2+2=4) ✓
- > 4: cross-section relationships zu lateral — wird als unrelated betrachtet

## Beispiel (example.com)

```
DOM:
  <div>
    ├─ <h1>          parent: div
    ├─ <p>           parent: div
    └─ <p>
        └─ <a>       parent: p(inner)

Pair-wise analyse:
  (h1, p): direct siblings, dist=2     → relates_to  ✓
  (h1, a): LCA=div, dist=1+2=3        → relates_to  ✓
  (p, a):  p contains a, dist=0+1=1   → part_of (a → p) ✓ (containment trifft erst)

Vorher (nur direct-sibling-check):
  Nur (h1, p) → 1 relation.

Jetzt (LCA + threshold):
  3 relations.
```

## Warum nicht scrapling?

Scrapling hat `element_to_dict` + `relocate()` — fokussiert auf element-finding und fingerprint-equivalence-matching. **Kein** DOM-relation-discovery. Das ist ein orthogonales Problem; LCA + tree-distance ist der klassische graph-theoretische Standard.

## Konstanten

```ts
TREE_DISTANCE_THRESHOLD = 4;
```

Anhebung bewirkt mehr "verwandt"-relationen, Senkung restriktiver. 4 ist heuristisch zwischen "nur direkte Verwandte" (2) und "alles im selben section" (>6).

## Cross-refs

- `services/regions/region-draft.svelte.ts` — caller (region.commit → analyzeDomRelations → submitRelation)
- `services/relations/lookup-service.svelte.ts` — sibling-service für relation-queries gegen die zentrale state-list (nicht zu verwechseln)
