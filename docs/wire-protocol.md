# Wire Protocol — Backend ↔ Overlay Bridge

> **SSoT**: [`src/frontprompt/bridge/messages.py`](../src/frontprompt/bridge/messages.py)
>
> Diese Datei ist der **kanonische Überblick** über alle Wire-Messages. Bei Drift gegen `messages.py` ist `messages.py` autoritativ — diese Doc nachziehen.

## Architektur-Anker

- Typed messages via Playwright's `expose_function` + `page.evaluate`
- backendState category: jede mutation ist eine `*Requested` intent vom Overlay
- Codegen: `python -m frontprompt.build` regeneriert `frontend/src/_generated/{state,schemas}.ts` aus den Pydantic SSoTs

## Schema-Version

| Version | Date | Diff |
|---|---|---|
| 0.1.0 | 2026-05-18 | Initial Phase-1 Durchstich (panel-state only) |
| **0.2.0** | **2026-05-19** | **+ Inspector / Pick-Flow** (current) |

Schema-version-Bump notwendig bei **breaking change** (field rename / remove / kind-rename). Forward-compatible adds (neue optional fields) ohne Bump.

## Discriminator-Pattern

Jede Envelope:

```python
class XyzRequested(BaseModel):
    kind: Literal["xyz_requested"] = "xyz_requested"
    schema_version: str = SCHEMA_VERSION
    # ... typed payload fields
```

Routing: Pydantic's `Annotated[Union[...], Field(discriminator="kind")]` macht O(1)-dispatch + Validierung. Ungültiges `kind` → `ValidationError`, geloggt in `BridgeManager._on_overlay_send` als `bridge.outbound.validation_failed`.

## Outbound (Overlay → Python)

### Lifecycle

| Class | `kind` | Payload | Server-Wirkung |
|---|---|---|---|
| `OverlayReady` | `overlay_ready` | `bundle_build_session` | Markiert overlay-mount; triggert initial-snapshot-broadcast |
| `HeartbeatAck` | `heartbeat_ack` | `heartbeat_seq`, `client_recv_time_ms` | Schließt Heartbeat round-trip (Latenz-messung) |

### Panel-Mutations

| Class | `kind` | Payload | Server-Wirkung |
|---|---|---|---|
| `PanelToggleRequested` | `panel_toggle_requested` | `panel_id` | `StateManager.toggle_panel` flippt `open` |
| `PanelResizeRequested` | `panel_resize_requested` | `panel_id`, `new_size` | `StateManager.resize_panel` (clamp + set) |
| `HideAllPanelsRequested` | `hide_all_panels_requested` | `target_open` | `StateManager.set_all_panels_open` bulk |

### Inspector-Lifecycle (Phase 1)

| Class | `kind` | Payload | Server-Wirkung |
|---|---|---|---|
| `InspectorActivateRequested` | `inspector_activate_requested` | — | `inspector.active = True`; panels retracten via derived |
| `InspectorCanceledRequested` | `inspector_canceled_requested` | — | `inspector.active = False` (kein Pick) |
| `InspectorPickMadeRequested` | `inspector_pick_made_requested` | `pick: Pick` (volles Domain-Objekt) | **atomar**: append + select + deactivate |

### Pick-Mutations (Phase 1)

| Class | `kind` | Payload | Server-Wirkung |
|---|---|---|---|
| `PickSelectedRequested` | `pick_selected_requested` | `pick_id` | `active_pick_id = pick_id` |
| `PickCommentUpdatedRequested` | `pick_comment_updated_requested` | `pick_id`, `comment` | Patch `Pick.comment` in-place |
| `PickDeletedRequested` | `pick_deleted_requested` | `pick_id` | Entfernen aus Liste; `active_pick_id → None` wenn aktiv |

## Inbound (Python → Overlay)

| Class | `kind` | Payload | Trigger |
|---|---|---|---|
| `Heartbeat` | `heartbeat` | `seq`, `server_send_time_ns` | Periodisch (5s) vom CLI-Heartbeat-task |
| `StateSnapshotMessage` | `state_snapshot` | `snapshot: StateSnapshot` | Nach `OverlayReady` + nach jeder authoritative mutation |

## Atomicity-Garantien

`StateManager` Methoden mutieren unter `anyio.Lock` (single-writer). Eine wire-message → eine method → ein snapshot-broadcast.

