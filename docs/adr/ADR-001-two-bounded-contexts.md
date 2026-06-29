# ADR-001 — Two Bounded Contexts: Programmatic Executor & Interactive Surface

> Part of the frontprompt [Architecture Decision Records](./index.md).

**Status**: accepted with amendments (2026-05-18: §UI-Surface revoked, Two-BC-Axiom deferred)
**Date**: 2026-05-14
**Amendment-Date**: 2026-05-18
**Cross-References**: overview.md §3 Bounded Contexts, [ADR-002 Single-Writer Helland](./ADR-002-single-writer-helland.md), [ADR-005 Nursery-per-PageSession](./ADR-005-nursery-per-pagesession.md), single-writer-helland-explained (historische atlas-Recherche, nicht extrahiert), [ADR-014 Daemon-Singleton via Lockfile](./ADR-014-daemon-singleton-via-lockfile.md), [ADR-015 Overlay in Page Main World](./ADR-015-overlay-in-page-main-world.md), 2026-05-18 Architecture Reset

---

## Context

Der archivierte Patient `frontprompt-legacy` (v4.2.0) starb laut Krall-Hypothese-0 an einem **Category Error**: das Produkt wurde als "MCP-First browser-automation server with a Lit overlay for human-in-the-loop" spezifiziert. Dieser Satz schmuggelt zwei Produkte unter einem Banner:

1. **Ein programmatischer Browser-Executor** mit typed I/O, adressiert durch einen MCP-Client (Agent-Workflow).
2. **Eine interaktive Human-in-the-Loop-Annotation-Surface** mit dem Page-DOM als Schauplatz (Mensch-Workflow).

Diese zwei Produkte haben orthogonale Invarianten. Die Orthogonalität wurde im Patienten nie modelliert. Jede load-bearing Komplexität in v4.2.0 — MAIN↔ISOLATED↔SW↔Python-IPC, Codegen-Drift-Gate, Headless-WONTFIX, Cross-Origin-Overlay-Surrender, der count-vs-list-Bug der Page-scoped Recordings, der StartPage-HTTP-Injector — war downstream der Weigerung, die zwei als getrennte Contexts mit getrennten Lifecycles und getrennten Transports zu modellieren.

Der `OverlayState`-Pydantic-Aggregate-Singleton im Patient ist die "smoking gun": er wurde sowohl vom MCP-Tool-Call-Axis als auch vom Human-clicked-the-DOM-Axis durch denselben Write-Through-Cache mutiert. Das ist eine Write-Skew-Anomalie aus dem Helland-Lehrbuch — und der count!=list-Bug der Page-scoped Recordings war genau diese Anomalie, observed.

---

## Decision

Der Successor verpflichtet sich als **Axiom**, nicht als Refactoring-Ziel, auf zwei **Bounded Contexts**:

- **Programmatic Executor BC** umfasst alle Aggregate, die ein Agent typed durch das MCP-Surface fragt oder mutiert:
  - `PageSession` (Aggregate Root, BrowserContext-besitzend)
  - `InteractionFlow` (Aggregate Root, capture/replay)
  - `PageSessionProfile` (Value Object: Headers / Cookies / Proxy)

- **Interactive Surface BC** umfasst alle Aggregate, die ein Mensch durch das Annotation-UI mutiert:
  - `PointingSession` (Aggregate Root, Lifecycle: open → multiple Picks → closed)
  - `Pick` (Entity in PointingSession — offene Frage, siehe overview.md §10)
  - `Annotation` (Aggregate Root, Wire-Identitäts-Anker ist `Selector`)

Die beiden BCs haben **strukturell unterschiedliche Wire-Transports**:

- **Programmatic Executor BC** spricht **MCP** (stdio oder Streamable HTTP) — Agent-Pull, Server-Push für Resource-Updates.
- **Interactive Surface BC** spricht **WS Push-only** (Server → Browser-Tab) plus **HTTP POST** (Tab → Server, mit Idempotency-Key-Header).

Die beiden BCs leben **in einem Python-Prozess** (ein Daemon, persistent). Cross-BC-Coordination passiert ausschließlich über **einen** typed-Message-Mechanismus: die blockierende **IntentRequest-Queue** (H-1, anyio Memory-Stream mit `max_buffer_size`). Kein cross-aggregate Lock, kein doppelter Aggregat-Eigentum, kein geteilter Singleton-State.

---

## Consequences

**Strukturelle**:

- Jeder BC hat sein eigenes Aggregate-Set, seinen eigenen Single-Writer pro Aggregate (siehe [ADR-002](./ADR-002-single-writer-helland.md)), seinen eigenen Persistence-Adapter (SQLite-Tabellen mit BC-Prefix), seinen eigenen Audit-Log-Namespace.

- Die `IntentRequest`-Queue ist die **einzige** legitime Kommunikations-Verbindung. Sie hat ein typed Message-Set: `RequestPick(page_session_id) → PickResult | PickTimeout`, `NotifyPageNavigated(page_session_id, url)`, `NotifyAnnotationAdded(annotation_id, ...)`. Jeder Message hat einen typed Response-Slot oder ist explizit fire-and-forget.

- Tests können beide BCs **getrennt** als-ob unit-testen: Programmatic-Executor-Tests stubben die IntentQueue mit erwarteten Responses; Interactive-Surface-Tests stubben die Queue mit erwarteten Requests.

**Wire-Boundary**:

- Es gibt keinen Wire-Channel, der beide BCs spricht. Ein Agent kann nicht das Annotation-UI direkt manipulieren; ein Annotation-UI kann nicht direkt MCP-Tool-Calls absetzen. Beide gehen durch den Daemon, der die Queue moderiert.

- Im Frontend bedeutet das: das Svelte-5-UI hat **keinen Code-Pfad** für Programmatic-Executor-Aggregate. Es kennt `PointingSession` und `Annotation`, nicht `InteractionFlow`.

**Bezug zum Failure-Mode-Budget**:

- F-7 (Idempotency-Key-Replay mit World-State-Drift) hat eine saubere Domäne: der World-State-Hash wird per-PageSession berechnet, im Programmatic Executor BC. Das Interactive Surface BC kennt den Hash nicht — es schickt Picks mit ihrem Idempotency-Key, der Daemon prüft Drift gegen die laufende PageSession.

---

## Related ADRs

- [ADR-002 Single-Writer Helland](./ADR-002-single-writer-helland.md) ist die Disziplin, die diese BC-Trennung intra-process erzwingt.
- [ADR-005 Nursery-per-PageSession](./ADR-005-nursery-per-pagesession.md) ist die concurrency-strukturelle Erzwingung von Single-Writer.
- [ADR-011 anyio Concurrency](./ADR-011-anyio-concurrency.md) ist die Wahl des Concurrency-Mechanismus, der die IntentRequest-Queue als bounded MemoryObjectStream realisiert.

---

## Update 2026-05-17 — Wire-Transport-Realisierung

Die Wire-Boundary zwischen den BCs und dem Tab-Frontend (Channel 2 + 3 aus overview §5) ist seit 2026-05-15/16 als adoptable Foundation-Library extrahiert: `py-wire-rpc` ist die Daemon-Seite des WebSocket-JSON-RPC-2.0-Channels, `ts-wire-rpc` ist die Tab-Seite mit Svelte-5-Runes-Bridge. Beide Libs sind anyio- bzw. Svelte-5-rune-aware und respektieren strukturell die BC-Trennung — kein Wire-Channel spricht beide BCs, die Discrimination passiert im Daemon hinter den Wire-Method-Registries.

Die HTTP-POST-Mutation-Boundary (Channel 3, Idempotency-Key gemäß [ADR-006](./ADR-006-daemon-wall-clock.md)) ist NICHT durch `py-wire-rpc` abgedeckt — sie bleibt im Daemon (klassisches `aiohttp.web` / `starlette`). Status der Foundation-Libs: siehe overview.md §11.

---

## Amendment 2026-05-18 — §UI-Surface revoked, Two-BC-Axiom deferred

Nach 5 Wochen Architektur-Arbeit ohne sichtbares Tool-Verhalten ist diese ADR teilweise revidiert worden. Vollständige Begründung in der Architecture-Reset-Decision 2026-05-18. Konkret:

### A1 — §UI-Surface "never inside the automated browser" ist **revoked**

Die Decision-Section sagte (Original):

> "Interactive Surface BC spricht **WS Push-only** (Server → Browser-Tab) plus **HTTP POST** (Tab → Server, mit Idempotency-Key-Header)."

Und das Diagramm in overview.md §3 (Original):

> "Annotation UI (Svelte 5, ext. Tab, 127.0.0.1:PORT — never inside the automated browser)"

