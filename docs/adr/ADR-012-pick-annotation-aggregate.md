# ADR-012 — Pick und Annotation als Entities im PointingSession-Aggregate (kein BC-Straddle)

> Part of the frontprompt [Architecture Decision Records](./index.md).

**Status**: accepted with amendment (2026-05-18: Phase-1-Implementation drastisch simpler)
**Date**: 2026-05-17
**Amendment-Date**: 2026-05-18
**Cross-References**: [ADR-001 Two BCs](./ADR-001-two-bounded-contexts.md), [ADR-002 Single-Writer Helland](./ADR-002-single-writer-helland.md), [ADR-005 Nursery-per-PageSession](./ADR-005-nursery-per-pagesession.md), [ADR-006 Daemon Wall-Clock](./ADR-006-daemon-wall-clock.md), [ADR-007 Failure-Mode-Budget](./ADR-007-failure-mode-budget.md), overview.md §10.1 (resolved), [ADR-015 Overlay in Page Main World](./ADR-015-overlay-in-page-main-world.md), 2026-05-18 Architecture Reset

---

## Context

Der Konsortiums-Hub identifizierte im consortium-of-brain-verdict §"Pick + Annotation Aggregate-Konflikt" (historische atlas-Recherche, nicht extrahiert), dass die Aggregat-Granularität für die Interactive-Surface-Entities `Pick` und `Annotation` ungeklärt geblieben ist. Zwei Sub-Fragen wurden offen markiert (overview.md §10.1):

1. **Pick-Aggregate-Status** — ist `Pick` ein eigenständiges Aggregate mit eigener Konsistenz-Grenze, eigenem Single-Writer und eigenen Invarianten? Oder ist `Pick` eine Entity innerhalb der `PointingSession`?
2. **Annotation-BC-Boundary** — lebt `Annotation` rein in der Interactive Surface BC? Oder straddelt sie in die Programmatic Executor BC, weil eine Annotation auf eine `InteractionFlow`-Step oder einen DOM-Snapshot referenzieren kann, deren Eigentümer die Programmatic-Seite ist?

Die Frage ist hart, weil zwei orthogonale Disziplinen kollidieren. Vernon (Implementing Domain-Driven Design) sagt: ein Aggregate ist eine **Konsistenz-Grenze**, keine Query-Grenze; und cross-Aggregate-Referenzen werden über **Identifier**, nicht über direkte Objekt-Verbindungen geführt — und cross-BC ist die schärfste Form dieser Grenze. Helland (Life beyond Distributed Transactions) sagt: jedes Aggregate hat **genau einen Writer**, Cross-Aggregate-Coordination ist Typed-Message-only. Die Two-BC-Axiom-Disziplin aus [ADR-001](./ADR-001-two-bounded-contexts.md) sagt: **es gibt keinen Wire-Channel, der beide BCs spricht**; Cross-BC-Coordination passiert ausschließlich über die `IntentRequest`-Queue (`H-1`).

Wenn diese Frage unentschieden bleibt, sind drei konkrete Failure-Modes vorhersehbar: (a) der Owner-Scope für F-7 (Idempotency-Key-Replay mit World-State-Drift, siehe [ADR-006](./ADR-006-daemon-wall-clock.md) + [ADR-002 I4](./ADR-002-single-writer-helland.md)) wird unscharf — Picks erzeugen Idempotency-Keys aus dem Tab, deren Discriminator-Scope dann nicht eindeutig der `PointingSession` oder der `PageSession` zugeordnet werden kann; (b) das Svelte-5-Frontend braucht entweder einen Pfad zum `InteractionFlow`-Aggregate (was [ADR-001 Wire-Boundary](./ADR-001-two-bounded-contexts.md) bricht: *"Es gibt keinen Wire-Channel, der beide BCs spricht. Im Frontend bedeutet das: das Svelte-5-UI hat keinen Code-Pfad für Programmatic-Executor-Aggregate"*), oder es braucht eine bi-direktionale Sync zwischen `Annotation`- und `InteractionFlow`-Replicas (was eine 8. Failure-Klasse außerhalb des geschlossenen [ADR-007-Budgets](./ADR-007-failure-mode-budget.md) öffnet); (c) der Nursery-Eigentums-Baum aus [ADR-005](./ADR-005-nursery-per-pagesession.md) bekommt einen unklaren Eintrag, weil `Pick` weder eindeutig zur `PointingSession`-Nursery noch eindeutig zu einer eigenen Nursery gehört.

---

## Decision

