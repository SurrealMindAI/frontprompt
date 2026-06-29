# ADR-002 — Single-Writer-per-Aggregate (Helland-Lese-Linse) + Invarianten I1-I6

> Part of the frontprompt [Architecture Decision Records](./index.md).

**Status**: accepted
**Date**: 2026-05-14
**Cross-References**: `../single-writer-helland-explained.md`, [ADR-001 Two BCs](./ADR-001-two-bounded-contexts.md), [ADR-005 Nursery-per-PageSession](./ADR-005-nursery-per-pagesession.md), `../failure-mode-budget.md`

---

## Context

Pat Hellands "Life beyond Distributed Transactions" (CIDR 2007) postuliert: in einem System mit ernsthafter Skalierungs-Ambition kann es keine ACID-Transaktion über mehr als ein Aggregat geben. Cross-Aggregate-Coordination passiert ausschließlich über typed Messages, jedes Aggregat hat genau einen Writer.

Im Patienten v4.2.0 wurde das Pattern strukturell **gebrochen**: der `BrowserManager`-Module-Singleton hielt einen coarse-grained `RLock`, der den Driver und den Transcription-Worker gleichzeitig schützte — zwei orthogonale Concerns in einem Lock-Slot. PKRs Diagnose (Konsortium): das war **Ownership-Confusion**, nicht "zu viele Prozesse". Multi-Process war nicht das Übel, geteilter Lock-Slot über zwei unzusammenhängende Aggregate war es.

Der Successor übernimmt Helland's Pattern als **Charter**. Die Disziplin wird **strukturell** (durch Nursery-Ownership, [ADR-005](./ADR-005-nursery-per-pagesession.md)) und **runtime-checkable** (durch Owner-Task-ID-Assertion in Aggregate-Methoden, AST-Tests gegen Lock-Imports, Audit-Log-Property-Tests) erzwungen.

---

## Decision

Helland's Single-Writer-per-Aggregate ist das **architektonische Axiom** des Successors. Sechs Invarianten **I1-I6** sind als Konsequenz formuliert und werden durch Tests und AST-Checks erzwungen.

### I1 — Aggregate-Identity ist Single-Writer-Quelle

Jedes Aggregat (`PageSession`, `InteractionFlow`, `PointingSession`, `Annotation`) hat eine ULID-Identity. Genau ein Task im Daemon hat das Recht, eine Schreib-Mutation gegen dieses Aggregat zu emittieren. Der Task ist syntaktisch durch eine Nursery-Ownership identifiziert.

### I2 — Cross-Aggregate-Coordination ist Typed-Message-Only

Aggregate sprechen miteinander ausschließlich über die IntentRequest-Queue ([ADR-001](./ADR-001-two-bounded-contexts.md) H-1) oder über In-Process-Aggregate-Specific Message Streams. Niemand greift direkt auf den State eines fremden Aggregats zu.

### I3 — IntentRequest-Queue ist blockierend und bounded

Die Queue verwendet `anyio.create_memory_object_stream(max_buffer_size=N)` mit explizitem Backpressure. Unbounded Queues sind verboten — sie sind ein versteckter Single-Writer-Bruch (Producer schreibt schneller als Consumer liest, Consumer wird Single-Writer eines unbegrenzten Backlogs).

### I4 — World-State-Hash ist Single-Writer-Output

Der World-State-Hash für F-7 (Idempotency-Key-Replay-Schutz) ist eine deterministische Funktion über (active_page_url, dom_structural_fingerprint, last_navigation_lsn) **pro PageSession**. Weil nur ein Task gegen die PageSession schreibt, kann der Hash deterministisch nach jeder Mutation neu berechnet werden, ohne Race.

### I5 — Cancellation propagiert deterministisch entlang Ownership

Wenn ein Aggregat stirbt (OOM, Detach, F-6-Trigger), wird seine zugehörige Nursery cancelled. Cancellation propagiert **nicht** in fremde Aggregate. Andere Aggregate sind strukturell isoliert.

### I6 — Crash-Recovery erzeugt keine Magic-Resume

Beim Daemon-Boot werden alle persistierten Aggregate, deren letzter persistierter State `in_progress` war (typisch: `InteractionFlow` während Capture, `PointingSession` während offener Pick), auf Status `aborted` gesetzt. Audit-Event `crash_recovery_aborted` ist emittiert. Wer fortsetzen will, muss explizit re-trigger mit neuem `IdempotencyKey`.

---

## Consequences

**Code-Konvention**:

- Aggregate-Klassen haben ein `_owner_task_id: TaskId`-Feld, gesetzt im Konstruktor (innerhalb der besitzenden Nursery).
- Alle mutierenden Aggregate-Methoden assertieren `current_task() == self._owner_task_id`. Verstoß fällt sofort mit klarem Stacktrace.
- Reads sind nicht-restringiert.

**Erzwingungs-Tests**:

- **AST-Test**: scannt Source-Tree, gibt Fail wenn ein Aggregate-Class-File `threading.Lock` oder `asyncio.Lock` importiert. Locks sind Indikator dafür, dass jemand das Pattern umgeht.
- **Hypothesis-Stateful-Model**: über Aggregate-Lifecycle (spawn → ... → terminate). Generator wirft zufällige Tool-Call-Sequenzen; Property prüft, dass keine Mutation außerhalb der besitzenden Nursery passiert. Fängt I1- und I2-Verstöße.
- **Audit-Log-Property-Test**: für jeden Aggregate-ID darf nur eine `writer_task_id` im Audit-Log existieren (über die Lebenszeit der Identität).
- **Goldenfile-Boot-Test**: Daemon-Boot mit präparierter Crash-State-DB. Property: alle `in_progress`-Aggregate sind nach Boot `aborted`; Event `crash_recovery_aborted` ist emittiert. Fängt I6-Verstöße.

**Bezug zum Failure-Mode-Budget**:

- F-7 (World-State-Drift) ist nur dank I4 (Hash-Determinismus) detectierbar.
- F-6 (PageSession-OOM) ist nur dank I5 (Cancellation-Isolation) tolerabel.
- F-2 (Tristate-Drift) und F-1 (Schema-Drift) sind durch I1/I2 (Single-Writer für Schema-Mutations) im Pydantic-SSoT-Sinn formal sauberer (siehe [ADR-004](./ADR-004-pydantic-2-13-ssot.md)).

---

## Related ADRs

- [ADR-001 Two BCs](./ADR-001-two-bounded-contexts.md) — die zwei BCs sind jeweils Single-Writer-Universen.
- [ADR-005 Nursery-per-PageSession](./ADR-005-nursery-per-pagesession.md) — die strukturelle Erzwingung von I1, I5.
- [ADR-006 Daemon Wall-Clock](./ADR-006-daemon-wall-clock.md) — I4-Voraussetzung: Wall-Clock als Idempotency-Truth.
- [ADR-007 Failure-Mode-Budget](./ADR-007-failure-mode-budget.md) — F-7 und F-6 hängen direkt an I4/I5.
