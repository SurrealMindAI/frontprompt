# ADR-011 — anyio + structured concurrency

> Part of the frontprompt [Architecture Decision Records](./index.md).

**Status**: accepted
**Date**: 2026-05-14
**Cross-References**: [ADR-002 Single-Writer Helland](./ADR-002-single-writer-helland.md), [ADR-005 Nursery-per-PageSession](./ADR-005-nursery-per-pagesession.md), `../failure-mode-budget.md` F-6, `../nursery-per-pagesession-explained.md`

---

## Context

Der Patient v4.2.0 verwendete `asyncio.create_task()` und `asyncio.gather()` ad hoc, mit gelegentlich vergessenen `RLock`s vor Module-Singletons. Ergebnis: swallowed exceptions in Hintergrund-Tasks, geleakte Tasks beim Shutdown, deadlocks beim Cross-Loop-Call, das ganze Sibling-Loop-Pattern (zwei asyncio-Loops, cross-loop threadsafe calls). Konsequenz: jeder neue Concurrency-Bug brauchte eine eigene Erklärung.

Structured concurrency ([Trio](https://trio.readthedocs.io/), [anyio](https://anyio.readthedocs.io/)) bricht das strukturell:

- **Nursery / TaskGroup** als syntaktisch sichtbare Ownership-Boundary.
- **ExceptionGroup** statt swallowed exceptions in background tasks.
- **Cancellation-Scope** propagiert deterministisch in den Subtree, nicht in fremde Aggregates.

PKR (Konsortium) markierte das als Bedingung 1 für Python-Backend-Tragfähigkeit (`../consortium-of-brain-verdict.md` §2.2 Bedingung 1, HISTORICAL).

---

## Decision

**anyio über asyncio** ist die Concurrency-Library des Successors. Konkret:

- **anyio 4.6.x** als Pin.
- **`anyio.create_task_group()` (Nursery)** für alle long-running task-groups (Daemon-Root-TG, PageSession-Nursery, IntentRequest-Consumer-TG, MCP-Stream-Reader-TGs).
- **`anyio.create_memory_object_stream(max_buffer_size=N)`** für die IntentRequest-Queue zwischen den BCs (H-1). Bounded ist **Pflicht**; unbounded ist verboten (siehe [ADR-002 I3](./ADR-002-single-writer-helland.md)).
- **`anyio.CancelScope`** für explizite Cancellation-Boundary innerhalb einer Nursery (z.B. Timeout-Cancellation für `pick_request`-Blocking-Call).

**CPU-Hot-Spots in ProcessPoolExecutor**:

- DOM-Parses **>5 MB** (HTML-Documents, JSON-Responses >5 MB) gehen in `concurrent.futures.ProcessPoolExecutor` über `anyio.to_thread.run_sync()` plus eigene Pool-Wrapper.
- **`multiprocessing.Pool` ist Pickle-teuer** (~5-10ms Roundtrip) und für Latenz-kritische Pfade ungeeignet; `ProcessPoolExecutor` mit `spawn`-Start-Method ist der Default.
- **`orjson` und `lxml.html.fromstring`** halten die GIL im Hot-Path nicht (Rust- bzw. C-Module, GIL-released) und bleiben im Main-Process.

**Multi-Tab Soft-Cap**:

- **150-250 concurrent Tabs** pro Python-Prozess im Sweet Spot.
- **Hard-Ceiling** ist Chromium-RAM (~150-300 MB pro Tab), nicht Python-Memory oder GIL-Contention.
- Jenseits 300 ist Browser-Pool-Service über Sharding-by-Tenant — das ist eine andere Architektur und **explizit nicht in Scope** des Successors v1.

**PEP 703 (No-GIL) ist Beobachtungs-Slot, kein Default**:

- **3.13 mit GIL** ist das Setting für v1.
- **3.14** bringt nogil als Build-Option auf größerer Front; **3.15+ default**.
- Library-Deps (`scrapling` mit Playwright-Python drunter, `lxml`, `pydantic-core`) müssen jeweils nogil-clean sein. Das ist 2026 nicht gegeben. Subinterpreters (PEP 734) bleiben experimentell.

---

## Consequences

**Strukturelle Erzwingungen**:

- **AST-Test**: scannt Source-Tree gegen `asyncio.create_task()`-Aufrufe direkt in Aggregate-Code (außerhalb von `anyio.TaskGroup.start_soon()`). Verstöße fallen im PR-Test.
- **AST-Test gegen Lock-Imports**: `threading.Lock`, `asyncio.Lock`, `multiprocessing.Lock` in Aggregate-Source-Files = fail. Begründung: Helland-Single-Writer wird strukturell durch Nursery-Ownership erzwungen, nicht durch Locks. Lock-Import ist Indikator für Pattern-Bruch.
- **Memory-Stream-Buffer-Size**: anyio-Memory-Stream ohne `max_buffer_size`-Argument = Lint-Warning (custom Ruff-Rule oder eigener AST-Scanner). Bevorzugt: Build-Fail.

**Bezug zu Single-Writer Helland**:

- **I3** (IntentRequest-Queue ist blockierend und bounded): anyio-Memory-Stream mit `max_buffer_size` ist die operative Implementierung.
- **I5** (Cancellation propagiert deterministisch): anyio's `CancelScope` und `TaskGroup` sind die strukturellen Mechanismen.

**Bezug zu Failure-Mode-Budget**:

- **F-6 PageSession-OOM**: <2s Recovery-SLA ist nur erreichbar weil `anyio.CancelScope.cancel()` deterministisch propagiert. Nursery-Exit schließt Scrapling-Session-Context, Chromium-Subprocess wird via Cleanup-Hook beendet.

**Distribution-Konsequenz**:

- `anyio` ist eine Backend-Dependency, kein Frontend-Concern.
- Test-Code verwendet `pytest-anyio` als Pytest-Plugin, plus `anyio.run()` für End-to-End-Test-Spawn.

**Was diese ADR NICHT macht**:

- Sie schreibt nicht Trio vor (anyio läuft auf asyncio-Backend by default; Trio-Backend ist eine Build-Time-Option für advanced cases, in v1 nicht aktiviert).
- Sie löst nicht das Sub-Interpreter-Pattern (PEP 734 ist experimentell, nicht in Scope).
- Sie spezifiziert kein Browser-Pool-Sharding (>300 Tabs ist nicht im Scope, siehe oben).

---

## Related ADRs

- [ADR-002 Single-Writer Helland](./ADR-002-single-writer-helland.md) — I3 und I5 sind durch anyio strukturell realisiert.
- [ADR-005 Nursery-per-PageSession](./ADR-005-nursery-per-pagesession.md) — die operative Anwendung von anyio TaskGroup.
- [ADR-007 Failure-Mode-Budget](./ADR-007-failure-mode-budget.md) — F-6 hängt an der Cancellation-Determinism dieser ADR.
- [ADR-009 Scrapling-only Substrate](./ADR-009-scrapling-only-substrate.md) — Scrapling's async-API wird durch anyio TaskGroup orchestriert.
