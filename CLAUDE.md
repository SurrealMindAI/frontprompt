# frontprompt

MCP server for browser automation — an in-page Svelte 5 inspector overlay plus
programmatic page control via Playwright. **Pydantic is the single source of truth**;
the TypeScript overlay types are generated from it.

## Where things are

- **[DEVELOPMENT.md](DEVELOPMENT.md)** — contributor dev guide: setup, the overlay
  build pipeline, the restart-free dev loop, tests/types/lint, **local-first CI
  (`actionlint` + `act`)**, and state-DB overrides.
- **[ARCHITECTURE.md](ARCHITECTURE.md)** — system design, layer boundaries, state
  classification (local vs backend).
- **[CONTRIBUTING.md](CONTRIBUTING.md)** — branches, PRs, the codegen drift gate.
- **[docs/adr/index.md](docs/adr/index.md)** — Architecture Decision Records.

## Non-negotiables

- **Pydantic is the SSoT.** `frontend/src/_generated/` and `src/frontprompt/_overlay/`
  are gitignored build artifacts — never hand-edit them; regenerate via
  `uv run python -m frontprompt.build`. Keep the drift gate green (`uv run pytest -m drift`).
- **One namespace.** Only `window.__fp` — anything else fails the architecture tests.
- **State classification.** Durable, user-authored state is backend state; ephemeral
  page/UI state is local state. No ephemeral UI state in the Pydantic backend models.
- **Validate workflows locally** with `actionlint` before pushing — `ci.yml` and
  `pages.yml` have different build surfaces (see [DEVELOPMENT.md § Local-first CI](DEVELOPMENT.md#local-first-ci-github-actions)).

## Quick start

```bash
bash setup.sh                     # uv deps + chromium + bun + overlay build
uv run pytest -v                  # python tests (incl. real-Chromium under tests/browser/)
cd frontend && bun run test       # frontend vitest
actionlint                        # validate CI workflows
```