**Wichtig**: `InspectorPickMadeRequested` mutiert **drei** Felder atomar (`picks.append` + `active_pick_id` + `inspector.active = False`). Frontend bekommt EINEN snapshot mit allen drei Änderungen — kein Zwischenzustand sichtbar.

## Idempotency

Phase 1: keine wire-level idempotency-keys. Die zwei kritischen Operationen sind idempotent durch Konstruktion:

- `InspectorPickMadeRequested`: re-send mit identischer `pick_id` ersetzt den existierenden Pick (last-write-wins) — siehe `StateManager.add_pick` `existing_idx`-Branch.
- `PickSelectedRequested` / `PickCommentUpdatedRequested` / `PickDeletedRequested`: alle no-op bei unbekannter `pick_id`, aber snapshot-broadcast feuert trotzdem (idempotente re-hydrate).

Phase 2+ kann echte idempotency-keys einführen (siehe `frontprompt.wire.mutations.IdempotencyKey` als Vorlage — dormant aus Channel-3-Plan).

## End-to-End Type-Safety

```text
   Python                                            TypeScript
   ──────                                            ──────────
   class PickCommentUpdatedRequested(BaseModel):       interface PickCommentUpdatedRequested
       kind: Literal["pick_comment_updated_requested"]    kind?: "pick_comment_updated_requested"
       pick_id: str                                       pick_id: string
       comment: str                                       comment: string
       │
       │  pydantic-zod-codegen
       └─────────────────────────────────────────────────►

   OutboundMessage = Annotated[                       OutboundMessage =
       PickCommentUpdatedRequested | ...,                | PickCommentUpdatedRequested | ...
       Field(discriminator="kind")
   ]

   bridge.on(PickCommentUpdatedRequested, _handler)   bridge.send({ kind: 'pick_comment_updated_requested',
                                                                    pick_id, comment })
   async def _handler(msg: PickCommentUpdatedRequested):    ◄── TS narrows union by literal 'kind'
       await state_manager.update_pick_comment(...)
```

Hinweis: pydantic-zod-codegen v0.x emittiert die Literal-defaults als `kind?:` (optional in TS). Das wird in `bridge.svelte.ts` mit `message.kind ?? 'unknown'` für log-emission abgefangen. Auf wire ist `kind` immer present (Pydantic default).

## Verifikations-Tests

- `tests/bridge/test_collection.py` — exhaustiveness-property-tests:
  - Jede `Literal[kind]`-Klasse ist in Outbound oder Inbound Union
  - Jede Union-Member ist in `__codegen_roots__` + `__all__`
  - Keine duplicate `kind`-literals innerhalb einer Richtung
  - Outbound + Inbound kinds kollidieren nicht
  - Jede Envelope trägt `schema_version`

- `tests/bridge/test_messages.py` — pro-envelope tests:
  - Discriminated-union routing (jeder `kind` → richtige Klasse)
  - Roundtrip (JSON dump → validate)
  - Validation-failures (missing required, unknown kind)

## Lebenszyklus einer neuen Envelope

Wenn du eine neue `XyzRequested` hinzufügst:

1. **Klasse definieren** in `messages.py` (richtige Section: Lifecycle / Panel / Inspector / Pick)
2. **Docstring** nach Konvention (User-Trigger + Server-Wirkung + Optimistic-UI / Atomicity-Hinweise wo relevant)
3. **`Field(description=...)`** auf jedem nicht-trivialen Field
4. **`OutboundMessage` Union** erweitern
5. **`__codegen_roots__`** + **`__all__`** ergänzen (jeweils in die richtige Section)
6. **Handler in `cli.py`** registrieren (`bridge.on(XyzRequested, _on_xyz)`)
7. **`StateManager`** method hinzufügen mit `anyio.Lock` + `_post_mutate()`
8. **TS-Side**:
   - `bridge.svelte.ts` `OutboundMessage` Union erweitern (Import + Variante)
   - State-store method auf `backendState` für UI-Aufruf
   - UI-Komponente hooked die method via Event-Handler
9. **Tests**:
   - `tests/bridge/test_messages.py` — discriminator-routing + roundtrip + invalid-input
   - `tests/state/test_manager.py` — StateManager-method-tests
10. **Codegen regen** + **canonical build**:
    ```bash
    uv run python -m frontprompt.build
    ```
11. **Verifikation**: `uv run pytest tests/bridge/ tests/state/` + `cd frontend && bun run check && bun run test`

`tests/bridge/test_collection.py` schlägt fehl wenn 4 oder 5 vergessen wurden — fail-fast safety-net.
