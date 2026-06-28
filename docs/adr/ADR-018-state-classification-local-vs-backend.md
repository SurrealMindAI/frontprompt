# ADR-018 — State-Classification: localState vs backendState

> Part of the frontprompt [Architecture Decision Records](./index.md).

**Status**: accepted
**Date**: 2026-05-19
**Cross-References**: [ADR-002 Single-Writer Helland](./ADR-002-single-writer-helland.md), [ADR-015 Overlay in Main World](./ADR-015-overlay-in-page-main-world.md), [ADR-016 Bridge via expose_function](./ADR-016-expose-function-bridge.md), 2026-05-18 Architecture Reset

---

## Context

Das Overlay hält state mit zwei orthogonalen kategorien — fundamental anderen lifetime-/ownership-/persistenz-eigenschaften:

| Attribute | bridgeLog (diagnostic) | panelState (operational) |
|---|---|---|
| Lifetime | dies on page-unload | survives page-unload |
| Authoritative-source | overlay (UI lokal) | Python-process |
| Persistenz-Bedarf | none — verlust akzeptabel | yes — verlust bricht UX |
| Sync-Richtung | none (pure lokal) | python ⇄ overlay (hydrate + intent) |
| Frequency | hochfrequent (jeder wire-event) | low (user-actions) |

Cross-origin navigation (`example.com → google.com`) zerstört den JS-renderer-context komplett. Alle browser-native persistenz-mechanismen (localStorage, IndexedDB, cookies, ServiceWorker) sind origin-scoped — keine echte cross-origin-persistenz für injected scripts. Einzige stabile quelle über navigations hinweg: der **Python-CLI-process** (lebt über alle navigations).

Daraus: jedes state-item das nav überleben muss, MUSS authoritative im Python leben. Items die nur für die page-lifetime existieren können lokal bleiben.

Ohne disziplin: "manchmal lokal, manchmal über wire"-state-mutations werden race-conditions, debug-nightmares, drift-quellen zwischen UI und python-truth.

## Decision

**Zwei state-kategorien mit hard boundary auf file-/folder-ebene:**

### `localState` (TS singleton im overlay)
- Owned + mutated nur vom overlay
- Lebt in Svelte 5 `$state`-runes
- Stirbt mit page (cross-origin = verlust, akzeptiert)
- NIEMALS über die bridge geschickt
- Phase 1: `bridgeLog`
- Future: drag-in-progress, hover-selector, transient-tooltips

### `backendState` (TS singleton im overlay, Python authoritative)
- Authority: `StateManager` im Python (single-writer per ADR-002)
- Overlay hält **read-mirror** in Svelte 5 `$state`
- Hydration: bei jedem `OverlayReady` → Python sendet `StateSnapshot` → mirror hydrated
- Mutations: user-action im overlay → `bridge.send(*Requested)` outbound → Python's StateManager mutiert → Python broadcastet neue `StateSnapshot` → mirror reconciles
- Optimistic updates erlaubt (mirror updated lokal sofort, reconcile beim snapshot)
- Phase 1: `panelState` (open/sizes pro panel)
- Future: picks, annotations, user preferences, page-history

## File-Boundary (hard contract)

```
frontend/src/
  local-state/
    local-state.svelte.ts          # umbrella: localState singleton
    bridge-log.svelte.ts           # BridgeLog sub-store
  backend-state/
    backend-state.svelte.ts        # umbrella: backendState singleton
    panel-state.svelte.ts          # PanelState sub-store (mirror + intent-emission)
    sync.svelte.ts                 # bridge.on('state_snapshot') → backendState.hydrate

src/frontprompt/
  state/
    __init__.py
    state.py                       # Pydantic: PanelStateView, StateSnapshot
    manager.py                     # StateManager (single-writer, anyio-lock)
    persistence.py                 # stub Phase 1, disk-JSON Phase 2
```

**Cross-contamination = code-review rejection**:
- `local-state/*` darf NIE `bridge` importieren (oder eigene wire-messages senden)
- `backend-state/*` ist der EINZIGE wire-consumer für state-bezogene messages
- Python `state/*` darf KEINE bridge-internals importieren

## Wire-Protocol Wachstum

Pro neuer backend-state kategorie:
1. Neue field auf `StateSnapshot` (z.B. `picks: list[Pick]`)
2. N outbound `*Requested` messages für mutations
3. Python `StateManager` bekommt entsprechende mutation-methods
4. TS-backend-state-umbrella: neuer sub-store + intents + hydrate-branch

Wenn `*Requested`-kinds > ~20: switch zu generischem `Command`-pattern. Bis dahin: typed-per-kind besser für tooling.

## Consequences

### Positive
- Klarer mental-model — jede state-zeile gehört zu einer kategorie
- Cross-origin-nav-resilience für backend-state automatisch
- Single-writer-aggregate-pro-namespace (DDD-light)
- Testability: localState ohne python; backendState mit mocked bridge

### Negative
- Round-trip-latenz für backend-state mutations (mitigiert via optimistic)
- Wire-message-proliferation (acceptable bis ~20)
- Backend-dependency: overlay-only-mode verliert backend-state-features (Phase 1 hat das ohnehin nicht)

## Alternativen erwogen

### Alt 1 — Browser-Storage für persistente state (ruled out)
Origin-scoped → keine cross-origin-share. Fundamental nicht lösbar ohne extension (ADR-016 rejected).

### Alt 2 — Backend-Authoritative für ALLES (ruled out)
bridgeLog ist hochfrequent + diagnostic. Round-trip durch python = latenz + bandwidth + echo-chamber-fragen. Für nur-diagnostic-state local sauberer.

### Alt 3 — Hybrid mit interceptor-pattern (ruled out 2026-05-19)
bridgeLog würde überleben aber complexity ohne UX-benefit. Violates KISS für non-essential feature.

## Related

- [ADR-002 Single-Writer Helland](./ADR-002-single-writer-helland.md)
- [ADR-015](./ADR-015-overlay-in-page-main-world.md), [ADR-016](./ADR-016-expose-function-bridge.md)
- 2026-05-18 Architecture Reset