**Pick ist eine Entity innerhalb des `PointingSession`-Aggregates. Annotation ist eine Entity innerhalb des `PointingSession`-Aggregates. Beide leben strukturell und ausschließlich in der Interactive Surface BC. Cross-BC-Referenzen auf Programmatic-Executor-Daten sind dehydrierte Identifier, validiert durch einen Anti-Corruption-Layer (ACL) innerhalb der Interactive Surface BC zum Construction-Zeitpunkt.**

Konkret: das `PointingSession`-Aggregate ist die Konsistenz-Grenze. Es besitzt einen Lifecycle (`open` → `closed`) und enthält eine geordnete Collection von `Pick`-Entities sowie eine Collection von `Annotation`-Entities. Beide Entities tragen eine eigene ULID-Identity (sie sind global referenzierbar im Audit-Log und über die Wire-API), aber ihre Konsistenz-Invarianten werden ausschließlich gegen den `PointingSession`-State validiert. Es gibt **keinen** Schreib-Pfad, der einen `Pick` oder eine `Annotation` ohne den Single-Writer-Slot der zugehörigen `PointingSession`-Nursery mutiert.

### Invarianten, die Pick zur Entity (nicht zum Aggregate) machen

- I-PA-1: `Pick.session_id` muss auf eine im selben Daemon-Process **offene** `PointingSession` zeigen (Lifecycle-Status `open`). Diese Invariante zwingt die Konsistenz-Grenze über die Session, nicht über den einzelnen Pick.
- I-PA-2: `Pick.created_at_monotonic_ns` muss `>= PointingSession.opened_at_monotonic_ns` und `< PointingSession.closed_at_monotonic_ns` (sofern gesetzt) liegen. Die Ordering-Quelle ist der per-PointingSession monotonic-clock-Tick analog zu [ADR-002 I4](./ADR-002-single-writer-helland.md) für den `last_navigation_lsn` der `PageSession`.
- I-PA-3: `PointingSession.picks` ist eine append-only Collection; die `pick_lsn` ist per-Session monoton und vom Single-Writer dieser Session geführt.

Diese drei Invarianten lassen sich **nicht** ohne `PointingSession`-State validieren — das ist die formale Helland-Definition: wenn die Invarianten eines Kandidaten-Aggregates fremden State konsultieren müssen, ist es kein Aggregate, sondern eine Entity im konsultierten Aggregate.

### Dehydrierte Identifier-Felder auf Annotation

`Annotation` darf folgende **optionale** Felder tragen, die auf Programmatic-Executor-Daten verweisen:

- `page_session_id: PageSessionId | None` — auf welcher `PageSession` der Anker-`Selector` aufgenommen wurde.
- `interaction_flow_step_id: InteractionFlowStepId | None` — Schritt-Identität, wenn die Annotation während eines aktiven Capture-Vorgangs entstand.
- `dom_snapshot_hash: DomFingerprint | None` — strukturelle Fingerprint des DOMs zum Pick-Zeitpunkt (gleiche Funktion wie der `dom_structural_fingerprint`-Term im World-State-Hash aus [ADR-002 I4](./ADR-002-single-writer-helland.md)).

Alle drei Felder sind **Identifier**, keine Objekt-Referenzen. Vernon-Regel: cross-Aggregate (und erst recht cross-BC) wird über Identity geführt, nicht über Object-Pointer.

### ACL-Platzierung — `ProgrammaticReferenceValidator`

An der Konstruktion einer `Annotation` (Receive an HTTP-POST in der Interactive Surface BC) prüft ein `ProgrammaticReferenceValidator` — ein ACL-Adapter, der **innerhalb** der Interactive Surface BC lebt — die optionalen Identifier durch **read-only Queries** gegen die Programmatic-Seite. Die Queries gehen über die `IntentRequest`-Queue (`H-1`, [ADR-001](./ADR-001-two-bounded-contexts.md)) als typed Read-Messages: `QueryPageSessionExists(PageSessionId) → bool`, `QueryInteractionFlowStepValid(InteractionFlowStepId) → bool`.

Drei strukturelle Eigenschaften des ACLs:

