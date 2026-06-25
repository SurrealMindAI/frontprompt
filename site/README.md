# site — frontprompt marketing + docs

The public site at **https://surrealmindai.github.io/frontprompt/** — a single
Svelte SPA that serves the marketing landing page and the documentation.

## Markdown is the single source of truth

This site **does not** contain documentation prose. It renders the repo's
existing Markdown:

| Surface | Source |
| ------- | ------ |
| Landing hero, install, usage | [`../README.md`](../README.md) |
| Docs → Overview | [`../README.md`](../README.md) |
| Docs → Architecture | [`../ARCHITECTURE.md`](../ARCHITECTURE.md) |
| Docs → Guides | [`../docs/*.md`](../docs/) |
| Docs → Services | `../frontend/src/services/*/README.md` |
| Docs → Specs | [`../docs/specs/*.md`](../docs/specs/) |
| Docs → Project | [`../DEVELOPMENT.md`](../DEVELOPMENT.md), [`../CONTRIBUTING.md`](../CONTRIBUTING.md) |

The **only** site-authored content is [`content/landing.md`](content/landing.md)
— the marketing feature cards and how-it-works steps, which exist nowhere else.
Edit the docs in their canonical files; the site picks the changes up on the
next build.

The design system is frontprompt's own — the site imports the tokens from
[`../frontend/src/lib/tokens`](../frontend/src/lib/tokens) so the page and the
in-page overlay speak the same visual language. On top sits an "inspector / HUD"
aesthetic layer in [`src/app.css`](src/app.css).

## Develop

```bash
cd site
bun install
bun run dev       # http://localhost:5173/frontprompt/
bun run build     # → site/dist (what Pages serves)
bun run preview   # serve the production build locally
```

## Versioning

`site/package.json`'s version is part of the repo-wide version-consistency gate
(`scripts/check_versions.py`) — it must always equal the shipped frontprompt /
plugin version, so the published site can never advertise a version the tool
doesn't ship.

## Deploy

Pushing to `main` with changes under `site/`, `docs/`, a top-level `*.md`, or
the shared tokens triggers [`.github/workflows/pages.yml`](../.github/workflows/pages.yml),
which builds and deploys to GitHub Pages.
