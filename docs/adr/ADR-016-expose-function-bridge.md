# ADR-016 — Bridge via Playwright `expose_function` (Phase 1)

> Part of the frontprompt [Architecture Decision Records](./index.md).

**Status**: accepted
**Date**: 2026-05-18
**Cross-References**: [ADR-001 Two BCs (amended)](./ADR-001-two-bounded-contexts.md), [ADR-014 Daemon Singleton (deferred)](./ADR-014-daemon-singleton-via-lockfile.md), [ADR-015 Overlay in Main World](./ADR-015-overlay-in-page-main-world.md), [ADR-017 Canonical Build Pipeline](./ADR-017-canonical-build-pipeline.md), 2026-05-18 Architecture Reset

---

## Context

Der Architecture-Reset 2026-05-18 hat den Daemon-Singleton (ADR-014) als deferred markiert und HTTP/WS-Server (Channels 2+3) als unbenutzt-in-Phase-1 stillgelegt. Der aktuelle Code-Pfad ist:

- `frontprompt show <url>` spawnt im selben Python-Process einen headful Chromium via Playwright
- Overlay läuft als IIFE-Bundle in der Main World, injectiert via `page.add_init_script`
- **Kein** HTTP-Server, **kein** WebSocket-Server, **kein** Daemon-Process

In dieser Konstellation ist eine bidirektionale Backend↔Overlay-Kommunikation nötig, aber HTTP/WS würden den ganzen Server-Stack zurückbringen, den der Reset gerade losgeworden ist.

Drei Optionen wurden evaluiert:

| Option | Server-Boilerplate | Port-Mgmt | CORS | Native | Bidirektional |
|---|---|---|---|---|---|
| WebSocket | ja | ja | ja | nein (lib) | ja |
| SSE | ja | ja | ja | nein (lib) | nein (uni) |
| **`page.expose_function`** | **nein** | **nein** | **nein** | **ja (CDP)** | **ja** |

`page.expose_function(name, callback)` ist eine native Playwright-API die eine Python-Async-Funktion als `window.<name>` im Page-Main-World-Context verfügbar macht. Aufrufe gehen direkt über den CDP-Channel — keine TCP-Port-Allocation, kein Origin-Header-Check, kein Reconnect-Handling.

Die andere Richtung (Python → Overlay) erfolgt via `page.evaluate(js_expr)` mit JSON-serialized payload, die der Bridge-Service im Overlay dispatched.

---

## Decision

**Phase-1-Bridge zwischen Python-Backend und Overlay-Frontend nutzt `page.expose_function` (Overlay → Python) + `page.evaluate` (Python → Overlay). Single Service `window.__fp` als einzige sichtbare Schnittstelle im Overlay-Page-Namespace. End-to-end-typed via Pydantic SSoT + auto-generated Zod-Schemas.**

### Architektur

```
Python-Process (CLI)
├── BrowserSessionManager (Playwright lifecycle)
│   └── Page
│       ├── add_init_script(overlay.iife.js)  ← overlay-bundle injected
│       └── expose_function('__fp_send', BridgeManager._on_outbound)
│
└── BridgeManager (owns message routing)
    ├── _on_outbound(raw) → Pydantic.validate → handler dispatch
    └── send(InboundMessage) → page.evaluate('window.__fp.dispatch(...)')

Overlay (Main World, injected IIFE)
└── window.__fp
    ├── .send(OutboundMessage)   ← consumed by overlay code; wraps __fp_send
    └── .dispatch(InboundMessage) ← called by Python; routes to handlers
```

### Namespace-Discipline

Playwright's `expose_function('X', cb)` schreibt `window.X` als top-level global — keine Möglichkeit das in ein nested object zu mounten. Lösung:

1. Python: `await page.expose_function('__fp_send', bridge._on_outbound)` → `window.__fp_send` existiert
2. Overlay-init: bridge.svelte.ts liest `window.__fp_send` in eine private closure, **deleted `window.__fp_send`**, mountet `window.__fp = { send, dispatch, version_info }` als einzigen sichtbaren global

End-state: **`window.__fp` ist das einzige frontprompt-Global im Page-Namespace.**

