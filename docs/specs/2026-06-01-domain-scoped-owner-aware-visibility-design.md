# Design: Domain-Scoped, Owner-Aware Pick/Region/Relation Visibility

- **Date**: 2026-06-01
- **Status**: Approved (brainstorming) — ready for implementation planning
- **Project**: frontprompt
- **Builds on**: [SQLite-persistence](2026-05-31-sqlite-persistence-design.md) (global store + `origin_session` provenance + steal-on-mutate)
- **Touches**: state classification (localState vs backendState) and ground-truth overlay rendering — see ARCHITECTURE.md
- **Schema impact**: none (current session id rides the wire envelope like `integrity_token`, not the `StateSnapshot` domain model)

## Problem

After SQLite persistence landed, every session loads **all** global picks/regions/relations and the LeftPanel renders them undifferentiated. There is no way to tell own-session work from other sessions', and entities from unrelated pages clutter the list. We want a page-relevant, ownership-aware view without a heavy UI.

## Goals

- **Own-session entities**: always visible, grouped by their hostname (you may have worked across several pages in one session).
- **Foreign entities** (other sessions): visible only under the **currently-open hostname's** group, rendered **slightly greyed but still selectable**. Foreign entities for other hostnames stay hidden until that hostname is open.
- **Overlay boxes**: drawn only for **owned** entities. Foreign entities are never drawn, even when their selector resolves on the current page.
- **Adopt on mutate**: a foreign entity becomes owned (and thus rendered) only through the existing steal-on-mutate path — i.e. when its content is edited. No new "adopt" control.
- Reactive: an ownership change (steal-on-mutate) flips an entity from greyed/non-rendered to normal/rendered automatically.

## Non-Goals (YAGNI)

- No owner **badge** or session-id label in the UI (explicitly rejected — greying is the only signal).
- No explicit "adopt / take over" button (mutate-to-adopt only).
- No registrable-domain (eTLD+1) matching — **exact hostname** only (no public-suffix-list dependency). `mail.google.com`, `www.google.com`, and `google.com` are distinct.
- No backend-side domain filtering — the backend stays the SSoT of all entities (see architecture).
- No live cross-process awareness beyond what persistence already provides.

## Architecture decision: frontend-derived view (Approach A)

The backend remains the single source of truth for **all** entities and gains exactly one new piece of wire data: the **current session id**. All domain/ownership filtering, grouping, greying, and the overlay render gate are computed **in the frontend**, because:

- The current hostname is inherently a frontend fact (`window.location.hostname`), live and re-evaluated whenever the overlay is re-injected on cross-origin navigation.
- Filtering is a *view projection*, not authoritative state — keeping it out of the StateManager preserves "load all globally" and the backend-authoritative / frontend-derived split.

Rejected alternatives: backend-filtered snapshots (would force the StateManager to track the live current domain, coupling it to a frontend concern) and a hybrid split (logic spread awkwardly across both sides).

## Ownership & domain model

For any entity, given the current session id and the current hostname:

- `isOwned = entity.origin_session === currentSessionId`
- `entityDomain`:
  - **Pick** → hostname of `pick.url`.
  - **Region** → hostname of its first resolvable member pick's `url` (regions have no `url`; `member_pick_ids` reference picks).
  - **Relation** → hostname of its source endpoint: a Pick directly, or — if the source is a Region — that region's derived domain.
- `onCurrentDomain = entityDomain === window.location.hostname` (exact string match, after a defined normalization: lowercase; no other normalization).

**Visibility rule** (per entity):

- `isOwned` → always visible, placed in the group for its own `entityDomain`.
- `!isOwned && onCurrentDomain` → visible (greyed) in the current hostname's group.
- `!isOwned && !onCurrentDomain` → hidden.
- Edge case: a foreign entity whose domain cannot be derived (e.g. a region with no resolvable members) → hidden (cannot be matched to the current hostname). An **owned** entity with no derivable domain → shown in a fallback "(unknown)" group so own work is never silently dropped.

**Overlay render gate**: draw a box only when `isOwned` (in addition to the existing ground-truth resolve and the visibility-toggle checks). Foreign entities never draw. Because `isOwned` is derived reactively from the snapshot's `origin_session`, a steal-on-mutate flips rendering on automatically.

## Components

**Backend (minimal):**
- Surface `current_session_id` on the wire **envelope** that carries the initial `getState()` seed (and snapshot broadcasts), exactly as `integrity_token` is surfaced today — sourced from `StateManager.session_id`. **No `StateSnapshot` schema change** (it is session metadata, not domain state).

