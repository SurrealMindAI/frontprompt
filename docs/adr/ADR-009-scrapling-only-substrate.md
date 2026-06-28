# ADR-009 — Scrapling-only Browser-Substrate

> Part of the frontprompt [Architecture Decision Records](./index.md).

**Status**: accepted
**Date**: 2026-05-14
**Cross-References**: `../user-directive-corrections.md` Korrektur 1, `../../sources/scrapling-context7-snapshot.md`, `../failure-mode-budget.md` F-4, F-5, [ADR-005 Nursery-per-PageSession](./ADR-005-nursery-per-pagesession.md)

---

## Context

Das Konsortium (`../consortium-of-brain-verdict.md` §2.3 + §2.4 + §2.5, HISTORICAL) empfahl drei Browser-Substrate-Implementierungen als Co-Equal hinter einem `BrowserSubstrate`-Protocol: `PlaywrightSubstrate` (default), `UCSeleniumSubstrate` (Cloudflare Tier-3), `ScraplingStealthySubstrate` (One-Shot Pure-Scrape). Routing-Policy in der Application-Schicht, Substrate-Swap-als-First-Class-Operation als Konfiguration plus Hot-Reload.

User-Korrektur 1 (`../user-directive-corrections.md`) überschrieb diese Empfehlung: **ein** Substrate, **Scrapling**. Begründung im Korrektur-Dokument festgehalten:

- Scrapling sitzt drunter auf Playwright (`DynamicFetcher` / `StealthyFetcher` nutzen Playwright + Chromium + CDP-Patches + Canvas-Noise) und auf curl-cffi (`Fetcher` / `AsyncFetcher`). Playwright-Funktionalität kommt durch Scrapling, ohne ein zweites Substrate.
- Three-substrates-with-protocol ist Premature-Generalization, ohne dass je gemessen wurde, dass die Bypass-Rate strukturell unzureichend wäre.
- UC-Selenium-Eskalation bleibt **Reserve** für F-4 (Substrate-Detection-Failure), nicht Front-Door-Substrate.

Scrapling-API-Snapshot in `../../sources/scrapling-context7-snapshot.md`.

---

## Decision

Der Successor verwendet **Scrapling** als **einziges Browser-Substrate**, mit direktem API-Konsum. Drei Modi:

1. **`DynamicSession`** — Standard für Multi-Step-Sessions (Annotation, Replay, normale Browser-Navigation). Playwright-drunter, async, TaskGroup-kompatibel.

2. **`StealthySession`** — für Cloudflare- / Turnstile- / hCaptcha-Walls. Playwright-drunter mit CDP-Patches und Canvas-Noise, automatic-solver.

3. **`FetcherSession` / `AsyncFetcher`** — für Pure-HTTP-Operationen ohne Browser-Roundtrip (z.B. einfacher GET auf statische Pages, JSON-API-Endpoints, REST-Calls innerhalb eines Flows). curl-cffi-drunter, sehr schnell, kein Chromium-Cold-Start.

**Wichtig**: es gibt **kein eigenes `BrowserSubstrate`-Protocol** im Code. Scrapling-API ist der Substrate. Das spart eine Abstraction-Layer (Protocol + drei Implementierungen + Routing-Policy + Hot-Reload-Logik), die der Konsortiums-Entwurf vorgesehen hatte und die für den aktuellen Bedarf Premature-Generalization wäre.

**Substrate-Wahl pro Page Session**:

- Die `PageSession` wird mit einem `SubstrateMode`-Hint instanziiert (`dynamic`, `stealthy`, `fetcher`).
- Der Mode wird zur Spawn-Zeit gewählt; ein laufender PageSession kann den Mode nicht wechseln (das wäre ein neuer PageSession-Spawn).
- Default-Mode ist `dynamic`. Wer `stealthy` will, gibt es im Tool-Call-Parameter mit (`page_navigate(url, substrate_hint="stealthy")` oder ähnlich).

**UC-Selenium-Eskalation als zukünftiger Engineering-Task**:

