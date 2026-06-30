# Overlay UI test harness

The overlay is an **injected, shadow-DOM custom element** (`<fp-overlay>`), not a
standalone page. That shapes which UI tests are meaningful: classic page-level
tools don't map cleanly onto a widget that lives inside arbitrary host pages.

## Layers

| Layer | Where | What it catches | Runs without a browser |
|---|---|---|---|
| **Semantic / interaction** | `frontend/src/**/*.test.ts` (vitest + Testing Library) | roles, `aria-pressed`, keyboard handlers, accessible names | ✅ yes (default suite) |
| **Visual regression** | [`test_overlay_visual_a11y.py`](test_overlay_visual_a11y.py) | structure + computed-CSS drift of the rendered chrome (colour/font/icon/markup; no geometry → portable) | ❌ real Chromium |
| **Accessibility audit** | same file | unnamed controls, missing focus-ring / reduced-motion in the *rendered* shadow root | ❌ real Chromium |
| **Performance budget** | [`../test_overlay_bundle_budget.py`](../test_overlay_bundle_budget.py) | bundle gzip/raw size ratchet | ✅ yes (needs a build) |

`vitest + jsdom` is **structurally blind to layout and computed style** (no
rendering engine) — it validates a11y *semantics* but never *visuals*. The
visual + computed-style layer therefore runs in real headless Chromium.

## Why not Lighthouse?

Lighthouse audits a **whole host page** (FCP/LCP/CLS, page-level a11y, SEO). The
overlay is a component injected over a *foreign* page, so a Lighthouse score
would measure the host site, not us. We substitute the parts that do apply to a
widget:

- **a11y** → in-page accessible-name + focus-ring + reduced-motion assertions
  against the rendered shadow root (the WCAG-relevant subset of Lighthouse's
  a11y category, scoped to the overlay).
- **performance** → a bundle **size budget** (the cost we actually impose on
  every navigation), instead of host-page paint timings.
- **visual** → a deterministic structure + computed-style snapshot diff, instead
  of full-page pixel scoring.

## Visual regression: structural + computed-style snapshot

Rather than pixel-diffing PNGs (which needs an image lib + tolerance tuning and
is noisy across machines), the harness snapshots a **structured** view of the
chrome — control counts, icon names, and ARIA state, plus key computed CSS
values (declared colours/fonts) but **no absolute geometry** — and diffs it
against a committed JSON baseline at
[`visual_baselines/overlay-chrome.json`](visual_baselines/). Dropping element
rects is deliberate: rect coordinates derive from system-font text metrics and
drift between the macOS author and the Linux CI runner, so the snapshot stays
portable. This is deterministic, diff-friendly in review, and catches the
regressions that matter (a control lost its colour, changed its ARIA state, or
reverted to a glyph icon). A full-page PNG is also written to
`visual_artifacts/` (gitignored) for the human-visual layout check.

## Running

```bash
# 1. build the bundle the harness renders
cd frontend && FRONTPROMPT_BUILD_SESSION=1 bunx vite build   # or: uv run python -m frontprompt.build

# 2. run the harness (integration-marked; skips if Chromium/bundle absent)
uv run pytest tests/browser/test_overlay_visual_a11y.py tests/test_overlay_bundle_budget.py

# regenerate the visual baseline after an intended UI change
FP_VISUAL_UPDATE=1 uv run pytest tests/browser/test_overlay_visual_a11y.py
```

## Future layers (not yet built)

- **Stateful visual fixtures** — seed `window.__fp.getState()` with canned
  snapshots (picks/regions/relations populated, recorder active, quick-comment
  mode) to snapshot the overlay in every meaningful state, storybook-style.
- **Cross-host-page contrast** — render over light *and* dark host backgrounds to
  prove the fixed-dark HUD stays legible everywhere.
- **Keyboard-traversal map** — assert full Tab order through the HUD controls.
