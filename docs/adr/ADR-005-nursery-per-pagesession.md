# ADR-005 — Nursery-per-PageSession Ownership-Topology

> Part of the frontprompt [Architecture Decision Records](./index.md).

**Status**: accepted
**Date**: 2026-05-14
**Cross-References**: Nursery-per-PageSession-Erläuterung (interne Recherche, nicht veröffentlicht), [ADR-002 Single-Writer Helland](./ADR-002-single-writer-helland.md), [ADR-011 anyio Concurrency](./ADR-011-anyio-concurrency.md), [ADR-007 Failure-Mode-Budget](./ADR-007-failure-mode-budget.md) F-6

---

## Context

Der Patient v4.2.0 hatte einen `BrowserManager`-Module-Singleton mit `RLock` über zwei orthogonalen Concerns (Driver-Lifecycle und Transcription-Worker-Lifecycle). Diagnose des Design-Reviews: das war **Ownership-Confusion**, nicht ein bloßes "zu viele Prozesse"-Problem.

In der ersten Fassung von ADR-005 stand ursprünglich nur: *"Single MCP-Server pro User, on-demand."* Das Review hat das geschärft: **Anzahl ≠ Ownership.** Single-MCP-Server schließt das Coarse-Grained-Lock-Problem nicht aus, wenn der eine Server intern wieder einen Module-Singleton hält, der zwei Concerns lockt.

Die Schärfung wurde Freigabe-Bedingung des Design-Reviews. Sie wird hier in der ADR-005-Endfassung als finale Decision festgehalten.

---

## Decision

Der Daemon hält **keinen Browser-State direkt**. Er hält ausschließlich einen `SessionRegistry`, der ein Mapping `PageSessionId → PageSessionHandle` ist — kein State, nur Index.

Jeder `PageSessionHandle` läuft in seiner **eigenen anyio-Nursery** (`TaskGroup`), die innerhalb des Daemon-Root-TG gestartet wird. Diese Nursery **besitzt**:

1. **Den Scrapling-BrowserContext** (`DynamicSession` oder `StealthySession`-Instanz).
2. **Den lokalen Annotation-State** für diese Session.
3. **Den `ReplayBuffer`** (laufende `InteractionFlow`-Capture, falls aktiv).
4. **Die MCP-Stream-Read-Half** für resource-subscribe-Streams gegen diese PageSession.

**Lifecycle**:

- Spawn: ein MCP-Tool-Call `page_navigate` triggert `SessionRegistry.spawn()`, das eine neue PageSession-Nursery startet. Handle wird registriert.
- Run: die Nursery besteht solange, wie die PageSession aktiv ist; alle vier owned Resources laufen in ihr.
- Terminate: `SessionRegistry.terminate(sid)` signaliert Detach, Nursery wickelt sich ab, alle owned Resources werden in Cancellation-Welle abgebrochen.
- Crash-Recovery: per [ADR-002 I6](./ADR-002-single-writer-helland.md) wird kein PageSession-Handle nach Boot resumed; persistente `PageSessionProfile`-Werte (Cookies, Headers, Proxy) sind separat persistiert und werden bei Re-Spawn gelesen, nicht auto-resumed.

**Strukturelle Eigenschaften**:

- **Kein cross-aggregate Lock**: zwei PageSessions teilen weder einen `RLock` noch eine mutable Singleton-Resource. Sie kommunizieren ausschließlich über `IntentRequest`-Queue mit anderen Aggregates ([ADR-001](./ADR-001-two-bounded-contexts.md) H-1).
- **Cancellation ist deterministisch und tief**: Detach-Signal weckt das Nursery-Main, `__aexit__` cancelt Sub-Tasks, Scrapling-Session-`__aexit__` schließt den Browser-Context. Kein leaked Page, kein Zombie-Chromium.
- **SessionRegistry hält keinen State, nur Handles**: wer State will, holt den Handle und spricht mit ihm. Eliminiert die "Singleton hält Browser + AudioWorker + StateManager"-Pathologie des Patienten.

---

## Consequences

**Bezug zu Failure-Mode-Budget**:

- **F-6 (PageSession-OOM)** ist nur tolerabel **dank** dieser Ownership-Topologie. Single-Session-Cancellation reißt keine fremden Sessions mit. Im Patient (Coarse-Grained-Lock) hätte F-6 alle Sessions in einen Deadlock geführt. Recovery-SLA <2s ist gegeben weil Cancellation deterministisch propagiert.
- **F-4 (Substrate-Detection-Failure)** kann pro Session abgebrochen werden, ohne globalen Effekt. Audit-Event `pagesession_id`-tagged.
- **F-7 (World-State-Drift)** ist pro PageSession berechnet, ohne Cross-Session-Interferenz.

**Bezug zu Single-Writer Helland**:

- **I1** (Aggregate-Identity ist Single-Writer-Quelle): die PageSession-Nursery **ist** der Single-Writer-Slot. Wer schreibt, schreibt aus dieser Nursery; wer schreiben will, ohne in dieser Nursery zu sein, wird vom AST-Test (kein Lock-Import) plus Owner-Task-ID-Assertion abgefangen.
- **I5** (Cancellation propagiert deterministisch entlang Ownership): die Nursery-Hierarchie **ist** die Ownership-Hierarchie. Wer cancelled wird, ist genau das Subtree-Scope.

**Code-Strukturelle Konsequenz**:

- Es gibt keine `BrowserManager`-Class (Patient-Anti-Pattern). Es gibt `SessionRegistry` und `PageSessionHandle`. SessionRegistry hat keinen mutierbaren State außerhalb des Handle-Dict; PageSessionHandle ist Single-Owner-pro-Nursery.
- `aiosqlite`-Persistence-Adapter läuft im Daemon-Root-TG, **nicht** in PageSession-Nursery. Begründung: persistence überlebt Session-Tod. Wenn die Session abgebrochen wird, müssen ihre persistierten Events trotzdem schreibbar bleiben (final flushed durch Audit-Subscriber).

**Was diese ADR NICHT macht**:

- Sie löst nicht das Cross-BC-Coordination-Problem zwischen Programmatic Executor und Interactive Surface — das löst die IntentRequest-Queue ([ADR-001](./ADR-001-two-bounded-contexts.md) H-1).
- Sie ersetzt nicht das Distributed-Tracing — Span-Continuity läuft über `trace_id`, der über Daemon-Lebenszeit stabil bleibt ([ADR-006](./ADR-006-daemon-wall-clock.md)).
- Sie ist keine Antwort auf Multi-Tab-Soft-Cap — das ist [ADR-011](./ADR-011-anyio-concurrency.md) (150-250 Tabs pro Daemon).

---

## Related ADRs

- [ADR-002 Single-Writer Helland](./ADR-002-single-writer-helland.md) — die Disziplin, die diese Topologie strukturell instanziiert.
- [ADR-011 anyio Concurrency](./ADR-011-anyio-concurrency.md) — die Concurrency-Library (anyio TaskGroup), die die Nursery bereitstellt.
- [ADR-007 Failure-Mode-Budget](./ADR-007-failure-mode-budget.md) — F-6 hängt direkt an dieser Topologie.