Wenn F-4 (Substrate-Detection-Failure) empirisch greift — Scrapling-StealthySession-Bypass-Rate fällt unter 60% in einer Rolling-Window-Sampling-Strategie (`../failure-mode-budget.md` F-4) — wird ein Audit-Event `ROOT_CAUSE_BOT_DETECTION` emittiert und ein **Engineering-Backlog-Item** ausgelöst: "UC-Selenium als zweite Substrate-Variante evaluieren".

Das ist **explizit kein Hot-Path-Auto-Failover**. Der User soll wissen, wenn die Bypass-Rate kollabiert; UC-Selenium-Integration ist eine architektonische Entscheidung, kein Runtime-Fallback. Im Moment des Triggers wird ein neues ADR-Update geschrieben, das die Integration spezifiziert; UC-Selenium kommt erst rein, wenn diese ADR-Erweiterung committed ist.

---

## Consequences

**Match-Confidence-Telemetrie ist Pflicht**:

Scrapling's Adaptive Selectors sind strukturelles Matching auf (tag-name, attribute-set, sibling-position, parent-chain-shape). Sie überleben Klassen-Renames und Sibling-Insertion, überleben **keine** Parent-Chain-Restrukturierung. Failure-Mode den Scrapling's Doku verschweigt: **keine Match-Confidence-Telemetrie** — Silent-Drift möglich.

Wir bauen die Telemetrie **selbst** in die Replay-Engine ein:

- Jeder adaptive Re-Match emittiert ein Audit-Log-Event mit `confidence_score: float ∈ [0,1]`.
- Match-Confidence-Score < 0.85 triggert F-5 (Silent-Match-Drift): Replay wird mit `non_deterministic=true` markiert; manuelle Review-Pflicht im Annotation-UI.

Siehe `../failure-mode-budget.md` F-5 für volle Detection/Response-Spezifikation.

**Verifikations-Spike**:

PKR's IDK-Punkte (`../consortium-of-brain-verdict.md` §2.4 + §6, HISTORICAL) sind autoritativ **offen** und werden im overview.md §10 Offene Punkte als 2. Punkt geführt:

- Threadsafety unter geteiltem Browser-Pool.
- Empirische Bypass-Rate gegen aktuellen Cloudflare-Stand.
- GitHub-Issue-Closing-Latency des Scrapling-Projekts.
- Match-Confidence-Telemetrie-Lücke (oben adressiert durch Eigenbau).

Verifikations-Spike vor Implementations-Beginn.

**Bezug zu Failure-Mode-Budget**:

- **F-4 Substrate-Detection-Failure**: Engineering-Eskalations-Hook bei Bypass-Rate-Kollaps. UC-Selenium-Integration ist die strukturelle Antwort, nicht silent retry.
- **F-5 Silent-Match-Drift**: Match-Confidence-Score < 0.85 ist harter Cutoff. Eigene Telemetrie, weil Scrapling sie nicht liefert.

**Bezug zu Nursery-per-PageSession**:

Jede PageSession besitzt eine eigene Scrapling-Session-Instanz (`DynamicSession`, `StealthySession`, oder `AsyncFetcher`) in ihrer Nursery. Cross-Session-Browser-Pool ist **nicht** implementiert — jede PageSession hat ihren eigenen BrowserContext. Das eliminiert PKR's Threadsafety-IDK-Punkt strukturell: kein Sharing → keine Threadsafety-Frage.

**Was diese ADR NICHT macht**:

- Sie spezifiziert keinen `BrowserSubstrate`-Protocol-Code. Es ist Scrapling, direkt.
- Sie spezifiziert keinen UC-Selenium-Integration-Plan. Das ist zukünftiger Engineering-Task im F-4-Response-Pfad.
- Sie löst nicht die Multi-Tab-Soft-Cap-Frage ([ADR-011](./ADR-011-anyio-concurrency.md): 150-250 pro Daemon).

---

## Related ADRs

- [ADR-005 Nursery-per-PageSession](./ADR-005-nursery-per-pagesession.md) — Substrate-Instanz lebt in der PageSession-Nursery, ist Single-Owner.
- [ADR-007 Failure-Mode-Budget](./ADR-007-failure-mode-budget.md) — F-4 und F-5 hängen direkt an dieser ADR.
- [ADR-011 anyio Concurrency](./ADR-011-anyio-concurrency.md) — async-Scrapling-API über anyio TaskGroup.
