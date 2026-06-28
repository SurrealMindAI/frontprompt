# ADR-006 — Daemon Wall-Clock als Idempotency-Truth

> Part of the frontprompt [Architecture Decision Records](./index.md).

**Status**: accepted
**Date**: 2026-05-14
**Cross-References**: [ADR-002 Single-Writer Helland](./ADR-002-single-writer-helland.md), `../failure-mode-budget.md` F-7

---

## Context

ULID enthält ein 48-bit Millisekunden-Timestamp als Präfix. Es ist verlockend, dieses Präfix als **Ordnungs-Truth** für Cross-Aggregate-Events zu verwenden ("Event A hat ULID kleiner als Event B, also kam A vor B"). Das ist **falsch**: ULID-Timestamp ist eine **Hint** für lexikographische Sortierbarkeit, kein verlässliches Ordering-Substrat.

Gründe:

1. **Cross-process Clock-Skew**: zwei Prozesse erzeugen ULIDs mit ihren lokalen Wall-Clocks. Eine erzeugte ULID kann lexikographisch kleiner sein als eine später erzeugte, weil der andere Prozess eine schnellere Uhr hat.
2. **NTP-Jumps**: ein Daemon, der monate-lang läuft, sieht NTP-Adjustments. Wall-Clock kann rückwärts springen.
3. **DST-Transitions**: lokale Zeitzonen-Adjustments sind außerhalb UTC-internal-time-Domäne, aber Systemzeit kann beeinflusst sein.

Im Patient v4.2.0 wurde das nie als Architektur-Constraint formuliert. Die Causality-Persona aus dem 12-Hub identifizierte das als CE-6 (Causality-Event Nr. 6): die Reihenfolge von Aggregate-Mutations ist nicht-trivial im einzelnen Aggregate, und ULID-Präfix darf das nicht entscheiden.

---

## Decision

**Daemon-Wall-Clock** ist die **einzige Truth-Quelle** für Idempotency-Cache-Lifetime, World-State-Hash-Berechnung, und Audit-Event-Timestamps innerhalb des Daemons.

**ULID-Time-Prefix** ist ein **Sortier-Hint**, keine Truth. Lexikographische Sortierung über ULID ist erlaubt für Display-Reihenfolgen und schwache Index-Strategien; harte Ordering-Invarianten (z.B. "Replay-Step N kam vor Replay-Step N+1") werden über **explizite LSNs pro Aggregate** gepflegt (Single-Writer pro Aggregate macht das deterministisch — siehe [ADR-002 I4](./ADR-002-single-writer-helland.md)).

Konkrete Anwendungen:

1. **Idempotency-Cache-TTL**: 24h ab `daemon.monotonic_time()`-Snapshot beim Insert. NTP-Jumps beeinflussen monotonic-clock nicht. Kein Real-Wall-Clock für TTL-Berechnung — `monotonic()` ist die Truth.

2. **World-State-Hash-Berechnung** (für F-7): der Hash ist deterministisch über (active_page_url, dom_structural_fingerprint, `last_navigation_lsn`). Der `last_navigation_lsn` ist **per PageSession** monoton, gepflegt durch den Single-Writer der PageSession-Nursery — er ist die einzige Ordering-Quelle, die F-7 braucht. Wall-Clock-Time geht **nicht** in den Hash ein.

3. **Audit-Event-Timestamps**: Wall-Clock-Time ist im Audit-Log enthalten **plus** ein monotonic-clock-Tick (`daemon_monotonic_ns`). Beim Audit-Replay (Forensik nach Daemon-Crash) wird `daemon_monotonic_ns` als primärer Sort-Key verwendet; Wall-Clock dient als Mensch-lesbarer Hint.

4. **MCP-Response-Timestamps**: dem MCP-Client zurückgegebene Zeit-Werte sind in **UTC ISO 8601** (Wall-Clock-Display), aber interne Berechnungen verwenden `monotonic_time`. Wenn ein MCP-Client einen Idempotency-Key mit einer "expired_at"-Annotation schickt, wird er gegen den Daemon-monotonic-snapshot validiert, nicht gegen Wall-Clock.

---

## Consequences

**Bezug zu Failure-Mode-Budget**:

- **F-7 (Idempotency-Key-Replay mit World-State-Drift)** ist nur korrekt detectierbar, weil der World-State-Hash nicht von Wall-Clock abhängt. Wäre er es, wäre der Drift-Check non-deterministic (zwei Berechnungen desselben State-Sets könnten unterschiedliche Hashes geben wegen Time-Component-Drift).

**Bezug zu Distributed Tracing**:

OpenTelemetry-Spans verwenden monotonic-clock für `start_time_unix_nano` / `end_time_unix_nano`. Wall-Clock geht nur in `created_at` ein, das im Span als Mensch-lesbares Hint dient.

**Was diese ADR NICHT macht**:

- Sie ersetzt nicht die per-Aggregate-LSN (siehe I4 in [ADR-002](./ADR-002-single-writer-helland.md)). LSN ist Single-Writer-Output und löst harte Ordering-Invarianten innerhalb eines Aggregates.
- Sie löst nicht die Cross-Aggregate-Ordering-Frage (es gibt keine globale Truth über Aggregate-Boundary hinweg; jeder Aggregat-Verband hat seine eigene Ordering-Domäne).
- Sie schreibt keinen Wall-Clock-Format vor: ISO 8601 für Display, monotonic-time für interne Berechnungen ist Pattern, nicht Schema-Pflicht.

**Code-Konsequenz**:

- Der Daemon hat eine `DaemonClock`-Class mit `now() -> WallClockTime`, `monotonic_ns() -> int`, und `idempotency_ttl_check(snapshot: MonotonicSnapshot) -> bool`.
- Aggregate-Methoden, die Time brauchen, holen sich die Time über `DaemonClock`, nicht über `time.time()` oder `datetime.now()`. AST-Test gegen direkte `time.time()`-Imports in Aggregate-Source-Files.

---

## Related ADRs

- [ADR-002 Single-Writer Helland](./ADR-002-single-writer-helland.md) — I4 (World-State-Hash) hängt strukturell an dieser ADR.
- [ADR-007 Failure-Mode-Budget](./ADR-007-failure-mode-budget.md) — F-7 lebt gegen diese ADR.
