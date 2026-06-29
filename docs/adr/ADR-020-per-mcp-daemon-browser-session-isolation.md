# ADR-020 — Per-MCP-Daemon Browser-Session-Isolation

> Part of the frontprompt [Architecture Decision Records](./index.md).

**Status**: accepted
**Date**: 2026-05-23
**Cross-References**: [ADR-014 Daemon Singleton (superseded)](./ADR-014-daemon-singleton-via-lockfile.md), [ADR-016 expose_function Bridge](./ADR-016-expose-function-bridge.md), [ADR-001 Two Bounded Contexts (amended 2026-05-18)](./ADR-001-two-bounded-contexts.md), 2026-05-18 Architecture Reset

---

## Context

Der MCP-Tool-Surface wird heute zum ersten Mal aktiviert (Phase-1-Out-of-Scope-Pivot 2026-05-23 per User-Direktive: "Ziel ist es jetzt, einen MCP-Server zur Verfügung zu stellen. Jeder Frontprompt-Prozess ist isoliert voneinander").

[ADR-014](./ADR-014-daemon-singleton-via-lockfile.md) hatte den Daemon-Singleton-Pattern via Lockfile als accepted festgelegt: eine Daemon-Instanz pro User, alle MCP-Stdio-Bridges attachen via Lockfile-Discovery, ein Browser, geteilter State. Begründung: Multi-Session-Isolation sei Phase-1 nicht nötig.

Tatsächlicher Code-Status zum Entscheidungszeitpunkt:

- ADR-014 ist **nie implementiert worden**. Es gibt im Repo weder `lockfile_singleton.py` noch `ensure_daemon()`-Helper noch `~/.frontprompt/daemon.json`-Discovery. Der existing `frontprompt daemon`-Command spawnt nur Two-BC-Skeleton + HTTP + WS-Server, **keinen Browser**, **keinen MCP-Server**.
- Der existing `frontprompt show`-Command (Phase-1-Haupttool) ist bereits strikt isoliert pro Aufruf: eigenes Session-Verzeichnis `~/.cache/frontprompt/sessions/<id>/`, eigener Unix-Socket `show.sock`, eigene `StateManager`-Instanz, eigenes Chromium. Mehrere parallele `show`-Aufrufe sind cross-talk-frei, ohne irgendwelche Lockfile-Koordination.

Die User-Direktive 2026-05-23 widerspricht der ADR-014-Acceptance: "MCP-Server Sessions sind isoliert voneinander, kennen sich nicht untereinander". Das ist genau das, was ADR-014 Alt 1 ("Per-MCP-Client-Session-Daemon") als ruled-out markiert hatte — wegen Browser-RAM × N und Discovery-Wildwuchs.

Mit dem Wissen, dass

1. ADR-014 nie Code wurde,
2. das `show`-Substrat bereits per-Process-Isolation als selbstverständliches Modell implementiert,
3. der User die Isolation explizit will,
4. der bisherige "Wildwuchs"-Konter (3 Daemons, 3 Browser, 3 Ports) nicht zutrifft, wenn keine HTTP/WS-Ports involviert sind (MCP-Stdio braucht keine TCP-Ports, und expose_function pro show-Child auch nicht),

ist die ADR-014-Begründung nicht mehr tragfähig.

## Decision

**Jeder `frontprompt daemon`-Aufruf ist ein vollständig isolierter Prozess. Er spawnt seine eigene `frontprompt show`-Child-Session als private Browser-Instanz und exponiert MCP-Stdio-Tools, die ausschließlich auf diese eigene Browser-Session wirken.**

### Konkret

- **Ein MCP-Daemon-Prozess besitzt genau eine Browser-Session als Child** (Process-Tree-Ownership). Beim Daemon-Boot wird `frontprompt show <start-url>` als Subprocess gestartet, der Child schreibt eine ready-Zeile auf stdout (`frontprompt:ready <session-id>`), der Daemon liest sie, kennt von da an seinen target Unix-Socket-Pfad.
- **Keine Lockfile-Discovery.** Kein `~/.frontprompt/daemon.lock`, kein `daemon.json`, kein `ensure_daemon()`-Helper. ADR-014 wird durch dieses ADR superseded.
- **Keine Cross-Daemon-Sichtbarkeit.** Daemon #1 und Daemon #2 sind im Filesystem-Cache `~/.cache/frontprompt/sessions/` jeweils ein Verzeichnis, kennen aber einander nicht — kein Scan, kein Listing, kein Shared-State.
- **Keine HTTP/WS-Server im daemon-Pfad.** Der heutige `daemon`-Code-Pfad (Two-BC-Nursery + `run_http_server` + `run_ws_push_server`) wird vom umgebauten `daemon`-Command nicht mehr aufgerufen. Der Skeleton-Code bleibt im Repo dormant (Phase-2-Reaktivierungs-Pfad bleibt offen, sollte ein zukünftiger Konsument-Pattern den brauchen).
- **MCP-Stdio bleibt der einzige Daemon-Channel.** Der Daemon spricht via stdin/stdout JSON-RPC mit Claude Code, und via Unix-Socket NDJSON mit seinem Child. expose_function (ADR-016) bleibt der Browser↔Python-Overlay-Channel — dieser ADR ändert daran nichts.

