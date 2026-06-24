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