1. **Read-only**: keine Mutation kreuzt die BC-Grenze. Validierung ist Lookup-only.
2. **Synchron-zur-Construction**: die `Annotation` ist nicht persistiert, bevor der ACL die Validierung quittiert hat. Bei `False`-Antwort: HTTP 400 mit klarem Reason; bei Timeout: HTTP 503 mit Idempotency-Key-erhaltend (Replay nach Erholung der Queue ist sicher dank [ADR-006](./ADR-006-daemon-wall-clock.md)).
3. **Eigentum bleibt in der Interactive Surface BC**: die `Annotation` selbst wird vom Single-Writer der `PointingSession`-Nursery geschrieben; der ACL ist nur ein Validierungs-Hop im Receive-Pfad, kein zweiter Writer.

### F-7-Discriminator-Scope (Idempotency-Key-Replay)

`Pick`-Creation und `Annotation`-Creation sind klassische mutierende HTTP-POSTs vom Tab zum Daemon und tragen daher Idempotency-Keys ([ADR-006](./ADR-006-daemon-wall-clock.md)). Der **Discriminator-Scope** des Keys ist `(PointingSessionId, IdempotencyKey)` — also pro `PointingSession`-Aggregate. Das ist der natürliche Owner-Scope, weil F-7's World-State-Drift-Check auf den per-Aggregate-monoton geführten `pick_lsn` bzw. `annotation_lsn` Bezug nimmt, und der Single-Writer der `PointingSession`-Nursery deterministisch entscheiden kann, ob ein Replay den State drifted hat oder nicht. Wäre `Pick` ein eigenständiges Aggregate, müsste der Discriminator-Scope `(PickId, IdempotencyKey)` sein — und der Drift-Check müsste über zwei Aggregate koordinieren, was per [ADR-002 I2](./ADR-002-single-writer-helland.md) (Cross-Aggregate-Coordination ist Typed-Message-only) eine zusätzliche Queue-Roundtrip im Hot-Path verlangen würde.

---

## Consequences

**Positive**:

- **Single-Writer-pro-Aggregate (I1) bleibt strukturell sauber**: ein einziger Writer (`PointingSession`-Nursery) für die gesamte Picks/Annotations-Kollektion. Kein zweiter Writer entsteht durch die Pick-oder-Annotation-Diskussion.
- **Wire-Boundary aus [ADR-001](./ADR-001-two-bounded-contexts.md) bleibt sauber**: das Svelte-5-Frontend bekommt **keinen** Code-Pfad zu Programmatic-Executor-Aggregaten. Die Annotation-Felder, die auf `PageSession`/`InteractionFlow` verweisen, sind nur Identifier-Strings — das Frontend kennt sie als opake `PageSessionId`/`InteractionFlowStepId`, nicht als Replicas.
- **F-7-Owner-Scope ist eindeutig** (`PointingSession`). Replay-Schutz ist im selben Single-Writer-Slot wie die Mutation. Keine Cross-Aggregate-Koordination im Hot-Path.
- **Nursery-Eigentums-Baum aus [ADR-005](./ADR-005-nursery-per-pagesession.md) erweitert sich kanonisch**: `PointingSession`-Nursery besitzt zusätzlich zu PointingSession-State auch die Picks- und Annotations-Collection. Symmetrisch zum `PageSession`-Nursery-Pattern.
- **Crash-Recovery [ADR-002 I6](./ADR-002-single-writer-helland.md) bleibt einfach**: eine `in_progress` `PointingSession` wird beim Boot auf `aborted` gesetzt; ihre Picks/Annotations sind durch Lifecycle-Status des Eltern-Aggregates implizit ungültig markiert.
- **Failure-Mode-Budget [ADR-007](./ADR-007-failure-mode-budget.md) bleibt geschlossen bei 7 Klassen**: keine neue Failure-Klasse für bi-direktionale Replication-Sync zwischen BCs.

**Negative / Trade-offs**:

- Die ACL-Validation für die optionalen Programmatic-Identifier kostet einen `IntentRequest`-Queue-Roundtrip pro Annotation-Creation, die diese Felder gesetzt hat. Das ist im UI-Flow tolerabel (Annotation wird selten mit der Frequenz von DOM-Mutationen erstellt). Bei Queue-Backpressure oder Programmatic-BC-Stillstand schlägt die Annotation-Creation mit HTTP 503 fehl — bewusst gewählt gegenüber "Annotation persistieren ohne Validierung" (würde F-1-Schema-Drift-analoge Inkonsistenz erzeugen: Annotation referenziert Phantom-PageSession).
- Picks und Annotations sind im Daemon-Audit-Log global per-ULID identifizierbar, aber **nur** im Kontext ihrer Eltern-`PointingSession` lebenswichtig adressierbar. URL-Schemas der internen API tragen folglich beide IDs: `/pointing_sessions/{psid}/picks/{pid}`. Wer eine Pick-ID ohne Session-Context bekommt, kann sie zwar nachschlagen (Single-Index), aber nicht mutieren ohne den Lifecycle-Status der Session zu konsultieren.
- Die Wire-Repräsentation von `Annotation` zeigt nun explizit optionale Identifier-Felder mit der Semantik *"validiert zur Construction-Zeit, danach ist die referenzierte Entität in der Programmatic BC der Truth"*. Konsumenten dürfen daraus **nicht** ableiten, dass die referenzierte Entität noch existiert — Garbage-Collection einer `PageSession` invalidiert die `Annotation`-Referenz nicht (Annotation lebt weiter, der Identifier wird zum historischen Lookup-Schlüssel im Audit-Log).