### Lebenszyklus

```
claude-code  ─stdio─▶  frontprompt daemon
                           │ spawns child
                           ▼
                       frontprompt show <start-url>
                           │
                           ▼
                       chromium (headful, isoliert)
```

Daemon-Exit (stdin EOF, SIGINT, Crash) sendet SIGTERM an die Process-Group → Child terminiert → `session_lifecycle` Cleanup räumt Socket, Session-Verzeichnis und Browser auf. Keine Zombies möglich.

### Konfiguration

Der `daemon`-Command nimmt keine Argumente zur Browser-Session-Auswahl entgegen — es gibt keine Session zu wählen, er bringt seine eigene mit. Einzige Konfiguration: `FRONTPROMPT_MCP_START_URL` env var (default `about:blank`), für Plugin-Configs die mit einer bestimmten Landing-Page öffnen wollen. Kein `--session`-Arg, kein `--socket`-Arg, keine externe Bindung.

## Consequences

### Positive

- **Klare Lifetime-Coupling via Process-Tree:** keine versteckten Zombies, keine Stale-Sockets, kein Lockfile-Cleanup-Aufwand. Daemon stirbt → Browser stirbt.
- **Konsistenz mit `show`-Substrat:** show-Sessions sind heute schon per-Process-isoliert. MCP-Daemons folgen dem gleichen Pattern statt eine zweite Topology (Singleton) zu etablieren.
- **Trivialer Mental-Model für den User:** "Pro Claude-Code-Session ein eigener MCP-Daemon, der seinen eigenen Browser besitzt. Punkt." Keine Diskussion über Cross-Session-Picks-Sichtbarkeit, keine "warum sehe ich plötzlich Picks aus einer anderen Session"-Verwirrung.
- **Code-Minimum:** keine Lockfile-Logik, keine Discovery-File-Race-Conditions, kein Stale-Daemon-Recovery, kein Port-Allocation. Der gesamte daemon-Body ist child-spawn + MCP-stdio-loop.
- **Phase-2-fähig:** wenn später echte Multi-Daemon-Koordination gebraucht wird (z.B. Pick-Sharing zwischen MCP-Sessions, oder eine zentrale Annotation-Datenbank), kann der Two-BC-Skeleton + HTTP/WS-Code im Repo reaktiviert werden — ADR-020 nimmt dem nichts weg.

### Negative

- **Browser-RAM × N:** drei parallele Claude-Code-Sessions mit aktivem MCP = drei Chromium-Instanzen = ~900 MB RAM. Akzeptiert — dieser Tradeoff war der Hauptkonter in ADR-014 Alt 1, aber der User hat die Isolation explizit priorisiert und der zugehörige Use-Case (1-3 parallele Sessions, modern Dev-Hardware mit 32+ GB RAM) macht das unkritisch.
- **Kein Shared-State zwischen MCP-Daemons:** wenn ein User in zwei parallelen Claude-Codes "dieselben Picks teilen" wollen würde, geht das nicht. Akzeptiert — das war nie ein dokumentierter Use-Case, war nur eine Konsequenz aus ADR-014 die der User nicht wollte.
- **Cold-Boot pro Daemon:** jede neue Claude-Code-Session zahlt ~3s Chromium-Cold-Boot. Akzeptiert — gegenüber ADR-014 verlieren wir das Attach-an-laufenden-Daemon-Optimum, aber der Boot ist einmalig pro Session und transparent.

### Strukturelle Konsequenzen

