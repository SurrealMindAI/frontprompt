# Design: First-Class Local Dev Loop for the Overlay/Daemon

- **Date**: 2026-06-25
- **Status**: Draft — design only, ready for implementation planning
- **Project**: frontprompt
- **Touches**: CLI surface (`src/frontprompt/cli.py`), IPC protocol (read-only, no new wire types), overlay bundle loader (`src/frontprompt/overlay/loader.py`), session discovery (`src/frontprompt/ipc/session.py`), build pipeline (`src/frontprompt/build/__main__.py`), `DEVELOPMENT.md`
- **Schema impact**: **none** — every interaction this design adds maps to an `IpcRequest` that already exists in `IPC_SCHEMA_VERSION = 0.6.0`. This is a CLI/ergonomics layer over the existing socket, not a protocol change.

## Problem

A developer — human or Claude-Code agent — iterating on the overlay/daemon today has no first-class, repeatable loop. The gap, in the user's words:

> *"ein `frontprompt show` würde öffnen, aber wir brauchen ja die session und mit dieser können wir erst interagieren."*

`frontprompt show <url>` opens a headful Chromium and exposes a per-session unix socket, but:

1. **The interaction surface is not first-class.** The write/debug IPC operations (navigate, screenshot, eval-js, pick, page-info) exist in the protocol (`src/frontprompt/ipc/protocol.py`) and are driven only by the MCP daemon. The CLI exposes **only read-only** subcommands (`sessions list/prune`, `state`, `picks list/get`, `ping` — `cli.py:145-267`). To drive a running session by hand today, an agent must hand-write a throwaway script that opens the socket and speaks NDJSON. That is the status quo we are replacing.
2. **The session lifecycle is ad-hoc.** An agent spawns `frontprompt show` in the background, then has to find the socket. `pick_latest_session()` exists but "latest" is ambiguous once more than one session is alive.
3. **Rebuild→running-bundle propagation is undefined.** A rebuild does not reach an already-running session (see [Hot-reload verdict](#hot-reload-verdict)), and the embedded-vs-dev bundle precedence can silently serve a stale overlay.

This design makes all three first-class without republishing the plugin.

## Goals

- One documented, consistent way to run the local clone against a real session **without reinstalling/republishing the plugin**.
- Exactly **one** stable, discoverable, long-lived dev session, reliably targetable by both a human and an agent.
- First-class CLI debug subcommands (`navigate`, `eval`, `screenshot`, `page-info`, `pick`) that drive the selected/latest session over the **existing** IPC socket — DRY with the read-only subcommands and the MCP tool surface (same `IpcRequest` types). This deletes the throwaway-harness pattern.
- One ergonomic command: build → (re)start dev session → ready.
- Deterministic local↔plugin consistency: version/schema/bundle provenance, doctor checks, predictable bundle precedence.

## Non-Goals (YAGNI)

- **In-page hot-swap of the overlay bundle without restarting `show`.** Shown infeasible below; the dev loop reloads by restarting the session, which is cheap and deterministic.
- **A new IPC schema version or new wire types.** Everything maps onto existing requests.
- **A daemon-singleton / cross-process live state sync.** Out of scope, already deferred (see [SQLite-persistence design](2026-05-31-sqlite-persistence-design.md)).
- **A new build tool (Make/just).** A single shell script under `scripts/` is enough and matches the repo (no Makefile/justfile today; `scripts/` already holds `check_versions.py`, `install-hooks.sh`).

---

## 1. Local-dev launch (no republish)

Two complementary mechanisms, both already partly documented in `DEVELOPMENT.md`:

### 1a. Local-scope MCP shadow (for driving frontprompt **as an MCP server** from Claude Code)

```bash
claude mcp add --scope local --transport stdio frontprompt \
  -- uv run --directory /abs/path/to/frontprompt frontprompt mcp
```

Scope precedence `local > project > user > plugin` means this shadows the plugin's `uvx --from frontprompt frontprompt mcp` (`plugin/.mcp.json`, confirmed) with the working tree. Lives in `~/.claude.json`, uncommitted. **Confirmed correct** — no change needed beyond documentation polish. (This design does not call `claude mcp add` for you; it is a one-time human step.)

### 1b. Direct CLI against a dev session (for driving frontprompt **as a tool**, human or agent)

This is the path this design makes first-class. You do **not** need the MCP layer to iterate on the overlay: run one `frontprompt show` dev session and drive it with the new CLI debug subcommands ([§3](#3-interaction-surface-the-core-ask)). `uv run frontprompt …` resolves the working-tree package, so local source is always what runs.

### Local↔plugin consistency primitives (provenance)

Three independent provenance signals already exist and must be the basis of every consistency check — do not invent a fourth:

| Signal | Source of truth | Where it lives |
|---|---|---|
| Python package version | `importlib.metadata.version("frontprompt")` | `pyproject.toml` → `frontprompt = "frontprompt.cli:main"` |
| Overlay **build session** (per-build UUID) | `build-manifest.json:build_session` | embedded `_overlay/` or dev `frontend/dist/`; handshaked at bridge `wait_until_ready` (`show_session.py:428`) |
| Two schema versions (independent, by design) | `IPC_SCHEMA_VERSION = 0.6.0` (socket wire) and overlay `schema_version = 0.7.0` (bridge/state, `build/__main__.py:_SCHEMA_VERSION`) | `ipc/protocol.py` vs `build-manifest.json` |

The two schema numbers are **intentionally different** (`protocol.py` docstring: "separate evolution"). A doctor check must compare like-for-like (IPC schema for the socket round-trip; overlay schema/build_session for the bridge handshake), never conflate them.

---

## 2. Session management — one stable dev session

### The invariant we want

> At any time during dev there is **exactly one** dev `show` session, and `frontprompt <debug-cmd>` (no `--session`) targets it.

`_resolve_session(None)` already returns `pick_latest_session()` (newest alive), and `--session <id>` targets explicitly (`cli.py:120-142`). Two ways to guarantee the invariant:

- **Approach A (zero code change, recommended default).** The dev launcher ([§4](#4-one-ergonomic-loop)) tears down any prior dev session before starting a new one. With at most one dev session alive, "latest" *is* the dev session. A human who also runs unrelated `show` instances falls back to explicit `--session`.
- **Approach B (stable, labeled session — small code change, recommended for robustness).** Allow `frontprompt show` to take a caller-supplied, human-stable session id so the socket path is predictable and survives "which one is latest?" ambiguity:
  - Add `frontprompt show <url> --session-id <label>` (and/or env `FRONTPROMPT_SESSION_ID`). When set, `session_lifecycle` uses the label instead of `new_session_id()`; the session dir becomes `~/.cache/frontprompt/sessions/<label>/` with a fixed socket at `…/<label>/show.sock`.
  - The dev loop uses `--session-id dev`. Every debug command can then target `--session dev` deterministically, and discovery still works (`session.json` is written the same way).
  - Guard: if a live session with that label already exists (`_pid_alive`), refuse to start (or take over after teardown) — never two writers on one label.

**Verdict:** ship **A** as the immediate, zero-risk path; add **B** (`--session-id`/`FRONTPROMPT_SESSION_ID`) as the first-class durable answer to "we need *the* session." B is the smallest change in `ipc/session.py` (`session_lifecycle`) + `ipc/paths.py` (already has `new_session_id`; just bypass it when a label is supplied) + the `show` command signature.

### Lifecycle

| Phase | Mechanism (existing) |
|---|---|
| Create | `frontprompt show <url>` → `ShowSession.run()` → `session_lifecycle` writes `session.json` + binds `show.sock` |
| Discover | `discover_sessions()` / `pick_latest_session()` (`ipc/session.py`), surfaced by `frontprompt sessions list` |
| Reuse | every debug command resolves via `_resolve_session(--session else latest)` |
| Teardown | Ctrl+C / tab-close → `session_lifecycle` cleanup; orphans reaped by `frontprompt sessions prune` |

State (picks/regions/relations) is global and reloaded on every start (per the [SQLite-persistence design](2026-05-31-sqlite-persistence-design.md) — `origin_session`, steal-on-mutate). **Consequence that strengthens the restart-based reload below:** a session restart does **not** lose annotations; only ephemeral selection resets.

---

## 3. Interaction surface (the core ask)

New **write/debug** subcommands, each mirroring the existing read-only ones exactly: resolve session via `_resolve_session`, `query()` the socket with an existing `IpcRequest`, print JSON. **No new protocol.** This is the feature that retires the hand-written socket harness.

### DRY refactor first (scout-mode)

Every read-only subcommand today repeats the same block: build request → `anyio.run(_run)` → `try query except IpcConnectError → exit 3` → `if not response.ok → exit 3` → `_emit_json(response.data)`. Extract one helper and route **all** subcommands (old and new) through it:

```
def _query_session(session_id: str | None, request: IpcRequest,
                   *, not_ok_exit: int = 3) -> Any:
    """Resolve session (or exit 2), run the IPC round-trip, handle connect/timeout
    (exit 3) and ok=False (exit `not_ok_exit`), and return response.data."""
```

This keeps the new commands DRY with the MCP surface (identical `IpcRequest` construction) and shrinks each subcommand to ~3 lines.

### Command catalogue

All commands accept `--session <id>` (default: latest). Output is `_emit_json(...)` (UTF-8, indent 2) unless noted.

| CLI command | `IpcRequest` | Notes / output |
|---|---|---|
| `frontprompt navigate <url> [--session ID]` | `NavigateRequest(url=url)` | prints `{navigated_to, title}` (`PageInfo`-ish dict from `page_controller.navigate`) |
| `frontprompt eval <expression> [--session ID] [--pick PICK_ID] [--mutating]` | `EvalJsRequest(expression, pick_id_arg=pick, mutating=flag)` | prints `EvalJsResult` payload (`{ok, result, error}`); `--mutating` invalidates the snapshot server-side |
| `frontprompt page-info [--session ID]` | `GetPageInfoRequest()` | prints `PageInfoResult` (`url, title, viewport, scroll, ready_state`) |
| `frontprompt screenshot [PATH] [--session ID] [--full-page] [--pick PICK_ID] [--padding N]` | `ScreenshotPageRequest(full_page)` **or**, when `--pick`, `ScreenshotElementRequest(pick_ids=[pick], padding)` | base64 is **decoded to a PNG file**, never dumped to stdout; default `PATH` = `./frontprompt-<session>-<ts>.png`; prints `{path, width, height, bytes}` |
| `frontprompt pick selector <css> --comment <c> [--limit N] [--parent PICK_ID] [--session ID]` | `PickBySelectorRequest(...)` | prints `PickCreatorResult` (`pick_ids, total_matches, captured`) |
| `frontprompt pick text <text> --comment <c> [--role R] [--limit N] [--parent PICK_ID] [--session ID]` | `PickByTextRequest(...)` | mirrors MCP `frontprompt_pick_by_text` |

Signature conventions match the existing Click group (`@main.command`, `@click.option("--session", "session_id", default=None, …)`, `@click.argument(...)`). `pick` is a `@main.group` with `selector`/`text` subcommands, parallel to the existing `picks` (read) and `sessions` groups — note the singular/plural split keeps "create picks" (`pick`) distinct from "inspect picks" (`picks`).

**Exit-code contract** (inherited from the read-only commands): `2` = no/!found session, `3` = connect/IPC error or `ok=False`, with `4` reserved where a not-found sub-resource deserves its own code (as `picks get` already does).

### Optional, low-cost additions (agent-ergonomic, same pattern)

`frontprompt outline` → `GetPageOutlineRequest`, `frontprompt html` → `GetPageHtmlRequest`, `frontprompt summary` → `GetStateSummaryRequest`, `frontprompt comments` → `GetCommentsRequest`. Each is a 3-line command via `_query_session`. Recommend shipping `summary` and `outline` with the core set; the rest on demand (YAGNI).

### Why this is the right surface

These commands are the CLI projection of the MCP tool surface (`frontprompt_navigate`, `frontprompt_eval_js`, `frontprompt_screenshot_page`, `frontprompt_pick_by_selector`, …). One protocol, two front-doors (MCP for the agent-in-session path; CLI for the dev/debug path). An agent that previously wrote a socket script now runs `uv run frontprompt eval '…'` — discoverable via `--help`, testable, and provenance-checked.

---

## Hot-reload verdict

**Verdict: true in-page hot-swap (keep the page, swap the bundle) is NOT cleanly feasible with the current architecture. The correct, deterministic reload is to restart the `show` session. A `--watch` loop means watch-and-respawn, not in-page reload.**

Evidence, from the code:

1. **The bundle is captured once, at startup.** `ShowSession.run()` calls `load_overlay_bundle()` once (`show_session.py:300`), builds `OverlayInjector(scaffold_script=bundle)`, and `install_init_script()` registers it via Playwright `page.add_init_script` **before** the first `navigate` (`show_session.py:423-425`, `browser/manager.py:256-291`, `overlay/injector.py:107-139`).
2. **`add_init_script` is append-only.** Playwright has no remove-init-script API. Registering a *second* (fresh) bundle does not replace the first; both are queued.
3. **The scaffold is idempotent by contract.** It no-ops if `#__frontprompt_overlay_host__` already exists (`injector.py` docstring point 1). So on the next navigation/reload, the **old** init script runs first, mounts the host and sets the ready flag; the **new** one runs second, sees the host, and no-ops. The page therefore keeps the **old** overlay across navigation — re-injection is defeated by the idempotency guard.
4. **Re-evaluating into the live page is equally blocked.** `browser.evaluate(new_bundle)` hits the same idempotency no-op unless you first tear down the host element, clear `window.__fp`, and reset the ready flag — and even then the bridge wiring (`page.expose_function("__fp_internal_state_getter", …)`, the per-session `integrity_token` seed, the 17 `bridge.on(...)` handlers; `show_session.py:339-421`) is established once per `_run_browser` and is not designed to be re-established against a mutated `__fp` singleton. The `window.__fp`-only namespace rule (arch-test enforced) makes a clean in-place teardown/re-mount fragile.

Because `load_overlay_bundle()` reads fresh on every process start, **restarting `show` is the clean propagation path** — and, per [§2](#2-session-management--one-stable-dev-session), annotations survive the restart (global persistence), so the restart is non-destructive to user state.

**`--watch` feasibility:** feasible as *session-restart reload* — a filesystem watch on `frontend/dist/` (the vite output) that, on change, kills the dev `show` and respawns it at the same URL (and, with Approach B, the same `--session-id dev`, so the socket path is stable across the restart). This is the realistic, low-magic hot-reload. A true zero-flicker in-page swap is explicitly a non-goal.

---

## 4. One ergonomic loop

A single script: `scripts/dev-session.sh` (sibling to `scripts/install-hooks.sh`). No Make/just (none exist in-repo).

Behaviour of `bash scripts/dev-session.sh [URL]` (default `URL=about:blank`):

1. `uv run python -m frontprompt.build` — codegen → vite → **embed** (the canonical build already re-embeds `_overlay/` every run; see [§5](#5-consistency--health) for why this keeps precedence consistent).
2. Tear down any prior dev session: `uv run frontprompt sessions prune`, and if Approach B is in place, SIGTERM the holder of the `dev` label.
3. Start exactly one dev session in the background: `uv run frontprompt show "$URL" --session-id dev` (Approach B) or plain `… show "$URL"` (Approach A), detached, logging to the session dir.
4. Wait for readiness by polling `uv run frontprompt ping` until `ok` (the `show` process also prints the `frontprompt:ready <id>` line; the script may parse it instead).
5. Print the resolved session id + socket path and exit, leaving the session running and driveable via the [§3](#3-interaction-surface-the-core-ask) commands.

`--watch` variant (`bash scripts/dev-session.sh --watch [URL]`): after step 4, watch `frontend/dist/` (or `frontend/src/`, rebuilding on change) and re-run steps 1–4 on change — i.e. **rebuild + respawn**, per the hot-reload verdict. Keep the watcher dependency-light (a simple `fswatch`/poll loop; no new Python deps).

> Note on the atlas Bash-output discipline: a `--watch` loop is long-running; launch it with `run_in_background` and a `# focus:` hint rather than piping its output through filters.

---

## 5. Consistency / health

### The bundle-precedence trap (and why the canonical build avoids it)

`overlay/loader.py` resolves **embedded `_overlay/` first, dev `frontend/dist/` second**. `build/__main__.py` **always** runs `_embed_into_package()` (`build/__main__.py:194`) — so after any canonical build, `_overlay/` exists and *shadows* `frontend/dist/`. The dev fallback path is therefore effectively dead once you have built at least once.

**This is fine *as long as the dev loop runs the full `python -m frontprompt.build` each iteration*** (which re-embeds the freshest bundle). The trap only bites if someone re-runs vite alone (writing `frontend/dist/`) while a stale `_overlay/` lingers — then the loader serves the stale embedded copy. Two defenses:

- **Primary (process discipline):** the dev loop always calls the full build, which re-embeds. No env override needed. Embedding is two `shutil.copy2` calls — negligible cost, so there is no reason to skip it.
- **Optional (explicit force-dev override):** add `FRONTPROMPT_OVERLAY_SOURCE = dev|embedded|auto` honored in `loader._resolve` (`auto` = today's behaviour). `dev` forces `frontend/dist/`, defeating any stale `_overlay/`. Ship only if a vite-only fast path is later wanted; not required by the primary loop.

### Doctor checks (`frontprompt doctor`, new — or extend `bootstrap`)

A read-only health command that reports:

- **Overlay bundle present** and from where (embedded vs dev) — reuse `load_build_manifest()` (already done in `bootstrap_command`, `cli.py:294-306`).
- **Bundle freshness:** warn if the newest mtime under `frontend/src/` is later than `frontend/dist/build-manifest.json:generated_at_iso` → "overlay source changed since last build; run the dev loop."
- **Stale-embed warning:** if both `_overlay/` and `frontend/dist/` exist and their `build_session` UUIDs differ → "embedded overlay is older than the dev build" (the exact trap above).
- **Provenance triple:** print package version, overlay `build_session`, `IPC_SCHEMA_VERSION`, overlay `schema_version`. A running session's bridge already handshakes `build_session` at `wait_until_ready` and logs a mismatch (`show_session.py:428-435`) — surface that as a doctor line too.
- **Sessions:** count alive sessions (`discover_sessions()`); flag >1 dev session as an ambiguity risk for `latest` resolution.

### Local↔plugin drift

The plugin runs the **published** wheel (`uvx --from frontprompt`); the dev loop runs the **working tree** (`uv run`). They are intentionally allowed to differ. Drift is *detected*, not prevented: the doctor's provenance triple makes the difference visible, and the bridge `build_session` handshake guarantees a running overlay and its daemon agree at the binary-bundle level regardless of which path launched them.

---

## 6. DEVELOPMENT.md update plan

Add/extend these sections (the file already has "Using the MCP server: published vs local dev" and "Running it"):

1. **"The dev session loop" (new, after "Running it").** Document `bash scripts/dev-session.sh [URL]` and `--watch`; state the one-dev-session invariant; show the create→drive→teardown cycle.
2. **"Driving a running session from the CLI" (new).** Table of the [§3](#3-interaction-surface-the-core-ask) debug commands with one example each (`uv run frontprompt navigate …`, `… eval '…'`, `… screenshot out.png`, `… page-info`, `… pick selector …`). Explicitly state: **this replaces hand-written socket scripts.**
3. **"Stable dev session" (new sub-section).** Document `--session-id dev` / `FRONTPROMPT_SESSION_ID` (Approach B) and the `--session` targeting flag.
4. **"Rebuild propagation & hot-reload" (new).** State the verdict: a rebuild does not reach a running session; the loop restarts it; annotations survive (global persistence). Cross-link this spec.
5. **Extend "The overlay build pipeline".** Add the bundle-precedence trap note (embedded shadows dev; the loop re-embeds every run) and the optional `FRONTPROMPT_OVERLAY_SOURCE` override.
6. **"Health: `frontprompt doctor`" (new).** What it checks (provenance triple, bundle freshness, stale-embed, session count).
7. **Scout fixes to fold in:** the `cli.py` module docstring (`cli.py:5-9`) lists only `mcp`/`show`/`bootstrap` and is stale (omits `sessions`/`state`/`picks`/`ping`); update it to enumerate the read + new debug subcommands.

---

## Implementation surface summary (for planning)

| Change | File(s) | Size |
|---|---|---|
| `_query_session` helper + reroute read-only cmds | `src/frontprompt/cli.py` | refactor, no behaviour change |
| New debug subcommands (`navigate`, `eval`, `page-info`, `screenshot`, `pick` group, `summary`/`outline`) | `src/frontprompt/cli.py` | additive, existing `IpcRequest` types |
| Stable session label (Approach B) | `src/frontprompt/ipc/session.py`, `src/frontprompt/ipc/paths.py`, `show` command | small |
| Dev loop script (+`--watch`) | `scripts/dev-session.sh` | new |
| `frontprompt doctor` | `src/frontprompt/cli.py` (+ small loader/manifest reads) | additive |
| Optional `FRONTPROMPT_OVERLAY_SOURCE` | `src/frontprompt/overlay/loader.py` | optional |
| Docs | `DEVELOPMENT.md` | edits per [§6](#6-developmentmd-update-plan) |

TDD note (per repo conventions): the CLI debug commands are unit-testable with a Click runner against a fake socket (the read-only commands already establish this pattern); the stable-label session and the doctor checks get round-trip tests; the dev script gets a smoke test that asserts the one-session invariant.

## Open questions for the user

1. **Approach A vs B for the stable session:** ship the zero-code "latest == dev session" path first, or go straight to a labeled `--session-id dev` (small change to `session_lifecycle`)? Recommendation: both, B as the durable answer.
2. **Screenshot output:** default to writing a PNG file (recommended — base64 to stdout is hostile to terminals and the atlas Bash-output hook) and print the path, or also offer `--stdout-base64` for piping?
3. **`frontprompt doctor` vs extending `bootstrap`:** new top-level `doctor` command, or fold the health checks into `bootstrap --check`?
4. **`--watch` watcher dependency:** acceptable to shell out to `fswatch` if present (poll-loop fallback), or keep it pure-poll to avoid an external tool assumption?
5. **`FRONTPROMPT_OVERLAY_SOURCE`:** include the explicit force-dev override now, or rely solely on "the loop always re-embeds" until a vite-only fast path is actually wanted?

## Cross-refs

- [SQLite-persistence design](2026-05-31-sqlite-persistence-design.md) — global state + `origin_session`; why a session restart preserves annotations.
- [MCP scout-tools design](2026-05-24-mcp-scout-tools-design.md) / [refinement v0.4.0](2026-05-26-mcp-scout-refinement-v0-4-0-design.md) — the MCP tool surface these CLI commands mirror.
- `ARCHITECTURE.md` — overlay injection model, `window.__fp` namespace discipline, build pipeline.
- `DEVELOPMENT.md` — local-scope MCP shadow, build pipeline, dev-state-is-disposable.