---

## Alternativen erwogen

### Alt 1 — Pick als eigenständiges Aggregate mit eigener Konsistenz-Grenze

**Pro**: einfachere lokale Invarianten (`Pick` validiert nur sich selbst: CSS-Selector valid, score non-empty, timestamp gesetzt); kleinere Aggregates folgen der Vernon-Empfehlung *"prefer small aggregates"*.

**Con**: die strukturellen Invarianten von `Pick` sind nicht selbst-genügsam — *"Pick muss zu einer offenen Session gehören"* und *"Pick.timestamp >= session.startedAt"* konsultieren `PointingSession`-State und sind damit per Helland-Definition keine Aggregate-Invarianten, sondern Cross-Aggregate-Invarianten. Cross-Aggregate-Invarianten sind in Hellands Modell explizit verboten. Eine Two-Aggregate-Lösung würde diese Invarianten in einen Synchronisations-Pfad zwischen `Pick` und `PointingSession` über die Typed-Message-Queue verschieben — was im Hot-Path eines UI-Click-Events einen unbegründeten Roundtrip wäre, **und** F-7's Discriminator-Scope auf `(PickId, IdempotencyKey)` schrumpfen würde, was den Drift-Check zwingt, gegen zwei Aggregate gleichzeitig zu prüfen. **Ruled out** weil die Invarianten-Topologie die kleinere Aggregate-Wahl nicht trägt.

### Alt 2 — Annotation straddelt die BC-Grenze (Replikate in beiden BCs)

**Pro**: *"Annotationen auf InteractionFlow-Steps"* würde sich als first-class-Konzept anfühlen; Programmatic-Executor-Konsumenten könnten Annotations als Index zu Replay-Steps verwenden, ohne die Interactive Surface BC anzufragen.

**Con**: Verstößt direkt gegen die Two-BC-Axiom-Regel aus [ADR-001](./ADR-001-two-bounded-contexts.md) (*"Es gibt keinen Wire-Channel, der beide BCs spricht"*). Verlangt bi-direktionale Sync zwischen den Replicas; Sync-Latency, Sync-Konflikt-Resolution und Sync-Crash-Recovery sind alle drei strukturelle Defekte, die das geschlossene [ADR-007-Budget](./ADR-007-failure-mode-budget.md) (7 Klassen, keine 8.) sprengen würden. Hellands Single-Writer-Disziplin wäre durch die Notwendigkeit zweier kollaborierender Writer (einer pro BC-Side der Replication) gebrochen. **Ruled out** weil sie eine 8. Failure-Klasse für Replication-Drift erzwingt und gleichzeitig die Wire-Boundary-Axiom-Garantie aushöhlt.

---

## Related ADRs

- [ADR-001 Two Bounded Contexts](./ADR-001-two-bounded-contexts.md) — wire-boundary rule und Two-BC-Axiom, die diese ADR konkretisiert auf die Pick/Annotation-Granularität.
- [ADR-002 Single-Writer Helland](./ADR-002-single-writer-helland.md) — Invarianten I1, I2, I4, I6, die diese ADR auf das `PointingSession`-Aggregate anwendet (Pick/Annotation als Entities innerhalb des Single-Writer-Slots).
- [ADR-005 Nursery-per-PageSession](./ADR-005-nursery-per-pagesession.md) — symmetrisches Ownership-Pattern; `PointingSession`-Nursery besitzt analog Picks und Annotations.
- [ADR-006 Daemon-Wall-Clock](./ADR-006-daemon-wall-clock.md) — Idempotency-Key-Cache-TTL und `monotonic_ns()`-Truth für die per-Session-LSN-Felder `pick_lsn` und `annotation_lsn`.
- [ADR-007 Failure-Mode-Budget](./ADR-007-failure-mode-budget.md) — F-7-Owner-Scope ist nach dieser ADR eindeutig die `PointingSession`; das Budget bleibt geschlossen bei 7 Klassen.

