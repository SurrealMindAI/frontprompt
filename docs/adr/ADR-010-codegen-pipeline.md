# ADR-010 — Codegen-Pipeline Pydantic v2.13 → JSON-Schema → Zod

> Part of the frontprompt [Architecture Decision Records](./index.md).

**Status**: accepted
**Date**: 2026-05-14
**Cross-References**: [ADR-004 Pydantic SSoT](./ADR-004-pydantic-2-13-ssot.md), [ADR-007 Failure-Mode-Budget](./ADR-007-failure-mode-budget.md) F-1, F-2, F-3, pydantic-version-policy-snapshot (historische atlas-Recherche-Quelle, nicht extrahiert)

---

## Context

[ADR-004](./ADR-004-pydantic-2-13-ssot.md) etabliert Pydantic v2.13.x als Schema-Source-of-Truth. Diese ADR ist die **operative Detail-Spezifikation**, wie die Schemas in das Frontend (Zod 3.24.1) und in die MCP-Wire-Manifests (JSON-Schema 2020-12) übersetzt werden, und welche Drift-Klassen strukturell vermieden werden müssen.

HTM's Konsortiums-Analyse (consortium-of-brain-verdict §2.1, historische atlas-Recherche, nicht extrahiert) listete vier Drift-Klassen bei deterministischen totalen Generatoren:

1. **Hand-Edition** (eliminierbar via pre-commit-Hook + CI-Drift-Gate)
2. **Validation-Default-Divergenz** (`additionalProperties` als `extra="forbid"` ↔ Zod `.strict()`)
3. **Recursion / Discriminated-Union-Branch-Drift** (Runtime-Restrisiko)
4. **Regex-Pattern-Divergenz** (ECMA-262 vs Python `re`-Unicode-Klassen)

HTM verlangte als Co-Sign-Bedingung: *"Codegen-Tests (Goldenfile-Property-Tests, Discriminated-Union-Cross-Tests, `None`/`undefined`/`missing`-Tristate-Tests, Regex-Pattern-Normalisierungs-Tests) sind Teil der CI; ohne sie ist ADR-010 nicht wahr"*. Bedingung akzeptiert, hier formalisiert.

---

## Decision

Die Codegen-Pipeline läuft in **drei deterministischen totalen Schritten**:

```
Pydantic v2.13.x Models (src/frontprompt/schemas/)
   │
   │  Schritt 1: pydantic.json_schema() → JSON-Schema 2020-12
   ▼
JSON-Schema 2020-12 (committed in _generated/json-schema/)
   │
   │  Schritt 2: eigener Emitter (TypeScript-Output)
   ▼
Zod 3.24.1 Schemas (committed in _generated/zod/)
   │
   │  Schritt 2b: derselbe Emitter
   ▼
MCP-Tool-Input-Schemas (committed in _generated/mcp-tools/)
```

**Strukturelle Erzwingungen**:

1. **`_generated/`-Marker** im Pfadname jeder generierten Datei. Pre-commit-Hook verbietet manuelle Edits in `_generated/`-Pfaden (per `git diff --name-only HEAD`).
2. **Frontend importiert ausschließlich aus `_generated/zod/`-Pfaden** für Wire-Types. Eigene Anpassungen (Brand-Augmentation, UI-spezifische Hilfs-Types) leben in separaten Files **außerhalb** `_generated/`. AST-Test scannt Frontend-Imports.
3. **CI-Drift-Gate vergleicht byte-exakt**: Build-Job läuft `pydantic-to-zod`-Emitter, vergleicht mit committedem `_generated/`-Tree. Diff → Fail.
4. **Discriminated-Union-Branches** im Pydantic-Modell (`Field(discriminator="kind")`) werden in Zod als `z.discriminatedUnion("kind", [...])` emittiert.

### Tristate-Normierung (F-2-Antwort)

Pydantic-`Optional[T]` vs Zod-`.optional()` vs Zod-`.nullable()`:

- **Pydantic `Optional[T]`** (`field: T | None = None`) → wird im Generator normiert auf:
  - JSON-Schema: `{"anyOf": [{"type": "..."}, {"type": "null"}], "default": null}` (nullable, default null)
  - Zod: `z.<T>().nullable().optional()` (sowohl null als auch undefined als auch missing werden akzeptiert, alle drei normalisieren auf `null`-equivalent in der internen Repräsentation)

- **Pydantic strict-missing** (Feld ohne Default, kein `Optional`) → 
  - JSON-Schema: `"required": ["..."]`
  - Zod: `z.<T>()` (kein `.optional()`, kein `.nullable()`)

- **Pydantic explicit-nullable** (`field: T | None`, ohne Default) →
  - JSON-Schema: `{"anyOf": [{"type": "..."}, {"type": "null"}]}`, `"required": ["..."]`
  - Zod: `z.<T>().nullable()` (null erlaubt, undefined/missing NICHT)

Diese Tristate-Normierung ist **explizit dokumentiert** im Generator-Source und wird durch F-2-Property-Test gegen Goldenfile-Corpus geprüft.

### Goldenfile-Property-Tests (HTM Co-Sign-Bedingung)

Bidirektional, gegen einen committedem Schema-Corpus in `tests/codegen-goldenfile/`:

- **Pydantic → JSON → Validate-by-Zod**: für jedes Pydantic-Modell wird via Hypothesis-Generator ein Sample erzeugt, zu JSON serialisiert, durch den generierten Zod-Schema validiert. Failure = F-1 oder F-2.
- **Zod-Validation-Round-Trip**: fast-check generiert Samples gegen das Zod-Schema, JSON-serialisiert, durch Pydantic re-validiert. Failure = F-1 oder F-2.
- **Tristate-Property-Test**: Hypothesis-Generator emittiert pro Optional-Field die drei Variants `(missing, null, present)`, fast-check empfängt sie via Zod, prüft Roundtrip-Konsistenz.
- **Discriminated-Union-Cross-Test**: alle Branches einer Discriminated-Union werden gegeneinander gevalidiert; wer Branch A schickt, muss von Branch A's Schema akzeptiert werden, von Branch B's Schema rejected werden.
- **Regex-Pattern-Normalisierung**: Pydantic-`pattern`-Field wird als ECMA-262-kompatibel ausgewählt (oder explizit konvertiert; Python-`re`-Unicode-Klassen ohne ECMA-262-Pendant sind verboten und werden vom Generator als Build-Fail erkannt). Property-Test gegen Stichproben-Strings, die in beiden Regex-Engines konsistent matchen müssen.

### Recursion-Cycle-Drift (F-3)

Pydantic erlaubt rekursive Schemas (`Selector.children: list[Selector]`). Property-Test-Generator hat eine harte `max_recursion_depth=8`-Konstante:

- **Hypothesis**: `recursive()` mit `max_leaves`-Bound.
- **fast-check**: `letrec()` mit Depth-Counter.

Schema, das gegen die Depth-Bound trifft, wird mit Audit-Event `recursion_bound_hit` geloggt; Test bleibt grün. Aggregat-Pathologie wird detected, wenn ein Schema >1% Skip-Rate hat — Trigger für ADR-Review.

---

## Consequences

**Was strukturell vermieden wird**:

- **F-1 Schema-Drift**: pre-commit-Hook plus CI-Drift-Gate fängt Pydantic-Update-ohne-Re-Codegen. Build fails.
- **F-2 Tristate-Drift**: Goldenfile-Property-Test mit `(missing, null, present)`-Generator catched Validator-Divergenz.
- **F-3 Recursion-Cycle-Drift**: Depth-Bound im Generator, Skip-mit-Warn als Response, Audit-Log-Aggregat als Pathologie-Detection.

**Was strukturell akzeptiert wird**:

- Generator-Implementierung lebt in `tools/codegen/` (atlas-internes Tool, nicht Distribution-Bundle). Der Generator selbst hat unit-tests gegen ein Mini-Corpus aus Single-Field-Modellen, plus die Goldenfile-Tests gegen das Production-Corpus.
- Brand-Augmentation für Frontend ist **separat** von `_generated/zod/`. Frontend-Code: `import { PageSessionIdBrand } from "../augment/page-session.brand"` plus `import { PageSession } from "../_generated/zod/page-session.schema"`.

**Distribution-Konsequenz**:

- Das `_generated/`-Verzeichnis ist **committed in git** (nicht .gitignore'd). Das ist die Audit-Trail-Disziplin aus HTM §5 P.4: Drift = git-diff.
- Beim Develop wird der Generator manuell oder per pre-commit gestartet (Bash-One-Liner `make codegen` oder ähnlich). Der Generator ist Python (Teil der Backend-Pipeline), nicht TypeScript.

**Was diese ADR NICHT macht**:

- Sie spezifiziert nicht den konkreten Emitter-Source. Implementierungs-Frage; das Pattern (Pydantic → JSON-Schema → Zod) ist gesetzt, die Code-Module sind nicht hier festgelegt.
- Sie löst nicht die Frage, ob `datamodel-code-generator` reverse-direction (JSON-Schema → Pydantic) parallel als Sanity-Check verwendet wird. Sanity-Check ist optional; Goldenfile-Property-Test ist Pflicht.

---

## Related ADRs

- [ADR-004 Pydantic SSoT](./ADR-004-pydantic-2-13-ssot.md) — die Schema-SSoT, deren Codegen diese ADR spezifiziert.
- [ADR-007 Failure-Mode-Budget](./ADR-007-failure-mode-budget.md) — F-1, F-2, F-3 hängen direkt an dieser ADR.
- [ADR-008 Svelte 5 Runes](./ADR-008-svelte-5-runes.md) — der Consumer der generierten Zod-Schemas.

---

## Update 2026-05-17 — Adoptierte Pipeline-Implementierung

Diese ADR ist seit 2026-05-15 als eigenständige Library realisiert: `pydantic-zod-codegen`. Die offen gelassene Frage "konkreter Emitter-Source" (siehe "Was diese ADR nicht entscheidet") ist beantwortet als **FastUI-hybrid pattern**: `CustomGenerateJsonSchema` (Pydantic-side) → `$defs`→`definitions` Pre-Processor → `bunx json-schema-to-typescript@15` → Zod-v4 Post-Processor (TS-side).

Die in §"Tristate-Normierung (F-2-Antwort)" geforderte Disziplin (None / undefined / missing kollabieren strukturell auf eines) ist in der Pipeline strukturell durchgesetzt. Goldenfile-Property-Tests (F-3-Antwort) sind als `pytest -m drift` realisiert und CI-gated gemäß 2026-05-06 unified-protocol §5.

Konsum durch frontprompt: git-link in `pyproject.toml`. Drift-Detection (F-1) im frontprompt-CI-Pipeline durch denselben `pytest -m drift`-Mechanismus, nur gegen die frontprompt-eigenen Pydantic-Models.
