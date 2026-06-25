# Contributing

Thanks for your interest in frontprompt. This is a short guide to getting set
up and landing a change. For the full dev workflow see
[DEVELOPMENT.md](DEVELOPMENT.md); for the design, [ARCHITECTURE.md](ARCHITECTURE.md).

## Set up

```bash
git clone <repo-url> frontprompt
cd frontprompt
bash setup.sh        # one-shot: uv deps + chromium + bun + frontend + overlay build
```

Or manually with `uv sync` plus `uv run python -m playwright install chromium`
and `uv run python -m frontprompt.build`. Details in [DEVELOPMENT.md](DEVELOPMENT.md#setup).

Install the git hooks once — the pre-push hook enforces version consistency:

```bash
bash scripts/install-hooks.sh
```

## Run the checks

Before opening a PR, run the same gates CI runs:

```bash
uv run ruff check src tests              # lint
uv run ruff format --check src tests     # format check
uv run mypy src/frontprompt              # python type-check
uv run pytest -v                         # python tests

cd frontend && bun run check             # frontend type-check
cd frontend && bun run test              # frontend tests (vitest)
```

## Keep the drift gate green

The TypeScript types under `frontend/src/_generated/` are generated from the
Pydantic models — they are the single source of truth. A CI **drift gate**
regenerates the types and fails if the working tree changes, which catches a
Pydantic edit that wasn't followed by a rebuild.

If the drift gate is red, rebuild and commit the (source) change properly:

```bash
uv run python -m frontprompt.build
```

Never hand-edit a generated type to satisfy the gate.

## Generated files are not committed

`frontend/src/_generated/` and `src/frontprompt/_overlay/` are gitignored build
artifacts. They are rebuilt by `python -m frontprompt.build` and shipped inside
the wheel — do not commit them.

## Releasing & version consistency

frontprompt is released as **one version** across six places — they must always
match, or a Claude Code plugin update stops mapping cleanly to a PyPI release:

- `pyproject.toml` `version`
- `src/frontprompt/__init__.py` `__version__`
- `.claude-plugin/plugin.json` + `plugin/.claude-plugin/plugin.json` `version`
- `.claude-plugin/marketplace.json` plugin `version`
- the pinned `uvx --from frontprompt==X.Y.Z` in `plugin/.mcp.json`

`scripts/check_versions.py` enforces this and runs in three places: the
**pre-push git hook** (`.githooks/pre-push`, installed via
`bash scripts/install-hooks.sh`) — which blocks a push on drift and, on a
`vX.Y.Z` tag push, also asserts the tag matches; **CI** (quality job); and the
**release workflow**, which refuses to publish a tag unless every version equals it.

To cut a release:

1. Bump all six versions to the new `X.Y.Z` (run `python scripts/check_versions.py`
   until it prints `OK`).
2. Commit and push to `main` — CI verifies consistency + the full suite.
3. Tag `vX.Y.Z` and push the tag — the release workflow re-checks the tag, builds
   the self-contained wheel, and publishes to PyPI.

## Branch and PR flow

1. Branch off `main`.
2. Make your change with a test first where it makes sense.
3. Run all the checks above locally.
4. Push and open a pull request against `main`.
5. CI runs lint, type-checks, tests, and the drift gate; keep them green.

Keep commits focused and messages in lowercase, imperative mood.

## License

By contributing you agree your contributions are licensed under the project's
[BSD-3-Clause License](LICENSE).