- **Code-Pfad-Pivot im `daemon`-Command:** `cli.py daemon` ruft nicht mehr `_daemon_async_main` → `run_daemon` (Two-BC + HTTP/WS). Stattdessen einen neuen, minimalen Top-Level: spawn-show-child → boot `serve_mcp_stdio` mit 5 read-only Tools.
- **`mcp_server.py` Tool-Registry wird gefüllt:** die 5 Tools (ping, get_session_info, get_snapshot, get_picks, get_pick) wrappen die existing IPC-Read-Operations zum Child-Socket via `frontprompt.ipc.query()`.
- **Two-BC + HTTP + WS bleibt dormant:** `daemon.py`, `bc/`, `wire/http_server.py`, `wire/ws_server.py` werden vom daemon-Command nicht mehr referenziert, bleiben aber als Skeleton im Repo für Phase-2-Reaktivierung.
- **Kein neuer Lockfile-Code:** `~/.frontprompt/daemon.lock` und `daemon.json` werden nicht angelegt. Falls je ein User ein altes `~/.frontprompt/`-Verzeichnis aus Pre-ADR-020-Experimenten hat, ist es harmlos.

## Alternativen erwogen

### Alt 1 — ADR-014-Singleton-Lockfile-Pattern (superseded)

Wäre der ursprüngliche ADR-014-Pfad gewesen. Ruled out 2026-05-23 wegen User-Isolations-Direktive. Begründungs-Details siehe ADR-014 §Decision (heute superseded). Die Browser-RAM-Konter aus ADR-014 Alt 1 wird hier akzeptiert, weil expose_function (ADR-016) den HTTP/WS-Stack nicht braucht und Browser-RAM die einzige verbleibende Kosten-Komponente ist.

### Alt 2 — Singleton-Daemon mit per-MCP-Session-Browser-Sub-Spawn (ruled out)

Idee: ein Daemon pro User (Lockfile, wie ADR-014), aber der Daemon spawnt pro angeschlossener MCP-Stdio-Bridge eine eigene Browser-Session und tagged sie mit `mcp_client_session_id`. MCP-Tools operieren strikt auf dem zur eigenen Bridge gehörenden Browser.

**Pro:** behält Daemon-Singleton-Eleganz UND erfüllt Isolations-Direktive.
**Con:** signifikante Implementation-Komplexität (mcp_client_session_id-Bookkeeping im Daemon, Multi-Browser-Lifecycle, Lockfile-+-Per-Session-Cleanup). ADR-014 selbst sagt diese Isolation sei "Phase 2+ wenn benötigt". Wenn wir es brauchen, brauchen wir aber auch die Singleton-Komponente nicht mehr — der Per-Daemon-Pattern ist konsistenter und minimaler.

**Ruled out** wegen unnötiger Komplexität gegenüber Per-Daemon. Eine zukünftige Reaktivierung ist nicht ausgeschlossen, wenn ein echter Daemon-shared-state-Use-Case auftaucht.

### Alt 3 — `frontprompt show`-Side hat MCP-Stdio inline (ruled out)

Idee: kein separater daemon-Command. `frontprompt show <url>` selbst booted zusätzlich zum Browser + Socket auch einen MCP-Stdio-Server auf seinem stdin/stdout.

**Pro:** ein Prozess statt zwei (Parent-Child).
**Con:** stdin/stdout des `show`-Commands ist heute für User-Logs reserviert (structlog ConsoleRenderer, Status-Messages, click.echo). Diese stdio würde MCP-Stdio kapern. Außerdem würde es das `show`-Command für Plugin-stdio-Spawning konfigurieren erfordern (mit zusätzlichem Flag), was die existing CLI-Surface kompliziert.

**Ruled out** wegen stdio-Konflikt und CLI-Komplexität. Parent-Child mit separatem daemon-Command ist sauberer.

## Related ADRs

- [ADR-014 Daemon Singleton via Lockfile](./ADR-014-daemon-singleton-via-lockfile.md) — **superseded by this ADR**
- [ADR-016 expose_function Bridge](./ADR-016-expose-function-bridge.md) — Overlay-Transport bleibt CDP; ADR-016 §Phase-2+-Trigger ("HTTP/WS zurückbringen wenn ADR-014 aktiviert") wird bedeutungslos, weil ADR-014 nicht mehr aktiviert wird. Trigger gilt nur noch für hypothetische zukünftige Multi-Daemon-Koordinations-Use-Cases.
- [ADR-001 Two Bounded Contexts (amended 2026-05-18)](./ADR-001-two-bounded-contexts.md) — Two-BC bleibt deferred; ADR-020 ändert daran nichts. Two-BC-Code im Repo bleibt dormant.
- 2026-05-18 Architecture Reset — der Reset hat ADR-014 als accepted markiert auf Basis der Phase-1-No-Isolation-Annahme. Diese Annahme wird mit ADR-020 revidiert.
- message-hub-mcp Lockfile-Pattern — bleibt das Referenz-Pattern für Multi-Client-MCP-Server, ist hier aber nicht passend, weil frontprompt-MCP gerade keinen shared state braucht.
