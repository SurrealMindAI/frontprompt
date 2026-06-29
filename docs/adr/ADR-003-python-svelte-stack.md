# ADR-003 — Python 3.13 Backend + TypeScript / Bun / Svelte 5 Frontend

> Part of the frontprompt [Architecture Decision Records](./index.md).

**Status**: accepted
**Date**: 2026-05-14
**Cross-References**: overview.md §4 Stack-Inventar, [ADR-008 Svelte 5 Runes](./ADR-008-svelte-5-runes.md), [ADR-004 Pydantic 2.13 SSoT](./ADR-004-pydantic-2-13-ssot.md), [ADR-011 anyio Concurrency](./ADR-011-anyio-concurrency.md), `../user-directive-corrections.md`

---

## Context

Der 12-Hub konvergierte initial auf TypeScript-end-to-end (Polyglots Eröffnung: Node 22 LTS für Daemon, Bun für Tooling). Diese Wahl hatte zwei Probleme: (1) sie war eine **unausgesprochene** Default-Setzung — keine Persona forderte expliziten Counter-Beweis; (2) sie folgte einem Reflex ("TS ist neuer und nicer für lokale Tools"), nicht einer Invariante.

Im Konsortium-Hub kippte das. Krall stellte seinen unausgesprochenen Python-Prior explizit; PKR lieferte die GIL-Analyse mit klaren Tragfähigkeits-Bedingungen; HTM stützte die Pydantic-SSoT-Asymmetrie; SKH dokumentierte den Disziplin-Defekt der unausgesprochenen Präferenz. Die Konsortiums-Empfehlung wurde: Python 3.13 für Backend, TypeScript für Frontend.

Die User-Direktive (`../user-directive-corrections.md` Korrektur 3) korrigierte das Frontend-Framework von SolidJS auf **Svelte 5 mit Runes** (Team-Erfahrung).

---

## Decision

**Backend**: Python **3.13.x**. Distribution via `uv tool install frontprompt`. Single Daemon-Process. anyio über asyncio. Pydantic v2.13.x als Schema-SSoT.

**Frontend**: TypeScript **5.4+**, gebaut mit Bun **1.2.x** (FE-only — kein `bun build --compile`). Framework **Svelte 5** mit Runes (`$state`, `$derived`, `$effect`). Schemas werden aus Pydantic generiert ([ADR-010](./ADR-010-codegen-pipeline.md)).

**Kein Node im Stack**. Bun ist ausschließlich Frontend-Build-Tool; das fertige Frontend-Bundle ist ein statisches Artefakt, das vom Python-Daemon ausgeliefert wird (HTTP GET auf `/ui/`).

**Distributionsweg ist Python, nicht Bun**:

- `uv tool install frontprompt` → installiert ein PEP-723-kompatibles Python-Package mit Entry-Point `frontprompt`.
- `frontprompt start` startet den Daemon; das eingebettete Frontend-Bundle wird aus dem Python-Package-Resource-Path serviert.
- Kein eigenes Binary pro Plattform; uv kümmert sich um Python-Runtime-Bootstrapping plus virtuelles Tool-Environment.

---

## Consequences

**Warum Python-Backend trotz Patient-Pathologie**:

Der Patient v4.2.0 starb nicht *an Python*, sondern an drei strukturellen Anti-Patterns, die strukturell vermeidbar sind:

1. **Drei Python-Prozesse parallel** (Daemon + MCP-Server + Worker) — wir haben **einen** Daemon mit Nursery-per-PageSession ([ADR-005](./ADR-005-nursery-per-pagesession.md)).
2. **Coarse-grained RLock vor Module-Singleton** mit zwei Concerns — Single-Writer-per-Aggregate ([ADR-002](./ADR-002-single-writer-helland.md)) verbietet das strukturell.
3. **CPU-Hot-Spots im Main-Loop** — `ProcessPoolExecutor` für DOM-Parses >5 MB ([ADR-011](./ADR-011-anyio-concurrency.md)).