Diese Position war direkt downstream des frontprompt-legacy FAREWELL.md-Schmerzes ("treat browser as dumb executor, host UI outside"). Der Schmerz war **mechanik-spezifisch** (MV3-Extension mit 4 IPC-Layern), nicht prinzipiell. Mit Playwright/CDP-`page.add_init_script`-Inject in einen einzigen Main-World-Context sind die FAREWELL-Probleme strukturell vermieden.

**Ab 2026-05-18 gilt**: Das Overlay-UI lebt **in** der Main World der automated Page, injectiert via Playwright. Formalisiert in [ADR-015 Overlay in Page Main World](./ADR-015-overlay-in-page-main-world.md). Keine separate UI-Tab, keine Discovery-Sequenz, keine zweite Browser-Instanz.

Das hat Folgen für Channel-2 und Channel-3 aus dieser ADR:

- **Channel 2 (WS Push, Daemon → Tab)**: in Phase 1 unbenutzt. Code bleibt (aus `wire-protocol` SP02), wird aktiviert wenn echter Push-Bedarf entsteht.
- **Channel 3 (HTTP POST, Tab → Daemon)**: bleibt aktiv, vereinfacht zu POST `/picks` ohne `IdempotencyReplayCache` (siehe Amendment in [ADR-012](./ADR-012-pick-annotation-aggregate.md)).

### A2 — Two-BC-Axiom ist **deferred**, nicht **revoked**

Die Trennung in "Programmatic Executor BC" und "Interactive Surface BC" bleibt im Code-Layout (`bc/programmatic_executor/`, `bc/interactive_surface/`), wird aber als Architektur-Constraint nicht mehr durchgesetzt. In Phase 1 hat `frontprompt` **einen Use-Case** (User klickt Elemente, Picks werden geloggt) — die Programmatic-Executor-BC mit MCP-Tool-Surface, `InteractionFlow`-Capture/Replay, etc. ist Phase 2+.

**Begründung**: Wir haben einen Bounded-Context-Split eingeführt, bevor wir den zweiten BC tatsächlich nutzten. Das ist Premature-DDD. Wenn Phase 2+ einen echten zweiten Konsumenten bringt (MCP-Agent fragt typed durch das Surface, Annotation referenziert InteractionFlow-Step), wird die Two-BC-Axiom-Disziplin wieder aktiviert — alle Invarianten aus dieser ADR (Single-Writer pro Aggregate, IntentRequest-Queue als einziger Cross-BC-Pfad, ACL-Validation für cross-BC-Identifier) bleiben dann gültig.

**Konkret unbenutzt in Phase 1**:

- IntentRequest-Queue (`H-1`, anyio MemoryObjectStream) — bleibt im Code, kein Producer/Consumer aktiv
- WS-Server (Channel 2) — bleibt im Code, kein Subscriber aktiv
- ProgrammaticReferenceValidator-ACL (aus ADR-012) — entfällt, weil keine cross-BC-Referenzen geprüft werden

Diese Komponenten bleiben **lauffähig und getestet**, damit Phase 2+ sie ohne Re-Implementation wieder nutzen kann.

### A3 — Konsequenz für Aggregat-Set

Die in §Decision aufgelistete Aggregat-Sets bleiben konzeptionell gültig, aber Phase 1 nutzt nur eine Teilmenge:

- **PageSession** (PE-BC): aktiv in Phase 1 — das ist unser Headful-Chromium-Browser-Tab-Wrapper
- **InteractionFlow** (PE-BC): unbenutzt in Phase 1
- **PageSessionProfile** (PE-BC, VO): unbenutzt in Phase 1
- **PointingSession** (IS-BC): drastisch simpler in Phase 1 — in-memory Liste, kein Aggregate-Lifecycle, kein Single-Writer-Nursery (siehe [ADR-012 Amendment](./ADR-012-pick-annotation-aggregate.md))
- **Pick / Annotation** (IS-BC Entities): in Phase 1 = strukturierte Log-Einträge via structlog, keine persistierten Entities

Die volle Aggregat-Topologie wird in Phase 2+ wieder aktiviert.

### A4 — Daemon-Lifecycle wird durch ADR-014 ergänzt

Diese ADR sagte "**ein** Daemon-Prozess hält **alle** Aggregate" aber nicht wie viele Daemon-Prozesse pro User existieren. [ADR-014 Daemon-Singleton via Lockfile](./ADR-014-daemon-singleton-via-lockfile.md) ergänzt: eine Daemon-Instanz pro User, Lockfile-koordiniert, Discovery via `~/.frontprompt/daemon.json`. Multiple Claude-Code-Sessions attachen an dieselbe Daemon.
