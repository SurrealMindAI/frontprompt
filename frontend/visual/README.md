# Overlay visual-regression + a11y harness

Screenshot + accessibility coverage for the `<fp-overlay>` HUD, complementing
the jsdom unit/component suite (which is blind to real layout, CSS custom-property
cascade across the shadow boundary, z-index stacking, and contrast).

## What it does

`visual/harness.ts` mounts the **real** overlay custom element in a normal browser
page with a deterministic, fully offline stub of the Python bridge
(`window.__fp`). No Python daemon, no network: `getState()` returns `null`, which
is the documented cold-boot path, so the overlay renders its default chrome.

Playwright then:

1. **Visual regression** — screenshots `#__frontprompt_overlay_host__` and diffs it
   against the committed baseline under `tests-visual/__screenshots__/`.
2. **Accessibility** — runs axe-core (WCAG 2 A/AA) against the overlay. The suite
   gates on `critical` findings; `serious`/`moderate` findings are logged
   (non-gating) so the baseline reflects the overlay's real a11y posture honestly.

Determinism comes from the Playwright config: fixed `1280×800` viewport, DPR 1,
`reducedMotion: 'reduce'`, frozen CSS animations, dark color scheme.

## Run it

```bash
cd frontend
bun run test:visual          # compare against committed baselines + run axe
bun run test:visual:update   # (re)generate the screenshot baselines
```

Requires the Playwright browser once: `bunx playwright install chromium`.
The Vite dev server for the harness is started automatically by
`playwright.config.ts` (`webServer`).

## Scope notes

- **Lighthouse is intentionally not wired here.** The overlay is an injected
  shadow-DOM layer, not a navigable route — a Lighthouse run measures the *host*
  page, not the HUD, so its perf/SEO/PWA audits are meaningless for this surface.
  axe-core (accessibility) + pixel diffing are the on-target signals. Lighthouse
  belongs against the standalone marketing `site/`, if anywhere.
- The cold-boot baseline locks the **chrome** (toolbar, panel tabs/laschen). Seeded
  state variants (populated picks/regions/recordings) would extend coverage by
  feeding `getState()` a real `StateSnapshot` instead of `null`.
- Baselines are committed; `test-results/` and `playwright-report/` are gitignored.