---

## Amendment 2026-05-18 — Phase-1-Implementation drastisch simpler

Diese ADR bleibt **konzeptionell gültig** (Pick + Annotation als Entities im PointingSession-Aggregate, keine cross-BC-Replikation), aber die Phase-1-Implementation wird drastisch reduziert. Vollständige Begründung in der Architecture-Reset-Decision 2026-05-18. Konkret:

### Was Phase 1 NICHT implementiert

- **Keine SQLite-Persistierung**: Picks landen in-memory in einer Liste auf dem Daemon und werden via structlog geloggt. Bei Daemon-Restart sind sie weg. Akzeptiert — Phase 1 ist explorativer Tool-Use, kein Long-Term-Recording.
- **Keine PointingSession-Lifecycle-Aggregate-Mechanik**: kein `open` → `closed`-Übergang, kein `PointingSession`-Nursery, kein Single-Writer-Slot. Eine implizite "current PointingSession" pro `PageSession` reicht.
- **Keine ACL-Validation für `page_session_id`-Referenzen**: weil Phase 1 keine cross-BC-Referenzen erzeugt — der Pick existiert immer im Kontext der aktiven PageSession (eine pro Daemon).
- **Kein `ProgrammaticReferenceValidator`**: das ACL-Modul wird in Phase 1 nicht gebraucht. Es bleibt im Code (Stub aus `daemon-skeleton`-Bundle) für Phase 2+ Reaktivierung.
- **Keine F-7-Idempotency-Key-World-State-Drift-Logik**: wenn der User doppelklickt, ist das ein Doppel-Pick. Akzeptiert für Phase 1.
- **Kein `IdempotencyReplayCache` auf dem HTTP-Endpoint**: der `wire-protocol` SP03 `IdempotencyReplayCache` wird in Phase 1 nicht aktiviert. POST `/picks` ist fire-and-write-and-forget.

### Was Phase 1 implementiert

- **In-memory Pick-Liste** auf dem Daemon, scoped per `PageSession`
- **structlog-Output** beim Pick-Receive (`logger.info("pick_received", selector=..., page_session_id=..., timestamp=...)`)
- **HTTP POST `/picks`-Endpoint** auf dem Daemon: nimmt `{selector, page_session_id, timestamp}` an, antwortet `202 Accepted`, fertig
- **Pick-Mode-UI** im Overlay (TypeScript, SvelteKit-Bundle, siehe [ADR-015](./ADR-015-overlay-in-page-main-world.md)): `document.elementFromPoint` + Hover-Highlight + Click-Capture + Selector-Optimizer-Logik (aus Legacy portiert)

### Re-Aktivierung in Phase 2+

Wenn in Phase 2+ ein echter Bedarf entsteht (Annotation referenziert InteractionFlow-Step, persistent Pick-Storage über Daemon-Restart hinweg, oder Multi-User-Concurrency), werden die hier deferred-Komponenten ohne Re-Design wieder aktiviert:

- `PointingSession`-Aggregat-Lifecycle mit Nursery (aus `daemon-skeleton` SP03 als leeres Aggregate vorhanden)
- SQLite-Persistierung via `aiosqlite` (geplant in ursprünglicher §Decision, in Phase 1 nicht angefasst)
- `ProgrammaticReferenceValidator`-ACL für cross-BC-Identifier-Validation
- F-7-Idempotency-Key-World-State-Hash gemäß ADR-006/ADR-007

Diese ADR (`ADR-012`) bleibt in dem Moment der Referenzpunkt für die volle Domain-Topologie.

### Folge für die Wire-Repräsentation

Das `wire-protocol` SP01 hat `PickRequested` als `MutationEnvelope`-Variant definiert mit Feldern `selector`, `page_session_id`, `pointing_session_id`. In Phase 1:

- `pointing_session_id` bleibt im Schema (optional), wird vom Overlay aber **nicht gesetzt** — der Daemon behandelt einen Pick ohne `pointing_session_id` als "default current pointing session for this page_session"
- `IdempotencyKey`-Header wird vom Overlay-Client nicht generiert, vom Daemon nicht geprüft

Das Schema bleibt forward-compatible für Phase 2+ — die Overlay-Clients können später den `pointing_session_id` setzen, Daemon kann später den Idempotency-Key prüfen, ohne Wire-Breaking-Change.
