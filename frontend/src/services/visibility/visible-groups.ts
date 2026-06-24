/**
 * visible-groups.ts — domain-scoped, owner-aware entity projection.
 *
 * Pure function: no Svelte runes, no globals, no side effects.
 * Generic over any entity that carries `origin_session` provenance.
 *
 * Consumed by the LeftPanel tabs (Task 5), where each tab binds a
 * per-kind `domainOf` callback (e.g. `pickDomain`, `regionDomain`,
 * `relationDomain`) via partial application.
 *
 * Spec: docs/specs/2026-06-01-domain-scoped-owner-aware-visibility-design.md
 * §Ownership & domain model, §Components
 */

// ---------------------------------------------------------------------------
// Public interfaces
// ---------------------------------------------------------------------------

/** A single entity with its ownership flag in the current session context. */
export interface VisibleItem<E> {
  entity: E;
  /** True when entity.origin_session === currentSessionId. */
  isOwned: boolean;
}

/** A group of entities that share the same effective hostname. */
export interface VisibleGroup<E> {
  /**
   * Effective hostname key:
   *   - currentHostname     — the active browser tab's hostname
   *   - any own-entity domain — alphabetically sorted after current
   *   - "(unknown)"         — own entities whose domainOf returned null
   *   - "(all)"             — only used when currentSessionId is null (degrade mode)
   */
  hostname: string;
  items: VisibleItem<E>[];
}

// ---------------------------------------------------------------------------
// Implementation
// ---------------------------------------------------------------------------

const UNKNOWN = '(unknown)';
const ALL = '(all)';

/**
 * Projects `entities` into domain-grouped, ownership-annotated buckets.
 *
 * Filtering rules (when currentSessionId is non-null):
 *   - Own entities (origin_session === currentSessionId):
 *       → always included; bucket key = domainOf(e) ?? "(unknown)"
 *   - Foreign entities (origin_session !== currentSessionId):
 *       → included only when domainOf(e) === currentHostname; absent otherwise
 *
 * Null degrade: when currentSessionId is null, returns a single "(all)"
 * group containing every entity with isOwned:true.
 *
 * Group ordering: currentHostname first · remaining own-domain groups
 * ascending localeCompare · "(unknown)" last.
 */
export function visibleGroups<E extends { origin_session?: string | null }>(
  entities: E[],
  ctx: {
    currentSessionId: string | null;
    currentHostname: string;
    domainOf: (e: E) => string | null;
  }
): VisibleGroup<E>[] {
  const { currentSessionId, currentHostname, domainOf } = ctx;

  // Null degrade: no session → show everything as owned
  if (currentSessionId === null) {
    return [
      {
        hostname: ALL,
        items: entities.map((entity) => ({ entity, isOwned: true })),
      },
    ];
  }

  // Bucket entities into a Map preserving insertion order within each bucket
  const buckets = new Map<string, VisibleItem<E>[]>();

  for (const entity of entities) {
    const isOwned = entity.origin_session === currentSessionId;
    const domain = domainOf(entity);

    let bucketKey: string | null = null;
    if (isOwned) {
      bucketKey = domain ?? UNKNOWN;
    } else if (domain === currentHostname) {
      bucketKey = currentHostname;
    }
    // foreign entity on a different domain → skip (bucketKey stays null)

    if (bucketKey === null) continue;

    let bucket = buckets.get(bucketKey);
    if (bucket === undefined) {
      bucket = [];
      buckets.set(bucketKey, bucket);
    }
    bucket.push({ entity, isOwned });
  }

  if (buckets.size === 0) return [];

  // Sort group keys: currentHostname first, "(unknown)" last, rest alphabetical
  const keys = Array.from(buckets.keys());
  keys.sort((a, b) => {
    if (a === currentHostname) return -1;
    if (b === currentHostname) return 1;
    if (a === UNKNOWN) return 1;
    if (b === UNKNOWN) return -1;
    return a.localeCompare(b);
  });

  return keys.map((hostname) => {
    // Invariant: hostname was derived from buckets.keys() — key is guaranteed present.
    const items = buckets.get(hostname);
    if (!items) throw new Error(`invariant: bucket key missing for hostname "${hostname}"`);
    return { hostname, items };
  });
}

/**
 * Returns the total number of items that `visibleGroups` would render for
 * the given entities and context — the number the LeftPanel tab header must
 * display.
 *
 * Implemented as a thin reduction over `visibleGroups` so that the
 * include/exclude rule lives in exactly one place (DRY — no rule duplication).
 */
export function visibleCount<E extends { origin_session?: string | null }>(
  entities: E[],
  ctx: {
    currentSessionId: string | null;
    currentHostname: string;
    domainOf: (e: E) => string | null;
  }
): number {
  return visibleGroups(entities, ctx).reduce((n, g) => n + g.items.length, 0);
}
