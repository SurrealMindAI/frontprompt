# ADR-015 — Overlay lebt in der Page (Main World, Playwright-injected)

> Part of the frontprompt [Architecture Decision Records](./index.md).

**Status**: accepted
**Date**: 2026-05-18
**Cross-References**: [ADR-001 Two Bounded Contexts §UI-Surface (revoked)](./ADR-001-two-bounded-contexts.md), [ADR-008 Svelte 5 Runes (amended)](./ADR-008-svelte-5-runes.md), [ADR-009 Scrapling-Only-Substrate](./ADR-009-scrapling-only-substrate.md), [ADR-012 Pick + Annotation (amended)](./ADR-012-pick-annotation-aggregate.md), 2026-05-18 Architecture Reset, chrome-extension-overlay-architecture

---

## Context

[ADR-001 §UI-Surface (original)](./ADR-001-two-bounded-contexts.md) hat festgelegt:

> "Annotation UI (Svelte 5, ext. Tab, 127.0.0.1:PORT — never inside the automated browser)"

Diese Decision war direkt downstream des frontprompt-legacy FAREWELL.md-Schmerzes:

> "Stop building UI inside the page. Treat the browser as a dumb executor and host all UI outside it."

Die Architecture-Reset 2026-05-18 §Root-Cause #1 hat herausgearbeitet, dass dieser Schmerz **mechanik-spezifisch** war (MV3-Extension mit MAIN ↔ ISOLATED ↔ ServiceWorker ↔ Python = 4 IPC-Layer), nicht prinzipiell. Mit Playwright/CDP-Inject sind die FAREWELL-Probleme strukturell vermieden:

- **Ein** Inject-Point (`page.add_init_script`)
- **Ein** Execution-Context (Main World)
- **Kein** Service Worker (kein 20-Sekunden-Keepalive nötig)
- **Keine** Bridge (kein doppelter `postMessage`-Hop)
- **Funktioniert über Cross-Origin-Navigations** (Playwright re-injectet automatisch)

Die "UI outside" Architektur hatte ihre eigenen Kosten:

- Zwei Browser-Instanzen (automated + UI-Tab)
- State-Discovery zwischen ihnen
- WebSocket-Channel Daemon → UI-Tab als Architektur-Constraint
- Bidirectional-Sync-Issues wenn User die UI-Tab schließt / URL ändert
- Zwei Builds (Overlay-in-Page + Mission-Control-SPA)

Mit der Wave-A-Investition haben wir den falschen Build gemacht (Mission-Control statt Overlay) und nichts erfahrbares produziert.

---

## Decision

**Das Overlay-UI lebt in der Main World der automated Page, injectiert via Playwright `page.add_init_script(content=overlay_iife)`. Single SvelteKit Static-SPA-Build, mit `vite-plugin-singlefile` zu einem einzigen IIFE-Bundle gebündelt. Mount in Shadow DOM für CSS-Isolation gegen die Host-Page.**

Konkret:

### Inject-Mechanik

`PageSession.navigate(url)` ruft vor der eigentlichen `page.goto(url)` einmalig:

```python
await self._scrapling_page.add_init_script(content=self._overlay_iife)
```

`page.add_init_script` ist Playwright-API; sie injectiert das Script **vor jedem Page-Script** in jeden neuen Document-Load — inklusive Iframe-Loads und Cross-Origin-Navigations. Das Script läuft **einmal pro Document**, vor `<script>`-Tags der Page.

Das Overlay-IIFE ist beim Daemon-Start in den Memory geladen (`importlib.resources` aus dem installed Package) und an alle `PageSession`-Instances weitergereicht.

### Build-Pipeline

- Quelle: `overlay/src/` mit SvelteKit + Svelte 5 Runes (TypeScript)
- Routing: SvelteKit-Routes erlaubt (User-Direktive: "wir wollen ja schon irgendwie Features von SvelteKit nutzen")
- Build-Output: `overlay/dist/` via `@sveltejs/adapter-static`
- Post-Build: `vite-plugin-singlefile` mergt `index.html` + alle Assets in eine einzige `overlay.iife.js`-Datei (oder das `index.html` mit inline-bundled JS — beide funktional äquivalent als IIFE-string)
- Distribution: das IIFE-Artefakt wird via `importlib.resources` ins Python-Package eingebettet (`src/frontprompt/_assets/overlay.iife.js`)

### Mount in Shadow DOM

Die IIFE-Bootstrap-Logik (handgeschriebenes TS, ~20 LoC) erstellt einen Shadow-Root:

```typescript
const host = document.createElement('div');
host.id = 'frontprompt-overlay-host';
document.documentElement.appendChild(host);
const shadow = host.attachShadow({mode: 'closed'});
mount(App, {target: shadow});
```

