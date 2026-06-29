# Security Policy

## Supported versions

frontprompt is pre-1.0; only the latest released version receives security fixes.

| Version | Supported |
|---------|-----------|
| 0.1.x   | ✅ |
| < 0.1   | ❌ |

## Reporting a vulnerability

Please report security issues **privately** — do not open a public issue.

- Preferred: GitHub's [private vulnerability reporting](https://github.com/SurrealMindAI/frontprompt/security/advisories/new).
- Or email **admin@surrealmind.ai** with `frontprompt security` in the subject.

Include a description, affected version, reproduction steps, and impact. We aim to
acknowledge within a few working days and will coordinate a fix and disclosure
timeline with you.

## Threat model

frontprompt is a **local developer tool**, and its security posture reflects that:

- **No inbound network listener by default.** The MCP server speaks over **stdio**;
  the overlay talks to Python through Playwright's `expose_function`, not HTTP. The
  live-session debug API is a **read-only** Unix domain socket under
  `~/.cache/frontprompt/sessions/<id>/show.sock`, scoped by filesystem permissions.
- **It drives a real browser over agent control.** The MCP tool surface includes
  page-mutating and script-executing capabilities (e.g. `eval_js`, `dom_patch`,
  `navigate`). Treat the MCP server as a **trusted-agent-only** surface — anyone
  who can call its tools can run JavaScript in, and navigate, your browser.
- **Untrusted page content.** Visiting arbitrary URLs carries the normal risks of
  running a browser against hostile pages. The overlay is isolated in a shadow DOM,
  and Chromium runs with its standard sandbox.
- **Local data at rest.** Annotations (picks, regions, relations, recordings) and
  any voice-over audio are stored locally in the SQLite state DB and the session
  cache. Screenshots may capture whatever is on the page — handle exported
  artifacts accordingly.

## Dependency posture

frontprompt pins **`scrapling==0.4.8`** exactly and uses it only as an lxml-backed
HTML parser for DOM fingerprint matching, isolated behind
`analysis/_impl/scrapling_bridge.py` so it can be swapped without touching the rest
of the codebase (the browser itself is driven by Playwright, not Scrapling). A CI drift
gate keeps the generated TypeScript types in lock-step with their Pydantic source
of truth. See [CONTRIBUTING.md](CONTRIBUTING.md) and the
[Architecture Decision Records](docs/adr/index.md) for the rationale.