### Message-Discipline

- Pydantic-Models definieren message-schemas in `src/frontprompt/bridge/messages.py`
- `pydantic-zod-codegen` generiert Zod-Schemas + TS-Types nach `frontend/src/_generated/schemas.ts`
- Beide Seiten validieren am bridge-boundary:
  - Overlay → Python: Zod parse (overlay-side) + Pydantic validate (python-side, defense-in-depth)
  - Python → Overlay: Pydantic serialize (python) + Zod parse (overlay)
- Discriminated unions via `kind`-field-discriminator
- Jede Message trägt `schema_version: "0.1.0"` für forward-compatibility

### Interceptor-Pattern

Bridge exposes `addInterceptor(fn: (event: BridgeEvent) => void): () => void` — jeder registrierte Interceptor sieht ALLE Events (in + out) inkl. timestamps, kinds, payloads. Returns unsubscribe-function.

Erste Konsumenten:
- DebugPanel (zeigt live-feed)
- Future: metrics, replay, schema-validation-failure-collector

### Lifecycle-Sequence

Beim `frontprompt show <url>`:

1. `BrowserSessionManager.__aenter__` → page created
2. **`BridgeManager.__aenter__`** → `expose_function('__fp_send', ...)` **VOR** `add_init_script`
3. `OverlayInjector.install_init_script(bundle)` → bundle registered
4. `BrowserSessionManager.navigate(url)` → page loads, bundle runs at document_start, bridge.svelte.ts setupt `window.__fp` (mit lazy lookup von `__fp_send` falls expose noch nicht ready)
5. Overlay-side bridge sendet `OverlayReady` outbound
6. Python `wait_until_overlay_ready()` returns
7. Python kann jetzt Heartbeats und andere Messages senden

---

## Consequences

### Positive

- **Zero Server-Boilerplate**: kein Starlette, kein Uvicorn, kein WS-Library
- **Zero Port-Mgmt**: kein Port-Conflict, kein Discovery, kein Lockfile
- **Zero CORS-Config**: alles über CDP-Channel, kein Origin-Header-Check
- **End-to-end-typed**: Pydantic-SSoT macht TS-types automatisch korrekt
- **Single Window-Global**: `window.__fp` ist der einzige sichtbare API-Surface
- **Native Playwright-API**: keine extra deps für Transport
- **Interceptor-extensible**: Debug-Panel, Metrics, etc. ohne bridge-changes

### Negative

- **Kein Cross-Process**: funktioniert nur wenn Python die Page selbst spawned hat. Wenn später ein zweiter Client (z.B. weitere MCP-Bridge) den selben Daemon attachen will, ist HTTP/WS unvermeidbar.
- **CDP-Channel-Throughput-Limit**: für sehr high-frequency events (>1kHz) wäre WS performanter. Phase 1 hat keine solche Anforderung.
- **Kein replay-fähiges Wire-Logging**: messages laufen nicht über netzwerk, sind nicht trivial in einem Wireshark-/Devtools-Network-Tab capturable. Mitigation: interceptor-pattern + Debug-Panel.

## Known TOCTOU Limitations (F-S-002)

**Finding**: F-S-002 / ur-20260520-main-03187317  
**Decision**: accept as architectural false-positive

### The TOCTOU window

From the moment `page.expose_function("__fp_internal_state_getter", fn)` registers the callback until `setupBridge()` in the overlay executes `delete w.__fp_internal_state_getter`, the name `window.__fp_internal_state_getter` exists as a callable global in the browser's main world. Any script that runs before `DOMContentLoaded` could, in principle, call this function.

### Risk assessment

- **Window duration**: the gap closes synchronously at `DOMContentLoaded`. Playwright's `add_init_script` model guarantees the overlay bundle runs at document-start, and `setupBridge()` is the very first action in `mountOverlay()`. No async gap exists.
- **Data exposed**: the function returns the current session's picks, regions, and relations — local in-session state. This is not authentication credentials, not cross-user data, not session tokens.
- **Threat model**: the overlay runs inside a Playwright-controlled browser session spawned by the local Python process. This is not a public multi-tenant web context. Third-party scripts running before `DOMContentLoaded` in this context are an extremely narrow threat surface.
- **CDP constraint**: `expose_function` is a Playwright/CDP architectural constraint, not a frontprompt bug. There is no public Playwright API to register a callable directly at `window.__fp.getState` — only top-level globals are supported.

