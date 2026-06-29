# ADR-004 — Pydantic v2.13.x als Schema-SSoT

> Part of the frontprompt [Architecture Decision Records](./index.md).

**Status**: accepted
**Date**: 2026-05-14
**Cross-References**: overview.md §4, [ADR-010 Codegen-Pipeline](./ADR-010-codegen-pipeline.md), `../failure-mode-budget.md` F-1, F-2, `../../sources/pydantic-version-policy-snapshot.md`, `../user-directive-corrections.md` Korrektur 2

---

## Context

Codegen-Drift war im Patienten v4.2.0 strukturell präsent: Pydantic-Modelle in `state/models.py`, TypeScript-Interfaces in `overlay/src/types/*.ts`, dazwischen ein `scripts/codegen.py` mit sechs Stufen und ein `test_codegen_no_drift.py` als CI-Pflaster. Drei Definitionen eines Konzepts, drei Stellen, an denen Drift entstehen kann. Eine `test_ts_python_parity.py` testete eine Klasse von Drift retroaktiv.

HTM hat im Konsortium das Phänomen formal definiert: `Drift(Spec_P, Spec_T) ≡ ∃ i ∈ U_op. Spec_P.validate(i) ≠ Spec_T.validate(i)`. Vier Bedingungen für No-Drift: (a) eindeutige Quelle, (b) deterministische totale Generatoren, (c) validation-extensional äquivalente Encodings, (d) kein Hand-Edition-Pfad in der Build-Pipeline.

Vier Begründungs-Punkte für **Pydantic-als-Source** (HTM §5):

1. **Beweislast-Asymmetrie**: ein Generator zu beweisen ist strikt einfacher als zwei plus eine Schema-IR-Treue-Bedingung.
2. **Validation-Default-Vermeidung**: Pydantic *ist* schon das Backend-Validation-Modell. `Spec_P = identity` schließt die Lücke zwischen Spec-Definition und Backend-Verhalten strukturell.
3. **Single-Writer-Erzwingung**: Pydantic-as-Source erzwingt einen einzigen Writer für Schema-Mutationen — den Python-Entwickler. ([ADR-002](./ADR-002-single-writer-helland.md) verlangt das.)
4. **Audit-Trail**: Pydantic-Modelle und `_generated/*.ts` leben beide in git; Drift = git-diff.

Der konkrete Pin ist **v2.13.x** — gewählt nach Context7-Verifikation 2026-04-13. v2.13.0 ist die aktuelle Production-Release-Linie. v3 ist Roadmap, nicht released. Auf v2.10.x zu pinnen (Konsortium-Default) wäre ein bewusster Backstep um drei Minor-Versions. Snapshot der Verifikation: `../../sources/pydantic-version-policy-snapshot.md`.

User-Korrektur 2 hat den Pin von v2.10.x auf v2.13.x angehoben — autoritative Begründung in `../user-directive-corrections.md`.

---

## Decision

**Pydantic v2.13.x** ist die einzige Quelle für Datenmodell-Definitionen im frontprompt-Successor:

- **Aggregate-Schemas** im Programmatic Executor BC (`PageSession`, `InteractionFlow`, `PageSessionProfile`) sind Pydantic-Modelle.
- **Aggregate-Schemas** im Interactive Surface BC (`PointingSession`, `Annotation`, `Pick`) sind Pydantic-Modelle.
- **Wire-Payloads** für MCP-Tool-Inputs, WS-Push-Frames, HTTP-POST-Bodies sind Pydantic-Modelle.
- **IntentRequest-Queue-Messages** zwischen den BCs sind Pydantic-Modelle.

Aus diesen Pydantic-Modellen generiert die [Codegen-Pipeline](./ADR-010-codegen-pipeline.md) **deterministisch und total** JSON-Schema 2020-12, und daraus Zod-Schemas (Frontend) plus MCP-Tool-Input-Schemas (Backend selbst, für MCP-Wire-Manifest).

Konkrete Sub-Entscheidungen:

- **Branded IDs** via `Annotated[str, Brand("PageSessionId")]` mit dem im PEP 681 spezifizierten `Brand`-Wrapper-Pattern oder einem äquivalenten Marker. Generator emittiert auf der Zod-Seite `.brand<"PageSessionId">()`.
- **`extra="forbid"`** ist der Default für alle Pydantic-Modelle (entspricht Zod's `.strict()`). Wer eine offene Map will, muss `extra="allow"` explizit setzen.
- **Tristate-Normierung** (siehe [ADR-010](./ADR-010-codegen-pipeline.md)): `None`-vs-`undefined`-vs-`missing` wird im Generator explizit normiert; F-2-Detection (Goldenfile-Property-Test) gilt als Pflicht.
- **Discriminated Unions** mit `Field(discriminator="kind")` — Generator emittiert auf Zod-Seite `z.discriminatedUnion("kind", [...])`.

---

## Consequences

**Was strukturell verhindert wird**:

- **F-1 Schema-Drift** wird zur unmöglichen Bug-Klasse: Pydantic-Modell-Update ohne Re-Codegen wird vom pre-commit-Hook und CI-Drift-Gate abgefangen. Pydantic-Modell-Update mit erfolgreichem Re-Codegen propagiert die Änderung byte-deterministisch.
- **F-2 Tristate-Drift** wird durch explizite Generator-Normierung plus bidirektionale Goldenfile-Property-Tests gefangen.
- **Manuelle Edits in `_generated/`** sind durch pre-commit-Hook verboten. Frontend importiert ausschließlich aus `_generated/`-Pfaden für Wire-Types.

**Was strukturell akzeptiert wird** (SKH's Eingeständnis):

Die Wahl macht Bedienung *teuer*, nicht *unmöglich*. Universe-of-Codes (Option C) wäre strukturell unausdrückbar als Drift, aber der Interpreter-Boilerplate-Preis pro Sprache ist außerhalb unseres Budgets. Wir akzeptieren "teuer statt unmöglich" und kompensieren mit Goldenfile-Property-Tests (HTM §6 Co-Sign-Bedingung).

**Versions-Disziplin**:

- Bump auf v2.14, v2.15 → kompatibel ohne Charter-Änderung.
- Bump auf v3.x → erfordert ADR-Update (mindestens ein neuer ADR, der die Migration plant und neue Codegen-Drift-Klassen abprüft, sobald v3 stable released ist).

**Bezug zur Audit-Trail-Diszipline**:

Pydantic-Modelle leben in einem klar definierten Source-Tree (`src/frontprompt/schemas/`). Jeder Modell-Change ist ein git-commit; jeder generierte Zod-Schema-Change ist im `_generated/`-Tree als git-diff sichtbar. Audit-Trail ist git-native; kein eigenes Schema-Registry, kein eigenes Migration-Framework.

---

## Related ADRs

- [ADR-010 Codegen-Pipeline](./ADR-010-codegen-pipeline.md) — operative Detail der Pydantic → JSON-Schema → Zod-Brücke.
- [ADR-002 Single-Writer Helland](./ADR-002-single-writer-helland.md) — Pydantic-SSoT erzwingt Single-Writer für Schema-Mutations.
- [ADR-007 Failure-Mode-Budget](./ADR-007-failure-mode-budget.md) — F-1 und F-2 leben gegen diese ADR.
