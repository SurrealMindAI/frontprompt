# ADR-007 — Failure-Mode-Budget (geschlossen, 7 Klassen)

> Part of the frontprompt [Architecture Decision Records](./index.md).

**Status**: accepted (closed)
**Date**: 2026-05-14
**Cross-References**: `../failure-mode-budget.md` (Volltabelle), `../user-directive-corrections.md` Korrektur 5

---

## Context

Kralls Charter-Bedingung 4 (`../consortium-of-brain-verdict.md` §1 Pre-emptive Eviszerationen, HISTORICAL):

> Spezifiziere die Failure-Mode-Budget. Was kinds of failure are tolerable, what kinds are not. Legacy spent its lifetime treating "Chrome crashed" und "MV3 didn't inject" und "STT detection lied" als bugs to be fixed individually rather than as classes of failure to be designed against. The successor must declare its budget *before* its tools.

Das Konsortium identifizierte 5 Klassen (Discriminated-Union-Branch-Drift, Validator-Semantik-Drift unter Tristate, Recursion-Cycle-Drift, Substrate-Detection-Failure, Silent-Match-Drift) und ließ das Budget offen, mit Krall persönlich als Owner. User-Korrektur 5 (`../user-directive-corrections.md`) schloss das Budget mit einer **7-Klassen-Tabelle** und expliziter Detection/Response/Recovery-Pflicht pro Klasse.

---

## Decision

Das Failure-Mode-Budget des Successors umfasst **genau 7 Klassen**, geschlossen. Wer eine 8. Klasse entdeckt, eröffnet eine neue ADR, die dieses Budget explizit revidiert. Keine "ergänzen wir nach Bedarf"-Klausel.

### Executive Summary der 7 Klassen

| Klasse | Kurzbezeichnung | Tolerabel? |
|---|---|---|
| **F-1** | Schema-Drift (Pydantic ↔ Zod) | NEIN — CI-Drift-Gate fails Build |
| **F-2** | Tristate-Drift (None / undefined / missing) | NEIN — Goldenfile-Property-Test fails Build |
| **F-3** | Recursion-Cycle-Drift im Property-Test-Generator | TOLERABEL (Skip-mit-Warn, Depth-Bound) |
| **F-4** | Substrate-Detection-Failure (Cloudflare iteriert) | TOLERABEL (Engineering-Eskalations-Hook) |
| **F-5** | Silent-Match-Drift (adaptive Selector matched falsch) | NEIN — Match-Confidence-Score-Cutoff 0.85 |
| **F-6** | PageSession-OOM (Chromium-RAM oder >50 MB DOM) | TOLERABEL (Nursery-Cancellation <2s) |
| **F-7** | Idempotency-Key-Replay mit World-State-Drift | NEIN — HTTP 409 mit Drift-Diagnose |

Volltabelle mit Trigger / Detection / Response / Recovery-SLA pro Klasse in `../failure-mode-budget.md`. Diese ADR enthält nur Executive-Summary und Strukturelle Begründung.

---

## Consequences

**Vier nicht-tolerable Klassen** (F-1, F-2, F-5, F-7) müssen **strukturell unmöglich** sein — entweder durch CI-Gate (build fails vor merge) oder durch Runtime-Reject (HTTP 409, Tool-Call-Block). Keine "wir loggen und hoffen"-Strategie.

**Drei tolerable Klassen** (F-3, F-4, F-6) haben **explizite Response**, kein silent retry und kein generischer Exception-Handler. Tolerabel heißt: die Architektur **leistet** etwas — eine Cancellation (F-6), eine Eskalation (F-4), eine Skip-with-Warn (F-3) — und das ist Single-Path, nicht eine offene Retry-Schleife.

**Verteilung über die ADRs**:

| Klasse | Primär-ADR |
|---|---|
| F-1 | [ADR-004 Pydantic SSoT](./ADR-004-pydantic-2-13-ssot.md), [ADR-010 Codegen-Pipeline](./ADR-010-codegen-pipeline.md) |
| F-2 | [ADR-010 Codegen-Pipeline](./ADR-010-codegen-pipeline.md) |
| F-3 | [ADR-010 Codegen-Pipeline](./ADR-010-codegen-pipeline.md) |
| F-4 | [ADR-009 Scrapling-only Substrate](./ADR-009-scrapling-only-substrate.md) |
| F-5 | [ADR-009 Scrapling-only Substrate](./ADR-009-scrapling-only-substrate.md), [ADR-006 Daemon Wall-Clock](./ADR-006-daemon-wall-clock.md) |
| F-6 | [ADR-005 Nursery-per-PageSession](./ADR-005-nursery-per-pagesession.md), [ADR-011 anyio Concurrency](./ADR-011-anyio-concurrency.md) |
| F-7 | [ADR-006 Daemon Wall-Clock](./ADR-006-daemon-wall-clock.md), [ADR-002 Single-Writer Helland](./ADR-002-single-writer-helland.md) |

**Klassen, die nicht im Budget sind und es bewusst nicht sind**:

- **Chrome-Crash**: tolerabel implizit via F-6 (PageSession-OOM hat denselben Cancellation-Pfad). Wir trennen nicht "Chrome ist abgestürzt" von "Chromium-RAM-overflow" — beides löst F-6 aus.
- **MCP-Wire-Disconnect**: tolerabel implizit. MCP-Client ist verantwortlich für Reconnect; der Daemon (persistent) bleibt aktiv. Idempotency-Key-Replay greift bei Re-Send.
- **WS-Disconnect** (Frontend-Tab): tolerabel implizit. WS-Reconnect mit Client-Cursor (siehe 12-Hub-Protocol-Synthese in `../12-hub-final-synthesis.md` Phase 1, HISTORICAL). Annotation-State persistiert im Daemon, geht beim Tab-Reload nicht verloren.

---

## Related ADRs

- [ADR-002 Single-Writer Helland](./ADR-002-single-writer-helland.md), [ADR-004 Pydantic SSoT](./ADR-004-pydantic-2-13-ssot.md), [ADR-005 Nursery-per-PageSession](./ADR-005-nursery-per-pagesession.md), [ADR-006 Daemon Wall-Clock](./ADR-006-daemon-wall-clock.md), [ADR-009 Scrapling-only Substrate](./ADR-009-scrapling-only-substrate.md), [ADR-010 Codegen-Pipeline](./ADR-010-codegen-pipeline.md), [ADR-011 anyio Concurrency](./ADR-011-anyio-concurrency.md).
