# Design: SQLite-Persistence für frontprompt

- **Date**: 2026-05-31
- **Status**: Approved (brainstorming) — ready for implementation planning
- **Project**: frontprompt
- **Touches**: state classification (localState vs backendState), single-writer discipline, daemon-singleton (deferred), and ground-truth overlay rendering — see ARCHITECTURE.md
- **Schema impact**: additive bump **0.6.0 → 0.7.0** (`origin_session` on Pick/Region/Relation)

## Problem

`InMemoryPersistence` is a no-op stub: all state dies with the process. Panel state and — more importantly — the user's inspector annotations (picks, regions, relations) do not survive a restart. frontprompt is not daily-driver useful until this lands. Replace the stub with a SQLite-backed persistence layer that durably stores panel state and inspector state, globally, with per-entity provenance.

## Goals

- Durable, cross-restart persistence of **panel state and inspector state** (picks/regions/relations).
- Per-entity provenance via an `origin_session` field, with **steal-on-mutate** (last-writer-owns) ownership.
- Resilient to the still-moving 0.x Pydantic schema — no migration treadmill.
- **Graceful degradation**: a persistence failure never breaks the overlay.

## Non-Goals (YAGNI)

- **Live cross-process state sync** — the daemon-singleton model stays deferred. Two simultaneous `frontprompt show` processes do not see each other's writes live.
- **A migration framework** — only a forward-looking schema-version seam (`schema_meta`).
- **The breaking unified single/group Pick schema** (the existing deferred "Pick-Schema-Evolution v0.7.0" backlog item) — it is renumbered to **0.8.0**, because this design claims 0.7.0 for the *additive* `origin_session` field.
- Any Two-BC / HTTP / WebSocket changes.

## Ownership model

Picks, regions, and relations are a **single global collection** — not partitioned per session. Each carries an `origin_session` field identifying the session that last touched it. Ownership is **steal-on-mutate**: any session that mutates an entity becomes its owner by stamping its own `session_id` onto that entity. There is no liveness check and no orphan-adoption pass — owner simply equals whoever last wrote.

On startup a session loads **all** entities globally. The ground-truth renderer already returns `null` for any pick/region whose selector does not resolve on the current page, so loading the full global set is safe — non-matching entities simply do not render (no ghost boxes), while the LeftPanel list still shows them (consistent with the existing cross-origin survival behaviour).

## SSoT: session identity

The **single source of truth for session identity is `session_lifecycle` / `SessionMetadata.session_id`** in `ipc/session.py`. There is exactly one producer of session ids. `StateManager` is a pure **consumer**: it receives `session_id` as an injected dependency and never fabricates one. This is the load-bearing constraint of the design — no second session-id generator anywhere.

Consequence (the one real wiring task): `frontprompt show` / `ShowSession` must run within `session_lifecycle` (the same path the MCP daemon already uses) so that it has an authoritative `session_id` to inject into `StateManager`. If `frontprompt show` currently establishes no session at all, that gap is closed by routing it through `session_lifecycle` — never by generating a parallel id inside the persistence or state layer.

## Architecture & components

The current single `state/persistence.py` is replaced by a small, focused package `state/persistence/`:

| Module | Responsibility |
|--------|----------------|
| `protocol.py` | The broadened `StatePersistence` Protocol (interface only) |
| `in_memory.py` | `InMemoryPersistence` — no-op default + test double (unchanged behaviour) |
| `sqlite.py` | `SqlitePersistence(db_path)` — the new durable implementation |
| `paths.py` | `state_db_path()` — resolves the DB location, env-overridable for tests |

The DB lives at `$XDG_STATE_HOME/frontprompt/state.db`, falling back to `~/.local/state/frontprompt/state.db`. The path resolver honours an environment override so tests target a `tmp_path` database.

## SQLite schema (the data contract)

WAL journal mode; entities stored as JSON payloads with only identity / owner / query columns promoted to real columns:

```sql
PRAGMA journal_mode = WAL;

CREATE TABLE IF NOT EXISTS panel_state (
    id           INTEGER PRIMARY KEY CHECK (id = 0),
    payload_json TEXT NOT NULL,
    updated_at   TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS picks (
    pick_id        TEXT PRIMARY KEY,
    origin_session TEXT,
    url            TEXT,
    payload_json   TEXT NOT NULL,
    updated_at     TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS regions (
    region_id      TEXT PRIMARY KEY,
    origin_session TEXT,
    payload_json   TEXT NOT NULL,
    updated_at     TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS relations (
    relation_id    TEXT PRIMARY KEY,
    origin_session TEXT,
    payload_json   TEXT NOT NULL,
    updated_at     TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS schema_meta (
    key   TEXT PRIMARY KEY,
    value TEXT NOT NULL
);  -- seeded with ('db_schema_version', '1') as a forward migration seam
```

