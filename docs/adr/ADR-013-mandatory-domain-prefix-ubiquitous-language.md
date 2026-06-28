# ADR-013 — Mandatory Domain-Prefix für ambiguose Begriffe (Ubiquitous Language Addendum)

> Part of the frontprompt [Architecture Decision Records](./index.md).

## Status

accepted

## Context

Die Ubiquitous Language des frontprompt-Successors hat mehrere strukturell überladene Begriffe, die ohne Disambiguierungs-Prefix zu Bug-induzierender Verwirrung führen — sowohl in Code (Pydantic-Field-Namen, Variable-Namen, Parameter-Namen) als auch in Dokumentation (Plan-Bundles, ADRs, Code-Comments) und in synchroner Mensch↔Agent-Kommunikation.

Konkrete Verwechslungsfälle, die in den ersten 4 Sub-Plans des `frontprompt-daemon-skeleton`-Bundles aufgetreten sind oder die ohne ADR-013 aufgetreten wären:

- **"session"** existiert mit MINDESTENS fünf orthogonalen Bedeutungen:
  - `PageSession` — Programmatic Executor BC Aggregate (ADR-012): ein offener Browser-Tab-State mit URL, DOM, history
  - `PointingSession` — Interactive Surface BC Aggregate (ADR-012): ein Mensch-Annotations-Vorgang
  - MCP `ClientSession` — Connection-State der MCP-SDK
  - Scrapling Session — `DynamicSession`, `StealthySession`, `FetcherSession` (drei verschiedene Browser-Substrate-Lifecycles)
  - Chromium "Session" — Browser-Process-Lifetime mit user_data_dir
- **"domain"** existiert mit drei Bedeutungen:
  - DNS-Domain (google.com vs amazon.com vs nowsecure.nl) — relevant z.B. für TR-001 user_data_dir-Pfade und Cloudflare-cf-clearance-Caching
  - DDD-Bounded-Context — Programmatic Executor BC vs Interactive Surface BC
  - Business-Domain — Browser-Automation als kommerzieller Bereich
- **"context"** existiert mit drei Bedeutungen:
  - DDD Bounded Context (BC)
  - anyio CancelScope-Context
  - Python Runtime-Context (z.B. async-Context)
- **"id"** allein ist nie sinnvoll — `id` muss `<thing>_id` sein
- **"clock"** ist heute eindeutig (es gibt nur `DaemonClock`), aber wird verwirrend sobald jemand `time.monotonic()` mit `Daemon`-Clock vermengt

Konkrete Manifestation in dieser Session: Im Plan-Bundle `frontprompt-daemon-skeleton` schrieb der Orchestrator "per-(domain, session-id) directory" für die TR-001-Mitigation — und der User musste explizit nachfragen, ob "domain" DNS-Domain oder DDD-Domain meint und ob "session-id" PageSessionId oder MCP-Session-ID meint. Das ist Bug-induzierende Ambiguität in einem Dokument das explizit für Implementation-Briefings genutzt wird.

Diese ADR ergänzt die Ubiquitous Language des Greenfield-Charters um eine Disziplin: **jeder Begriff der in mehr als einem Bounded Context, mehr als einer Schicht, oder mehr als einer Concern vorkommt, MUSS ein qualifizierendes Prefix tragen.**

## Decision

**Mandatory Domain-Prefix für ambiguose Begriffe**: jedes Substantiv, das ohne Prefix in der frontprompt-Ubiquitous-Language mehr als eine konsistente Bedeutung haben kann, MUSS in Code, Dokumentation und synchroner Kommunikation mit einem disambiguierenden Prefix verwendet werden.

### Konkrete Substantiv-Prefix-Regeln

| Bare Term | Erlaubte qualifizierte Form | Bedeutung |
|-----------|------------------------------|-----------|
| `session` | `page_session` / `PageSession` | Programmatic Executor BC Aggregate ([ADR-012](./ADR-012-pick-annotation-aggregate.md)) |
| `session` | `pointing_session` / `PointingSession` | Interactive Surface BC Aggregate (ADR-012) |
| `session` | `mcp_session` | MCP SDK `ClientSession`-Connection |
| `session` | `scrapling_session` | Scrapling-Substrate-Session (DynamicSession / StealthySession / FetcherSession) |
| `session` | `browser_session` | Chromium-Process-Lifetime (das was Chromium intern als "session" sieht) |
| `domain` | `dns_domain` | DNS-Hostname (z.B. `google.com`, `nowsecure.nl`) |
| `domain` | `bc_domain` | DDD Bounded Context (Programmatic Executor BC / Interactive Surface BC) |
| `domain` | `business_domain` | Kommerzieller Bereich (Browser-Automation) — selten verwendet, expliziter |
| `context` | `bc_context` | DDD Bounded Context (Synonym zu `bc_domain` aus Helland-Sicht) |
| `context` | `cancel_context` | anyio `CancelScope` |
| `context` | `runtime_context` | Python async-Context (`asyncio.current_task`, `contextvars`) |
| `id` | `<thing>_id` | nie bare `id` als Field-Name; immer mit Owner-Substantiv (`page_session_id`, `pick_id`, `annotation_id`, `daemon_id`, ...) |
| `clock` | `daemon_clock` | DaemonClock (ADR-006) — auch wenn aktuell eindeutig, immer expliziter Prefix |
| `queue` | `intent_request_queue` | Die Bounded MemoryObjectStream zwischen den BCs (ADR-001) |
| `task` | `bc_task` / `aggregate_task` / `daemon_task` | anyio TaskGroup-Tasks pro Ownership-Layer |

