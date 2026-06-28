# ADR-014 — Daemon-Singleton via Lockfile (message-hub-pattern)

> Part of the frontprompt [Architecture Decision Records](./index.md).

**Status**: superseded by [ADR-020](./ADR-020-per-mcp-daemon-browser-session-isolation.md) (2026-05-23)
**Date**: 2026-05-18
**Cross-References**: [ADR-020 Per-MCP-Daemon Browser-Session-Isolation](./ADR-020-per-mcp-daemon-browser-session-isolation.md), [ADR-001 Two Bounded Contexts](./ADR-001-two-bounded-contexts.md), [ADR-005 Nursery-per-PageSession](./ADR-005-nursery-per-pagesession.md), message-hub-mcp CLAUDE.md, 2026-05-18 Architecture Reset

> **Amendment 2026-05-23**: Superseded by [ADR-020 Per-MCP-Daemon Browser-Session-Isolation](./ADR-020-per-mcp-daemon-browser-session-isolation.md). Die Daemon-Singleton-Decision wurde nie als Code implementiert (kein `lockfile_singleton.py`, kein `ensure_daemon()`, kein `~/.frontprompt/daemon.json`). User-Direktive 2026-05-23 hat "MCP-Sessions sind isoliert voneinander" priorisiert — der dort als ruled-out markierte Alt 1 (Per-MCP-Daemon mit eigenem Browser) wird in ADR-020 rehabilitiert, weil der Hauptkonter (HTTP/WS-Port-Wildwuchs) bei reiner Stdio-MCP-Topologie nicht zutrifft. Der unten beschriebene Inhalt bleibt als historisches Dokument; die Decision selbst gilt nicht mehr.

---

## Context

`frontprompt` wird via `uv tool install frontprompt` distributed und ist als CLI-Tool gedacht (`frontprompt show <url>`). Der Daemon ist ein langlaufender Python-Prozess der einen headful Chromium besitzt, MCP-stdio-Verbindungen entgegennimmt, HTTP-Endpoints serviert, und Pick-Events von Overlay-injizierten Pages annimmt.

Die offene Frage: was passiert wenn der User parallel mehrere Aufrufe macht — drei `frontprompt show`-CLIs in drei Terminals, oder zwei Claude-Code-Sessions die jeweils via MCP-stdio-Bridge einen Daemon brauchen?

Drei mögliche Modelle waren auf dem Tisch:

1. **Per-Invocation-Daemon**: jeder Aufruf spawnt einen eigenen Daemon mit ephemeral Port. → Discovery-Hell für Mission-Control-UI, mehrere headful Chromium-Instanzen, kein Shared-State zwischen Sessions, Port-Salat.
2. **Per-mcp_client_session-Daemon**: ein Daemon pro MCP-Stdio-Bridge-Verbindung. → Selbe Probleme wie Per-Invocation, plus: CLI-Aufrufe (ohne MCP) brauchen extra Logik.
3. **Singleton-Daemon via Lockfile**: eine Daemon-Instanz pro User. Erste Invocation spawnt, alle weiteren attachen. → Shared State, ein Browser, ein Port. Vorhandenes Pattern: message-hub-mcp macht das produktiv.

User-Direktive 2026-05-18 hat Modell 3 gewählt mit der Begründung: Multi-Session-Isolation ist Premature, brauchen wir Phase 1 nicht.

---

## Decision

**Eine Daemon-Instanz pro User. Lifecycle-Koordination via Lockfile.**

Konkret:

### Lockfile-Layout

- Lockfile: `~/.frontprompt/daemon.lock` — POSIX `fcntl.flock` (exclusive, non-blocking) zur Single-Instance-Garantie
- Discovery-File: `~/.frontprompt/daemon.json` — JSON mit `{pid, port, started_at_iso, http_url, ws_url, schema_version}` — wird vom Lockfile-Owner geschrieben, von Attaching-Clients gelesen

### Boot-Sequenz (CLI + MCP-Bridge identisch)

1. Try `fcntl.flock(lockfile, LOCK_EX | LOCK_NB)`.
2. **Lock erworben** → ich bin der erste, spawne Daemon, schreibe `daemon.json`, halte den Lock für die gesamte Daemon-Laufzeit. Bei Daemon-Shutdown wird Lock + `daemon.json` aufgeräumt.
3. **Lock-Konflikt** → existierender Daemon läuft. Lese `daemon.json`, validiere `pid` ist alive (`os.kill(pid, 0)`), attache via `http_url` / `ws_url`. Falls `pid` tot (stale daemon.json), `daemon.json` löschen + retry ab Schritt 1.

### Port-Wahl

Bevorzugt `7178` (HTTP) und `7177` (WS-Push, Phase 2). Wenn belegt: ephemeral port (`bind(0)`) + write actual port in `daemon.json`. Discovery-Clients lesen `daemon.json`, kein Port-Hardcoding.

### Shutdown-Reihenfolge

1. SIGTERM/SIGINT trigger graceful Nursery cancel
2. PageSession-Aggregate cleanup (Browser close)
3. Lockfile-Release via context manager (`__exit__`)
4. Cleanup von `daemon.json`

Stale-Lock-Recovery: wenn Daemon-Crash ohne Cleanup (SIGKILL), liegt `daemon.lock` orphaned. Nächster Boot detektiert via `fcntl.flock` non-blocking attempt — Lock wird vom Kernel beim Crash freigegeben, deshalb erfolgreich. `daemon.json` mit toter `pid` wird gelöscht.

### Multi-Session-State-Semantik