Closed-Shadow + dedizierter Host-Div verhindert CSS-Bleed in beide Richtungen. Die Host-Page kann das Overlay nicht via DOM-Query manipulieren (außer durch `MutationObserver` auf `documentElement`-Children, was wir akzeptieren).

### Page → Daemon-Kommunikation

Pure HTTP POST: das Overlay-IIFE kennt den Daemon-Port (wird via `add_init_script` mit-injected als globale Konstante: `window.__FRONTPROMPT_DAEMON_URL__`). Ein Pick wird via:

```typescript
fetch(`${window.__FRONTPROMPT_DAEMON_URL__}/picks`, {
  method: 'POST',
  headers: {'Content-Type': 'application/json'},
  body: JSON.stringify({selector, page_session_id, timestamp})
});
```

CORS: der Daemon antwortet mit `Access-Control-Allow-Origin: *` auf `/picks` und vergleichbare Overlay-Endpoints. Das ist akzeptabel weil der Daemon nur auf `127.0.0.1` lauscht und mit dem `Origin-Allowlist`-Middleware aus dem `wire-protocol`-Bundle den Origin auf `http://`/`https://`-Schemas + beliebige Host (= jede gescrapte Page) limitiert. **Keine** Authentifizierung in Phase 1 — der Daemon ist localhost-bound.

### Daemon → Page-Push (Phase 2)

In Phase 1 nicht benötigt. Wenn später nötig: WebSocket-Connection vom Overlay-IIFE zum Daemon auf `ws://127.0.0.1:7177/`. Schon im Code (WS-Server aus `wire-protocol` SP02), aber unbenutzt.

### Pick-Mode-Logik

In TypeScript, im Overlay-SvelteKit-Bundle:

- `document.elementFromPoint(x, y)` für Hover-Detection
- Hover-Highlight via CSS-overlay-`div` mit `pointer-events: none` (verhindert dass Overlay selbst geklickt wird)
- Click-Capture mit `e.preventDefault() + e.stopPropagation()`
- Selector-Optimizer-Logik **aus dem Legacy portiert** (`frontprompt-legacy/overlay/src/services/selector-optimizer.ts`) — Entropy-Filter gegen Framework-Hashes, Priorität ID > data-testid > semantic-attrs > full-path

---

## Consequences

### Positive

- **Einfache Architektur**: ein Inject-Point, ein Build, ein Browser. Kein State-Sync zwischen UI-Tab und automated Tab.
- **Funktioniert über Cross-Origin-Nav**: Playwright re-injectet das Script auf jeden neuen Document-Load. Die Problemklasse "Overlay verschwindet nach Cross-Origin-Navigation" ist strukturell vermieden.
- **SvelteKit-Features nutzbar**: Routing, Layouts, $derived/$state/$effect, `@sveltejs/adapter-static` für Build, alles wie für normale Static-SPA.
- **Single-IIFE-Artifact**: `vite-plugin-singlefile` produziert ein einziges JS-File das in eine einzige `add_init_script`-Call geht. Kein Asset-Server, kein zweiter HTTP-Endpoint für JS-Hosting.
- **CSS-Isolation via Shadow DOM**: keine Kollision mit Host-Page-Styles.

### Negative

- **Größerer Inject-Payload**: SvelteKit-Bundle inkl. Runtime + Pick-Mode-Logik wird ~30-60 KB gzipped. Größer als ein 5-KB-Vanilla-TS-Picker. Akzeptiert — wir haben SvelteKit-Features als Feature gewollt.
- **First-Inject-Latency**: das Script muss vor jedem Document-Load parsen + executen. Bei 50 KB Bundle auf moderner Hardware: ~5-15 ms. Akzeptiert — UI-Tool, nicht Sub-100-ms-Pipeline.
- **Host-Page kann Overlay-Host-Div theoretisch entfernen**: closed Shadow + `MutationObserver` als Schutz wäre möglich aber Phase 2+. In Phase 1 vertrauen wir der Host-Page (User scrapt was er kennt).
- **DevTools für die Overlay-UI sind in der Host-Page-DevTools-Console** — User muss zwischen Frame-Selector wählen wenn er debuggen will. Annehmbar.

### Was diese ADR NICHT macht

- Sie löst nicht das Audio/STT-Recording-Problem. Audio ist Phase 2+ — MediaRecorder im Main-World hat bekannte Komplikationen bei Cross-Origin-Navigation (die Aufnahme bricht beim Document-Wechsel ab). Falls Audio zurückkommt, wird es **außerhalb** der Page hostet (separater Recording-Service, nicht im Inject).
- Sie löst nicht die "Mission-Control für den Entwickler"-Frage. Falls eine Debug-View nützlich wird, kommt sie als read-only `/debug`-Route im selben Overlay-Bundle — kein separater Build, kein separater Tab.
- Sie macht keine Aussage zu Plugin-Discovery oder Multi-Site-Permissions. Phase 1 = der User startet `frontprompt show <url>` selbst, kennt die URL.