Die Liste ist nicht erschöpfend — neue Disambiguierungen kommen via Pull-Request gegen diese ADR. Wenn ein neuer Begriff in zwei Pull-Requests parallel auf zwei Bedeutungen prallt, wird er rückwirkend qualifiziert (alle Vorkommen migrieren).

### Wann gilt die Regel NICHT (Ausnahmen)

Die Regel greift ausschließlich für ambiguose Begriffe. Begriffe, die strukturell eindeutig sind, bleiben unqualifiziert:

- `pick`, `annotation` — eindeutig im Interactive Surface BC (per ADR-012). Bare okay.
- `interaction_flow` — eindeutig (Programmatic Executor BC Aggregate-Type). Bare okay.
- `nursery` — eindeutig (anyio TaskGroup-Synonym). Bare okay.
- `protocol` als Python `typing.Protocol` — okay, Python-Konvention. Wenn Verwechslungsgefahr mit "wire protocol", explizit `python_protocol` vs `wire_protocol`.

### Anwendungsbereich

Die Regel gilt für:

1. **Pydantic-Field-Namen** in allen `BaseModel`-Klassen
2. **`typing.NewType`-Wrapper** für ID-Types (`src/frontprompt/types.py`)
3. **Funktions-Parameter** in jeder Daemon-API
4. **Variable-Namen** in Code (auch lokale)
5. **ADR-Prosa, Plan-Bundle-Prosa, Backlog-Items** — alle synchron geschriebenen Dokumente
6. **Synchron-Kommunikation** zwischen Mensch und AI-Agent (z.B. dieser User-Direktive 2026-05-18, die diese ADR triggerte)
7. **Code-Comments + Docstrings**
8. **MCP-Tool-Parameter** (User-facing API muss disambiguiert sein)

Die Regel gilt NICHT für:

- Externe APIs, die wir konsumieren (z.B. die `mcp` SDK's eigenes `session` ist deren Naming-Choice)
- Lokale Variablen in 3-Zeilen-Closures wo Kontext offensichtlich ist (z.B. `for s in sessions:`)

### Enforcement

- **Heute (2026-05-18)**: konventions-basiert, in Code-Reviews durchgesetzt
- **Future-Möglichkeit**: AST-Test analog zu `tests/test_adr002_ast.py` (ADR-002+ADR-011-AST-scan), der Pydantic-Field-Namen gegen die Erlaubt-Liste prüft. YAGNI bis erste Verletzung im Code auftritt.

## Consequences

### Positive Konsequenzen

- **Eindeutige Implementation-Briefings**: Plan-Bundle-Texte, ADRs, Backlog-Items sind ohne Rückfrage interpretierbar — der Orchestrator-Agent muss nicht mehr raten was "session-id" meint
- **Cross-BC-Refactor-Sicherheit**: wenn `page_session_id` umbenannt wird, ist der grep eindeutig — keine Kollision mit `pointing_session_id` oder `mcp_session_id`
- **Pydantic-Drift-Resilienz**: Codegen (`pydantic-zod-codegen`) produziert eindeutige Zod-Schemas — Frontend kann nicht versehentlich `Pick.session_id` als `PageSessionId` interpretieren wenn es eigentlich `PointingSessionId` ist
- **Compliance mit Evans-DDD-Disziplin**: Vernon's *"Implementing Domain-Driven Design"* §"Ubiquitous Language" macht genau diese Disambiguierung zur Kern-Praxis

### Negative Konsequenzen

- **Mehr Tipparbeit**: `page_session_id` ist 15 Zeichen statt `id`. In Hot-Code-Paths mit vielen Aggregate-Referenzen wird Code länger.
- **Bestehender Code muss migriert werden**: SP01-SP04 vom `frontprompt-daemon-skeleton`-Bundle (gerade gelandet) haben die Konvention überwiegend erfüllt (in SP03 sind `_owner_task_id`, `page_session_id` etc. korrekt prefixed). Aber: Plan-Bundle-Prosa von noch nicht executed Bundles (`frontprompt-scrapling-adapter`, `frontprompt-wire-protocol`, `frontprompt-frontend-skeleton`, `frontprompt-mcp-tools`, `frontprompt-annotation-ui`, `frontprompt-failure-mode-hooks`) muss vor Execute auf Konvention geprüft werden.
- **Lern-Kurve**: neue Contributors müssen die Liste lernen — wird Teil des `CLAUDE.md`-Onboarding.

### Migrations-Pflicht

Vor dem Execute jedes folgenden Bundles (`frontprompt-scrapling-adapter` ff.) muss der Plan-Workflow-Reviewer prüfen ob ambiguose Begriffe ohne Prefix verwendet werden. Konkrete Verstoß-Stellen aus der heute aufgetretenen User-Direktive (TR-001-Klarstellung 2026-05-18) sind als Fix-Anker zu nehmen.

Backlog-Items + ADRs vor 2026-05-18 sind grandfathered (bleiben wie geschrieben). Aber: neue Edits an alten Dokumenten ziehen die Konvention nach.

## Alternativen erwogen

### Alt 1: Implicit Context durch Modul-Namespacing (ruled out)

Idee: `frontprompt.bc.programmatic_executor.aggregates.page_session.PageSession.id` ist eindeutig durch den Import-Pfad. Verwende bare `id` als Field-Name.

Pro: weniger Tipparbeit.
Con: in Cross-BC-Code (z.B. `Annotation.page_session_id` referenziert ein Aggregate des anderen BC) ist die Disambiguierung über Modul-Path nicht möglich. Außerdem: in Dokumentation und Mensch↔Agent-Kommunikation existiert kein Modul-Path-Kontext.

Ruled out — die Disambiguierungs-Lücke ist genau dort wo die Bug-induzierende Verwirrung auftritt.

### Alt 2: `typing.NewType`-allein reicht (ruled out)

Idee: `PageSessionId = NewType('PageSessionId', str)` macht den Type-Annotation-Pfad eindeutig — Variable-Name `id` bleibt erlaubt.

Pro: Pydantic + mypy kümmern sich um die Disambiguierung.
Con: in Plan-Bundle-Prosa, ADR-Texten, Mensch↔Agent-Kommunikation gibt es keine Type-Annotations — die Disambiguierung fehlt genau dort wo sie am dringendsten gebraucht wird. Und mypy-strict warnt nicht wenn jemand `id: PageSessionId = pointing_session.id` schreibt (das `.id`-Attribut ist auf beiden Aggregaten vorhanden) — der NewType-Compile-Check rettet nur den initialen Wert, nicht die Zugriff-Site.

Ruled out — löst nur einen Teil des Problems.

### Alt 3: ESLint/Ruff-Regel statt ADR (ruled out — zu früh)

Idee: AST-Scanner der Field-Namen-Verstöße ablehnt.

Pro: hartes Enforcement.
Con: YAGNI bis erste Verletzung auftritt. AST-Scanner-Aufwand ist nicht trivial (man muss alle Pydantic-`BaseModel`-Subklassen finden + Field-Namen extrahieren + gegen Allow-List prüfen). Konventions-Disziplin reicht für jetzt — wenn sie 2x in Folge versagt, dann erst AST-Test.

Aufgeschoben, nicht abgelehnt.

## Related ADRs

- [ADR-001 Two Bounded Contexts](./ADR-001-two-bounded-contexts.md) — etabliert die zwei Bounded-Context-Boundaries, deren Disambiguierung diese ADR durchsetzt
- [ADR-002 Single-Writer Helland](./ADR-002-single-writer-helland.md) — Aggregate-Naming-Konvention die diese ADR ergänzt
- [ADR-012 Pick + Annotation Aggregate](./ADR-012-pick-annotation-aggregate.md) — definiert konkrete Aggregate-Namen die diese ADR als prefixed nutzt (`page_session_id`, `interaction_flow_step_id`, `dom_snapshot_hash` etc.)

## Trigger

User-Direktive 2026-05-18 in `frontprompt-daemon-skeleton`-Execute-Wrap-Up: nach der Klärung von TR-001's "domain"-Ambiguität ("welche Domain? google.com vs Amazon.com? oder DDD-domain?") und der "session-id"-Ambiguität ("welche Session? Browser, MCP, was?") schrieb der User wörtlich: *"Nimm das mit in die Ubiquitous Language. Schreib eine ADR, wo wir Präfixe fucking mandatory machen."*

Diese ADR ist die direkte Antwort. Verstöße werden ab sofort als Plan-Reviewer-Findings oder Plan-Challenger-Collisions geflaggt.
