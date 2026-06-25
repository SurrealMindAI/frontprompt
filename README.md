# frontprompt

**Annotate any web page, and drive it from an AI agent.**

frontprompt is a Python tool that opens a real (headful) Chromium browser and
injects an in-page overlay — a shadow-DOM HUD — onto whatever page you point it
at. You click to **pick** elements, drag to capture **regions**, and draw typed
**relations** between them. The same process runs an **MCP server**, so an AI
agent can navigate the browser, query the page, create picks, and read your
annotations as structured state.

The headline property: **your annotations survive cross-origin navigation.**
State is authoritative in the Python process, not in the page, so navigating
from one site to another never loses your picks. See
[ARCHITECTURE.md](ARCHITECTURE.md) for how that works.

## Status

**Alpha.** The interactive inspector is feature-complete and the MCP server
exposes a working tool set (pick, navigate, screenshot, page-read, state-read).
Some capabilities are intentionally deferred — see
[ARCHITECTURE.md § Scope](ARCHITECTURE.md#scope-alpha).

## Install

### As a Claude Code plugin (recommended)

```bash
claude plugin marketplace add SurrealMindAI/frontprompt
claude plugin install frontprompt@frontprompt
```

The `frontprompt` MCP server is wired automatically: it launches via `uvx` from
PyPI and the Chromium browser self-installs on first use — zero manual setup.

### As a standalone CLI / MCP tool

frontprompt ships as a self-contained wheel — the Svelte overlay is embedded in
the package, so the installed tool needs no Bun or Node at runtime, and Chromium
auto-installs on first run.

```bash
uv tool install frontprompt
frontprompt bootstrap          # optional — eagerly pre-installs the Chromium driver
```

## Usage

```bash
# open a page with the inspector overlay
frontprompt show https://example.com

# run as an MCP stdio server for an AI agent
frontprompt mcp
```

Point your MCP client at `frontprompt mcp`. Each invocation owns its own private
browser session and spawns Chromium lazily on the first tool call, so startup
is instant. The server is ephemeral — one process per client session, it dies
when the client disconnects.

## Dependencies & risk

frontprompt pins **`scrapling==0.4.8`** exactly. scrapling is a BSD-3 page
extraction library that is, at the time of writing, effectively
single-maintainer (a bus-factor-1 project). To contain that risk it is used
behind a thin internal isolation boundary, pinned to one verified version, and
never auto-upgraded — so it can be swapped out without touching the rest of the
codebase if it ever needs to be.

## Documentation

- [ARCHITECTURE.md](ARCHITECTURE.md) — system design: cross-origin survival,
  the `expose_function` bridge, single-writer state, the MCP daemon, schema
  histories.
- [DEVELOPMENT.md](DEVELOPMENT.md) — dev environment, build pipeline, tests.
- [CONTRIBUTING.md](CONTRIBUTING.md) — how to contribute.

## License

BSD-3-Clause — see [LICENSE](LICENSE).