The full entity is always `model_dump_json()` of the Pydantic model (the SSoT). Promoted columns (`origin_session`, `url`) are derived from the model on write — never a second source of truth. Because the entity body is opaque JSON, an additive Pydantic schema change needs no `ALTER TABLE`.

## Persistence Protocol (broadened)

The Protocol keeps the existing panel methods and adds a coarse, write-through inspector pair — mirroring the panel pattern rather than introducing eight granular per-entity methods (KISS):

- `load_panel_state() -> PanelStateView | None` — unchanged.
- `save_panel_state(panel_state) -> None` — unchanged.
- **new** `load_inspector_state() -> InspectorState | None` — rebuild the full picks/regions/relations collection from the DB; returns `None` to signal "empty / fall back to a fresh `InspectorState`". Only the durable entity collections are reconstructed; the ephemeral selection fields (`active_pick_id`, `active_region_id`, and the inspector-mode `active` flag) reset to their defaults on load — they are per-session UI state, never restored across restarts (consistent with the state-classification boundary and the no-ephemeral-state-in-backend rule).
- **new** `save_inspector_state(inspector_state) -> None` — one transaction that upserts every present pick/region/relation and deletes any row whose id is no longer in the collection.

`InMemoryPersistence` implements the two new methods as no-ops, preserving its semantics and the existing test surface.

The coarse `save_inspector_state` re-writes the touched-and-present set on every mutation. At realistic scale (tens to low-hundreds of entities) the per-mutation write cost is negligible, and the interface stays as simple as the panel one. Granular per-entity upsert/delete methods are an explicit future optimisation if write amplification ever shows up — not built now.

## Data flow

1. **Init** — `StateManager(session_id, persistence)` calls `load_panel_state()` (existing) and the new `load_inspector_state()`; the loaded inspector collection seeds `_inspector_state` (or a fresh empty one if `None`).
2. **Mutate** — a wire request hits a `StateManager` mutation method, which stamps `origin_session = self._session_id` on the touched entity (steal-on-mutate), then `_post_mutate_locked` calls `save_panel_state` **and** `save_inspector_state` inside the existing `anyio.Lock`, then the snapshot is broadcast. The single-writer discipline already serialises this; the synchronous SQLite write is sub-millisecond and runs under that lock (no `to_thread` needed).
3. **Restart** — a new process with a new authoritative `session_id` loads all global entities (owned by whichever session last touched each); the next mutation steals ownership of whatever it touches.

## Concurrency boundary

WAL mode permits concurrent readers and a serialised writer across processes, so the DB file never corrupts under parallel access. There is **no live cross-process sync**: each process loads on start and writes through; the last writer to disk wins. Live multi-session coordination is daemon-singleton territory and stays deferred.

## Error handling — graceful degradation

A persistence problem must never break the overlay:

- **DB open/create failure** → log a warning and fall back to `InMemoryPersistence` for the session; the overlay runs, just without durability this run.
- **Corrupt `payload_json` on load** → skip that row with a warning; one bad row does not abort the whole load.
- **Write failure mid-session** → log a warning and continue; a failed save never propagates into a UX crash.

## Testing strategy (TDD — Red before Green)

- Round-trip per type: `save_*` → `load_*` for panel state and each entity kind against a `tmp_path` DB.
- Steal-on-mutate: mutate through `StateManager` as session `A`, assert persisted `origin_session == "A"`; reload as session `B`, mutate, assert `origin_session == "B"`.
- Delete-missing: add three picks, delete one, assert the DB holds exactly two.
- Corrupt-row resilience: inject malformed JSON, assert the load skips it and logs.
- DB-error degradation: point at an unwritable path, assert fallback to in-memory and a functioning overlay.
- Schema-evolution tolerance: persist a payload with an extra / missing optional field, assert load tolerates it (Pydantic).
- End-to-end through `StateManager`: `add_pick` → construct a new `StateManager` on the same DB → its `snapshot()` contains the pick.
- Regression guard: `InMemoryPersistence` stays a no-op; existing panel-persistence tests remain green.

## Open wiring point (resolved in the plan)

`frontprompt show` / `ShowSession` ↔ `session_lifecycle`: ensure the standalone show path obtains its `session_id` from the SSoT before constructing `StateManager`. Scope and exact call site to be pinned down during planning.

## Cross-refs

- State classification — the localState-vs-backendState boundary this extends; see ARCHITECTURE.md.
- Single-writer discipline — the lock under which write-through runs; see ARCHITECTURE.md.
- Daemon-singleton (deferred) — the boundary of the no-live-sync decision; see ARCHITECTURE.md.
- Ground-truth overlay — why loading all global picks is safe; see ARCHITECTURE.md.
- Schema-history — `origin_session` is the additive 0.7.0 entry.