### Accepted-risk decision

This finding is classified as an **architectural false-positive** for Phase 1. The risk is accepted because:

1. The TOCTOU window is synchronous and extremely short (closes at DOMContentLoaded)
2. The exposed data does not include credentials or cross-user information
3. Fixing it properly (Phase-2 escape hatch) requires switching away from `expose_function` entirely

### Phase-2 escape hatch

If the threat model expands to include credentials, authentication tokens, or cross-user data:

1. Generate a UUID-named getter at Python startup: `getter_name = f"__fp_getter_{uuid.uuid4().hex}"`
2. Register it via `expose_function(getter_name, fn)`
3. Propagate the `getter_name` to the overlay via `page.evaluate` initial seed (not expose_function)
4. Overlay's `setupBridge()` uses the propagated name to locate and migrate the getter, then deletes it
5. This eliminates the fixed-name exposure entirely — no public script can guess the getter name before `DOMContentLoaded`

Trigger criteria: threat model expands to credentials or cross-user data. Until then: current implementation is correct.

---

### Phase-2+-Trigger

WS/SSE/HTTP-Server werden zurückgeholt sobald:

- Mehrere Page-Sessions / Browser-Tabs **in einem Daemon-Prozess** gleichzeitig (multi-user, multi-target-scrape) — nach [ADR-020](./ADR-020-per-mcp-daemon-browser-session-isolation.md) ist das nicht das normale Pattern, würde aber bei einem zukünftigen daemon-shared-state-Use-Case greifen
- ~~Daemon-Singleton (ADR-014) wird aktiviert (mehrere MCP-Bridges attachen)~~ — obsolet seit [ADR-020](./ADR-020-per-mcp-daemon-browser-session-isolation.md), ADR-014 ist superseded; jeder MCP-Daemon hat seinen eigenen Browser-Child, keine Multi-Bridge-Attaches
- Real-time-events die nicht vom Python-Process initiiert werden (z.B. server-pushed alerts)

Bis dahin: `expose_function` ist der canonical Transport.

---

## Alternativen erwogen

### Alt 1 — HTTP POST + SSE (ruled out für Phase 1)

**Pro**: Standard web pattern, debuggbar mit curl, Cross-process-tauglich.
**Con**: Bringt den Daemon-Server zurück (Starlette + Uvicorn + Port + CORS), gegen den Architecture-Reset 2026-05-18 explizit entschieden wurde. **Ruled out** weil der Server-Stack Komplexität zurückbringt die wir gerade losgeworden sind.

### Alt 2 — WebSocket-Server (ruled out für Phase 1)

**Pro**: Bidirektional, low-latency, lib aus wire-protocol bundle bereits da (ungenutzt).
**Con**: Selber Daemon-Server-Issue. Plus: Reconnect-Handling-Komplexität die wir bei expose_function nicht haben.

### Alt 3 — Multiple `expose_function`-Calls pro Message-Kind (ruled out)

**Pro**: Cleaner namespace pro kind (`window.frontprompt_pick`, `window.frontprompt_heartbeat`, etc.).
**Con**: Pollution des window-Namespace mit N globals. User-Direktive: "EIN service, keine 10000 functions". **Ruled out**.

---

## Related ADRs

- [ADR-001 Two Bounded Contexts (amended)](./ADR-001-two-bounded-contexts.md) — channels 2+3 deferred
- [ADR-014 Daemon Singleton (deferred)](./ADR-014-daemon-singleton-via-lockfile.md) — würde HTTP/WS zurückbringen
- [ADR-015 Overlay in Main World](./ADR-015-overlay-in-page-main-world.md) — overlay-context für expose_function
- [ADR-017 Canonical Build Pipeline](./ADR-017-canonical-build-pipeline.md) — codegen-pipeline (Pydantic → Zod) ist Voraussetzung
- 2026-05-18 Architecture Reset
