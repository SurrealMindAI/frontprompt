/**
 * PathPlanner — pure function (kind, source-pos, target-pos) → DrawCommand.
 *
 * Phase 1: nur binary directed edges. Pfad ist eine quadratische Bezier-Kurve
 * mit "Sag" — kontrollpunkt ist der Mittelpunkt verschoben senkrecht zur
 * Verbindungslinie. So überlagern sich mehrere edges zwischen gleichen rects
 * nicht und Self-flows wären unterscheidbar (Phase 1 verbietet self-loops eh).
 *
 * Output ist `DrawCommand[]` — Renderer-agnostic. SVG-renderer schreibt
 * `pathD` direkt in `<path d="...">`; ein theoretischer Canvas-renderer würde
 * dasselbe d-Format mit `Path2D(d)` einlesen.
 */
import type { Pick, Region, Relation } from '../../_generated/state';
import type { PositionService } from './position-service.svelte';

export interface DrawCommand {
  relationId: string;
  kind: Relation['kind'];
  isDirected: boolean;
  source: { cx: number; cy: number };
  target: { cx: number; cy: number };
  /**
   * Midpoint der quadratic-bezier-curve (t=0.5). Wird vom svg-renderer als
   * Anker für das kind+note-label benutzt — exakt auf der Kurve sitzend.
   */
  midpoint: { cx: number; cy: number };
  /** SVG-path-data attribute value (quadratic bezier ``M x y Q cx cy x y``). */
  pathD: string;
  note: string | null;
  /**
   * Provenance of the relation (Schema 0.7.0). Carried through so the overlay
   * render gate (`isOwnedFor`) can decide per-edge ownership without re-looking
   * up the Relation. `null`/absent when the relation pre-dates origin_session.
   */
  origin_session: string | null;
}

/** Symmetric kinds rendern ohne arrowhead. */
const DIRECTED_KINDS: ReadonlySet<Relation['kind']> = new Set(['triggers', 'part_of']);

/**
 * Plan paths für alle relations gegen die aktuelle pick-/region-positions.
 *
 * Relations, deren source ODER target nicht (mehr) in den listen sind, werden
 * silently skipped (degraded display — sollte via cascade-delete schon
 * verhindert sein, aber wir sind hier defensiv).
 *
 * Schema 0.4.0: Endpoints sind heterogeneous (pick ODER region), discriminiert
 * via ``source_kind`` / ``target_kind``.
 */
export function planPaths(
  relations: readonly Relation[],
  picks: readonly Pick[],
  regions: readonly Region[],
  positions: PositionService
): DrawCommand[] {
  const out: DrawCommand[] = [];
  for (const rel of relations) {
    const src = positions.centerForNode(rel.source_id, rel.source_kind, picks, regions);
    const tgt = positions.centerForNode(rel.target_id, rel.target_kind, picks, regions);
    if (src === null || tgt === null) continue;
    const { pathD, midpoint } = bezierWithMidpoint(src, tgt);
    out.push({
      relationId: rel.relation_id,
      kind: rel.kind,
      isDirected: DIRECTED_KINDS.has(rel.kind),
      source: src,
      target: tgt,
      midpoint,
      pathD,
      note: rel.note ?? null,
      origin_session: rel.origin_session ?? null,
    });
  }
  return out;
}

/**
 * Quadratic Bezier zwischen zwei punkten, mit kontrollpunkt der senkrecht
 * zur Verbindungslinie um ``sagFactor * distance`` versetzt ist. Sag macht
 * die Linie organisch, vermeidet straight-line-overlap bei parallelen edges.
 *
 * Returns both the SVG-path-string AND the curve-midpoint (t=0.5), weil der
 * Renderer beide braucht: pathD für <path>, midpoint für das label.
 */
const SAG_FACTOR = 0.15;

export function bezierWithMidpoint(
  src: { cx: number; cy: number },
  tgt: { cx: number; cy: number }
): { pathD: string; midpoint: { cx: number; cy: number } } {
  const midX = (src.cx + tgt.cx) / 2;
  const midY = (src.cy + tgt.cy) / 2;
  const dx = tgt.cx - src.cx;
  const dy = tgt.cy - src.cy;
  const dist = Math.hypot(dx, dy);
  if (dist === 0) {
    // degenerate — both ends in same spot. cascade-delete sollte das verhindern,
    // aber be safe: straight line + midpoint = src=tgt.
    return {
      pathD: `M ${src.cx} ${src.cy} L ${tgt.cx} ${tgt.cy}`,
      midpoint: { cx: src.cx, cy: src.cy },
    };
  }
  // Senkrecht-vector (rotated 90°, dann normiert + skaliert)
  const sag = dist * SAG_FACTOR;
  const nx = -dy / dist;
  const ny = dx / dist;
  const ctrlX = midX + nx * sag;
  const ctrlY = midY + ny * sag;
  // Quadratic Bezier evaluated at t=0.5: B(0.5) = 0.25*P0 + 0.5*P1 + 0.25*P2
  const t = 0.5;
  const mt = 1 - t;
  const cx = mt * mt * src.cx + 2 * mt * t * ctrlX + t * t * tgt.cx;
  const cy = mt * mt * src.cy + 2 * mt * t * ctrlY + t * t * tgt.cy;
  return {
    pathD: `M ${src.cx} ${src.cy} Q ${ctrlX} ${ctrlY} ${tgt.cx} ${tgt.cy}`,
    midpoint: { cx, cy },
  };
}

/** Kept as backward-compat alias — used by the path-planner tests. */
export function quadraticBezier(
  src: { cx: number; cy: number },
  tgt: { cx: number; cy: number }
): string {
  return bezierWithMidpoint(src, tgt).pathD;
}