- Alle Pick-Events von allen attached Clients (MCP-Bridges + CLI-Invocations) landen im selben Daemon
- Alle headful-Chromium-Tabs sind im selben Browser-Process
- Kein Per-Client-State-Namespace in Phase 1 — wenn drei Claude-Codes parallel arbeiten, sehen alle die gleichen Picks im structlog
- Isolation kommt in Phase 2 falls echter Bedarf entsteht (siehe Alternativen § Alt 1)

---

## Consequences

### Positive Konsequenzen

- **Pragmatisch funktionierender Pattern**: message-hub-mcp implementiert dasselbe Schema produktiv seit Monaten — kein neues Risiko
- **Kein Discovery-Tab-Problem**: Mission-Control (wenn sie kommt) hat einen festen URL pro User
- **Ein Browser**: User sieht eine Chrome-Instanz, eine User-Profile-Sammlung, ein Tabs-Set
- **Kein Port-Salat**: ein Port pro Daemon, in `daemon.json` discoverable
- **MCP + CLI identische Code-Pfade**: beide nutzen den `ensure_daemon()`-Helper

### Negative Konsequenzen

- **Kein Per-Session-Isolation in Phase 1**: zwei Claude-Codes können sich gegenseitig Picks anzeigen / Page-Sessions stören. Akzeptiert für Phase 1.
- **Single-Point-of-Failure**: wenn der Daemon crashed, sind alle attached Clients down. In Phase 1 akzeptiert; in Phase 2+ wird Restart-Resilienz wichtiger.
- **Lockfile-Cross-Platform**: `fcntl.flock` ist POSIX. Windows-Support (falls je relevant) bräuchte `msvcrt.locking` fallback. Akzeptiert — frontprompt ist primär macOS/Linux.

### Strukturelle Konsequenzen

- Neues Modul: `src/frontprompt/daemon/lockfile_singleton.py` — `ensure_daemon() -> DaemonHandle` API
- `daemon.py` (top-level Lifecycle) wird umgebaut: `run_daemon()` ist nicht mehr direkt callable, sondern via `ensure_daemon()` wrapped
- CLI-Subcommand `frontprompt show <url>` und MCP-stdio-Boot nutzen denselben `ensure_daemon()`-Code-Pfad
- `DaemonHandle` exponiert: `http_url`, `ws_url`, `attach()`, `close()` (wobei `close()` nur den eigenen Attachment löst, nicht den Daemon killed)

---

## Alternativen erwogen

### Alt 1 — Per-mcp_client_session-Daemon (ruled out)

Idee: ein Daemon-Prozess pro MCP-Stdio-Bridge-Verbindung; Identity = `mcp_client_session_id`.

**Pro**: natürliche Isolation zwischen Claude-Code-Sessions. Eine Session crashed nicht die anderen.

**Con**: Drei Probleme. (a) Discovery-Hell: drei Daemons, drei Ports, drei headful Browser, drei Mission-Control-Tabs — der User sieht Browser-Wildwuchs. (b) Inkonsistenter Code-Pfad: CLI-Aufruf hat kein `mcp_client_session_id`, braucht extra "cli-session"-Identity. (c) Ressourcen-Multiplikation: Chromium-Headful-Process ist ~300 MB pro Instanz. Drei parallele Claude-Codes → 900 MB Browser-RAM ohne Nutzen.

**Ruled out** weil die Isolation in Phase 1 nicht benötigt wird und die Kosten 3x höher sind.

### Alt 2 — Per-Invocation-Daemon mit ephemeral Port (ruled out)

Idee: jeder `frontprompt`-Aufruf spawnt einen kurzlebigen Daemon der mit dem Exit des CLIs stirbt.

**Pro**: keine Lockfile-Komplexität, kein Discovery-Issue.

**Con**: Tötet die Idee eines persistenten Tools komplett. MCP-Stdio-Bridges können nicht arbeiten weil sie kein eigenes CLI sind — sie sind selbst nur ein stdin/stdout-Pipe und brauchen den Daemon **außerhalb** ihres eigenen Lifecycles. Außerdem: jeder neue Browser-Spawn (~3 s Cold-Boot, ~300 MB RAM) ist UX-feindlich.

**Ruled out** weil MCP-Stdio-Bridges fundamental einen persistenten Daemon brauchen.

### Alt 3 — Systemd-Service / launchd-Plist statt Lockfile (ruled out für jetzt)

Idee: Daemon wird als OS-Service registriert (`launchctl load` auf macOS, `systemctl --user enable` auf Linux), automatisch beim Login gestartet.

**Pro**: kein Lockfile nötig, OS-managed Lifecycle, Auto-Restart bei Crash.

**Con**: zusätzliche Setup-Komplexität (Installer muss launchd/systemd-Konfig deployen), `uv tool install`-Workflow wird gebrochen, Distribution wird OS-spezifisch.

**Aufgeschoben, nicht abgelehnt**: wenn Phase 2+ ein "frontprompt läuft im Hintergrund auch wenn kein CLI offen ist"-Bedarf entsteht, ist OS-Service-Integration die richtige Antwort. Für Phase 1 reicht Lockfile.

---

## Related ADRs

- [ADR-001 Two Bounded Contexts](./ADR-001-two-bounded-contexts.md) — die Two-BC-Architektur lebt **im** Daemon-Prozess; ADR-014 entscheidet wie viele Daemon-Prozesse es gibt (Antwort: einer)
- [ADR-005 Nursery-per-PageSession](./ADR-005-nursery-per-pagesession.md) — Nursery-Hierarchie ist intern, Daemon-Singleton ist die äußere Schale
- [ADR-013 Mandatory Domain-Prefix](./ADR-013-mandatory-domain-prefix-ubiquitous-language.md) — `mcp_client_session_id` ist Phase-2-Term, in Phase 1 nicht benötigt
- 2026-05-18 Architecture Reset — Reset-Decision aus der diese ADR folgt