---

## Alternativen erwogen

### Alt 1 — UI in separater Browser-Tab (original ADR-001-Decision, ruled out)

**Pro**: Charter-konform. Trennt UI sauber von gescrapter Page. Keine CSS-Bleed-Risiken.

**Con**: Zwei Browser-Instanzen mit State-Sync, Tab-Discovery wenn User die UI-Tab schließt, Bidirectional-WS-Channel als Architektur-Constraint, Doppel-Build. **Ruled out** weil die Komplexität (siehe Reset-Doc) den User-Wert nicht trägt und das Legacy-FAREWELL-Argument mechanik-spezifisch war.

### Alt 2 — MV3-Extension-Architektur wie Legacy (ruled out — historisch)

**Pro**: Bewährter Pattern, Chrome-DevTools-Integration, Permissions-Modell.

**Con**: 4 IPC-Layer (MAIN/ISOLATED/SW/Python), ServiceWorker-Slumber-Bug, Chrome 137+ `--load-extension` removal, Manifest V2 EOL. Genau das was der Legacy gestorben ist. **Ruled out** — wir wechseln zu Playwright-CDP-Inject genau weil MV3 unser Hauptschmerz war.

### Alt 3 — CDP direkt statt Playwright `add_init_script` (ruled out — YAGNI)

Idee: `Page.addScriptToEvaluateOnNewDocument` direkt via CDP, ohne Playwright-Abstraction.

**Pro**: ein dependency weniger, voller CDP-Zugriff.

**Con**: Wir nutzen Scrapling, das Playwright unter der Haube nutzt, das CDP nutzt. Direkter CDP-Zugriff würde drei Layer überspringen — bringt keinen Nutzen, kostet Wartung. **Ruled out** — Playwright-API ist die richtige Abstraction-Höhe für unseren Use-Case.

### Alt 4 — Vanilla-TS Mini-Picker statt SvelteKit-SPA (ruled out — User-Direktive)

Idee: ~80 LoC Vanilla-TS ohne Framework, IIFE direkt geschrieben.

**Pro**: kleinerer Bundle, schnellerer First-Inject.

**Con**: kein Framework-Features wenn die UI komplexer wird (Layouts, Forms, Routing). User-Direktive 2026-05-18: "wir wollen ja schon irgendwie Features von SvelteKit nutzen und es halt einfach per [...] Build Injectable machen". **Ruled out** weil der User explizit SvelteKit-Features wollte.

---

## Migration

[ADR-001](./ADR-001-two-bounded-contexts.md) bekommt Amendment-Block mit `revoked: §UI-Surface "never inside the automated browser"`. Two-BC-Axiom bleibt konzeptionell, aber als `deferred` markiert (siehe Reset-Doc).

[ADR-008](./ADR-008-svelte-5-runes.md) bekommt Amendment-Block: SvelteKit Static-SPA-Build ist explizit erlaubt (ursprüngliche Fassung sagte "SvelteKit-Lite als Default-Add-on falls Routes notwendig" — wir aktivieren das jetzt).

[ADR-012](./ADR-012-pick-annotation-aggregate.md) bekommt Amendment-Block: Phase-1-Implementation drastisch simpler (in-memory Liste auf dem Daemon, keine SQLite, keine ACL-Validierung, keine Idempotency-Cache).

---

## Related ADRs

- [ADR-001 Two Bounded Contexts](./ADR-001-two-bounded-contexts.md) — `§UI-Surface` "never inside automated browser" wird durch diese ADR **revoked**
- [ADR-008 Svelte 5 Runes](./ADR-008-svelte-5-runes.md) — wird amended; SvelteKit Static-SPA-Build explizit erlaubt
- [ADR-009 Scrapling-Only-Substrate](./ADR-009-scrapling-only-substrate.md) — Scrapling liefert die `AsyncDynamicSession` mit Playwright-Page-API; `page.add_init_script` ist Playwright-Standard
- [ADR-012 Pick + Annotation Aggregate](./ADR-012-pick-annotation-aggregate.md) — Pick-Mode-Logik aus dieser ADR feedet in die `PointingSession`-Lifecycle; Implementation simpler
- [ADR-014 Daemon-Singleton via Lockfile](./ADR-014-daemon-singleton-via-lockfile.md) — Daemon hält den Overlay-IIFE im Memory, serviert HTTP-Endpoints für Overlay-Calls
- Interne Recherche zu Overlay-Architekturen in Browser-Extensions (interne Recherche, nicht veröffentlicht); relevante Sub-Sektionen zu Shadow-DOM-Isolation bleiben gültig, MV3-Sektionen sind in dieser ADR explizit ausgeschlossen
- 2026-05-18 Architecture Reset — Reset-Decision aus der diese ADR folgt