**Frontend:**
- `backend-state/session-info` (small mirror): extracts `current_session_id` once at mount in `main.ts` (mirroring the `integrity_token` extraction) and exposes `currentSessionId`. Session-stable, set once.
- `services/visibility/` (pure, unit-testable):
  - `hostnameOf(url): string | null` — `new URL(url).hostname` lowercased, `null` on parse failure.
  - `entityDomain(entity, picksById): string | null` — the Pick/Region/Relation derivation above.
  - `visibleGroups(entities, { currentSessionId, currentHostname, picksById }): Group[]` — returns `{ hostname, items: { entity, isOwned }[] }[]` applying the visibility rule, with own entities under their hostnames and foreign under the current hostname only. Defines group ordering (current hostname first, then own-domain groups alphabetically; "(unknown)" last).
- `components/left-panel/tabs/{Picks,Regions,Relations}Tab.svelte`: consume `visibleGroups`, render a hostname header per group and rows beneath; rows with `isOwned === false` get a muted/greyed class (reduced opacity) but keep their existing click/select behaviour unchanged.
- Overlay render path (the inspector/relations layers and/or `position-service`): add the `isOwned` gate before drawing each pick/region/relation box.

## Data flow

1. **Mount**: `main.ts` extracts `current_session_id` from the seed envelope → `sessionInfo.currentSessionId`. `backendState.inspector` already mirrors all entities (unchanged).
2. **Render list**: each tab calls `visibleGroups(backendState.inspector.<kind>, { currentSessionId, currentHostname: window.location.hostname, picksById })` and renders grouped rows; foreign rows greyed.
3. **Render overlay**: the layers draw a box only when `isOwned` (plus existing ground-truth + toggle checks).
4. **Adopt**: editing a foreign entity's content triggers the backend steal-on-mutate → new snapshot carries the entity with `origin_session === currentSessionId` → `isOwned` flips true → the row de-greys and the overlay box appears, all reactively.
5. **Navigate** (cross-origin): the overlay re-injects; `window.location.hostname` is the new host → the derived groups recompute → foreign content swaps to the new hostname's foreign set; own groups persist.

## Error handling / edge cases

- Unparseable `pick.url` → `hostnameOf` returns `null` → entity has no derivable domain (handled by the visibility edge-case rules above).
- Region with zero resolvable members → no domain → foreign hidden / owned shown under "(unknown)".
- `current_session_id` missing from the envelope (older backend / cold boot) → `currentSessionId` is `null`. Treating everything as foreign would over-hide the list **and** blank the overlay (the `isOwned` gate would be false for all). Therefore a `null` `currentSessionId` degrades **both** surfaces to pre-feature behaviour: the list shows all entities ungrouped/un-greyed, and the overlay render gate falls back to drawing every resolvable entity (as today). The degradation is a single guard checked by both the derived view and the overlay gate.

## Testing strategy (TDD)

- `hostnameOf`: valid http/https urls, ports, paths/queries (host only), `data:`/invalid → `null`.
- `entityDomain`: pick (direct), region (via member), relation (pick source, region source), missing member/url → `null`.
- `visibleGroups`: own-across-multiple-domains all present and grouped; foreign only under current hostname; foreign other-hostname hidden; greyed flag (`isOwned`) correct; "(unknown)" fallback for own no-domain; ordering (current hostname first); `currentSessionId === null` degrades to show-all.
- Overlay gate: owned draws; foreign does not draw even when selector resolves; after a simulated steal (origin_session flips to current) the entity draws — verify reactively.
- Backend envelope: `current_session_id` is present in the getState() seed and equals `StateManager.session_id`; frontend extracts it once.
- Tab components (vitest): group headers render; foreign rows carry the muted class and remain clickable.

## Cross-refs

- [SQLite-persistence design](2026-05-31-sqlite-persistence-design.md) — the `origin_session` field + steal-on-mutate this view consumes.
- State classification — backend-authoritative all-entities, frontend-derived view; see ARCHITECTURE.md.
- Ground-truth overlay — the existing render gate the `isOwned` check augments; see ARCHITECTURE.md.
- The `integrity_token` envelope pattern in `frontend/src/main.ts` + `frontend/src/bridge/bridge.svelte.ts` — the template for surfacing `current_session_id`.