Browser-Automation ist ~95% IO-bound. CDP-WebSocket-Roundtrips geben die GIL am `await` zurück. lxml und pydantic-core (Rust) halten die GIL im Hot-Path nicht. PEP 703 (No-GIL) ist Beobachtungs-Slot ab 3.15-default — keine Migration-Voraussetzung.

**Warum TS-Frontend zwingend ist**:

Das Frontend läuft im Browser-Tab. Es hat keine andere ausführbare Sprache. Polyglot-Tax = eine harte Boundary (Pydantic ↔ Zod via Codegen, [ADR-010](./ADR-010-codegen-pipeline.md)), nicht beliebig viele.

**Warum Svelte 5 statt SolidJS**:

User-Korrektur 3 ist autoritativ. Begründung: Team-Erfahrung. Atlas hat mehrere Research-Topics zu Svelte 5 (svelte-5-ecosystem, svelte-runes-extension-rules, svelte5-runes-external-state-bridge, tiptap-svelte5-prosemirror-bridge) — SolidJS hätte ein neues Framework eingeführt. Bundle-Size und Signal-Modell sind zwischen den beiden in derselben Klasse. Siehe [ADR-008](./ADR-008-svelte-5-runes.md) für Details.

**Warum kein Node-Daemon**:

Der MCP-Python-SDK (Anthropic-official) ist gleich-wertig zum Node-SDK. Das Bun-vs-Node-vs-stdio-Risiko des 12-Hub-Pfads (Polyglots Vorhersage: Bun's `process.stdin.resume()` in stdio-pipe-Mode hatte zuletzt subtile Issues) entfällt, weil wir die Python-Implementation nehmen, die diese Issues strukturell nicht hat.

**Wartbarkeit**:

- Eine Sprache pro Layer (Python für Backend, TS für Frontend) = klares Mental-Modell.
- Tests: pytest + Hypothesis + mutmut (Backend), Vitest + fast-check + Stryker.js (Frontend).
- Codegen-Drift wird strukturell durch [ADR-010](./ADR-010-codegen-pipeline.md) gefangen, nicht durch Hand-Maintenance.

---

## Related ADRs

- [ADR-004 Pydantic 2.13 SSoT](./ADR-004-pydantic-2-13-ssot.md) — der Schema-SSoT, der die Python-Backend-Wahl strukturell rechtfertigt.
- [ADR-008 Svelte 5 Runes](./ADR-008-svelte-5-runes.md) — die Frontend-Framework-Wahl.
- [ADR-010 Codegen-Pipeline](./ADR-010-codegen-pipeline.md) — die Pydantic → Zod-Brücke, die das Single-SSoT durchsetzt.
- [ADR-011 anyio Concurrency](./ADR-011-anyio-concurrency.md) — die Concurrency-Bedingungen, unter denen Python-Backend tragfähig ist.

---

## Update 2026-05-17 — Adoptierte Foundation-Libs

Konkrete Adoptionen seit dem Charter-Stand:

- **Backend-Wire-Transport**: `py-wire-rpc` (Python 3.13, anyio 4.13+, websockets 16+, jsonrpcserver 5+, Pydantic-validiert via `@pydantic_method`). Konsum via git-link.
- **Frontend-Wire-Transport**: `ts-wire-rpc` (TypeScript, Bun, `reconnecting-websocket@4.4.0` + `json-rpc-2.0@1.7.1` + Svelte-5-Runes-Bridge). Konsum via git-link.
- **Codegen**: `pydantic-zod-codegen` (Pydantic v2.13 → JSON-Schema 2020-12 → Zod v4, FastUI-hybrid pattern, CI drift-gate).

Build-Tool-Konsequenz aus dem Stack-Tisch (Backend Python via `uv tool install frontprompt`, Frontend Bun) bleibt unverändert. Bun bleibt FE-only — die Wire-Lib `ts-wire-rpc` ist source-only ESM, kein bundling-step nötig vor consumption durch das frontprompt-Frontend.
