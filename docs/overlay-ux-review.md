# Overlay UX & elegance review

Evidence-based review of the frontprompt **overlay** (the in-page Svelte 5
HUD: `frontend/src/`), focused on control elegance, UX, accessibility, and a
durable design-system foundation. Produced on branch `feat/overlay-ux`.

Method: read the design-system core (tokens, theme, primitives), the shell
(`App.svelte`, `main.ts`, bridge), and the control inventory; cross-checked
claims with `grep`/`svelte-check`/`vitest`; verified every change against the
green baseline (1182 vitest + svelte-check 0 errors).

---

## 1. What shipped on this branch

Two regression-free commits (foundation first, then its test net):

1. **Design-system foundation** (`overlay: hoist design tokens to :host …`)
2. **Visual-regression + axe harness** (`overlay: add Playwright …`)

| Change | Why it matters |
|---|---|
| Hoisted HUD tokens `.grid` → `:host` | The sibling layers (Inspector / Relations / Region-draw / FloatingRecorder) render **outside** `.grid` and never inherited the theme. `:host` reaches the whole shadow tree. |
| Added **motion** tokens (`--fp-duration-*`, `--fp-ease-*`) | There was no motion system; 31 components hardcoded ad-hoc transitions. |
| Added **elevation** scale (`--fp-z-*`), migrated all 9 hardcoded z-indexes | Two components both used `z-index: 100` (recorder toolbar vs dropdown) — an undocumented collision. The named scale encodes the documented stack. |
| One global `:focus-visible` ring | Keyboard focus was invisible on most controls (only 5 files had any focus style). |
| One global `prefers-reduced-motion` neutraliser | Only 1 of 31 animated components honoured it. Now the whole HUD does, from one rule. |
| Removed the unused `lib/` primitives tree (`lib/primitives`, `lib/theme`, `lib/types`, `lib/utils/cn`, barrels) | These had **0 importers, 0 tests** and were the *only* refs to scale tokens that never reached the shadow root. **Correction (post-branch):** `lib/tokens/*.css` was deleted here too but later **restored** — the static `site/` consumes it (see §2.1); only the primitives/theme/types/cn stayed gone. |
| Dropped unused `clsx` devDependency | Its only consumer was the deleted `cn.ts`. |

---

## 2. Headline findings (evidence)

### 2.1 The design-token system was half-dead *in the overlay* (but the site needs it)
- For the **overlay bundle**, `lib/tokens/*.css` + the (now-gone) `lib/theme/dark.css`
  were **not imported** (vite uses `emitCss:false` and forbids CSS imports — overlay
  styles must live in `.svelte`), so they never reached the overlay bundle.
- The live overlay defines its colour tokens **inline on `.grid`** (later hoisted to
  `:host`, see §1) and uses **only** `--fp-color-*`. The scale tokens
  (`--fp-radius/space/typography/shadow`) were referenced **only** by the dead
  `lib/primitives`, where they resolved to *nothing* in the shadow root.
- **Correction (post-branch):** this branch first deleted the whole `lib/` tree, but
  `lib/tokens/*.css` was **restored** — the static `site/` (`site/src/main.ts`)
  imports `lib/tokens/index.css` for the marketing/docs page, a normal CSS-import
  context where the tokens *do* ship pixels. So `lib/tokens` is live and consumed
  (by the site); only the genuinely-dead `lib/primitives`/`theme`/`types`/`cn` stayed
  removed. The overlay's own tokens live on `:host` as its single source of truth.

### 2.2 Colour is hardcoded, not tokenised — 32 files
`grep` finds raw `rgba()/#hex` in **32** component/service files, with a
recurring informal palette: `rgba(120,180,255)` (×50, a blue ≈ accent),
`rgba(157,255,177)` (green/success), `rgba(120,220,255)` (cyan/info),
`rgba(255,80,80)` (red/error), `#ffb400` (amber/warning)… The same handful of
semantic colours are re-typed by eye across the codebase. This is the biggest
remaining consistency/elegance lever (see §4.1).

### 2.3 No typography scale — sub-readable density
Hardcoded font sizes dominate: **`10px`×57, `11px`×50, `9px`×36, `12px`×24**,
down to `8px`. There is no type scale in use (the token one was dead). A 9–10px
floor is dense to the point of strain and fails comfortable-reading heuristics.

### 2.4 Icons are ad-hoc glyphs
Only **1** component uses inline `<svg>`. Everything else is emoji/glyph
(`⏺`, `⚡`, `×`) or text. No shared icon set → inconsistent weight/alignment,
no theming, variable screen-reader output.

### 2.5 Accessibility: good bones, real gaps
- **62** buttons, **41** `aria-label`, **63** `title`. ~21 buttons lean on
  `title` alone (not a robust accessible name; not keyboard-surfaced).
- The **serious nested-interactive** violation axe flagged (the relations status
  pill was a `<button>` containing a focusable descendant) is **fixed**: `StatPill`
  now renders its `action` snippet as a *sibling* of the clickable button, never
  nested inside it.
- Keyboard handling exists in 8 files but isn't systematic.
- Focus visibility was effectively absent → **fixed globally** this branch.

### 2.6 Doc drift (adjacent, noted for the parent review)
`DEVELOPMENT.md`'s project-layout omits `analysis/`, `ipc/`, `voice/`,
`scrapling/`. Out of scope for the overlay branch; flagged for the umbrella review.

---

## 3. Controls catalogue

Grouped by region (composition in `App.svelte`). All live in the shadow root.

| Region | Controls | UX notes |
|---|---|---|
| **Shell** | `App` grid (5 areas), `Panel`, `PanelResizer`, `PanelTab`, `TabbedPanel` | Grid-template animation is tasteful; now uses `--fp-ease-standard`. Resizer lacks an `aria` value surface (slider semantics). |
| **Toolbar (top)** | `Toolbar`, `StatPill`, `StatMetric`, `StatusDot`(component-local) | Status pills are dense; the relations pill's nested-interactive a11y bug is now fixed (`StatPill` renders `action` as a sibling, not nested). |
| **Left panel** | `LeftPanel`, `LeftPanelTools`, tabs: `Picks/Regions/Relations/Events/Recordings/Settings` + per-row `*Item` | Tab strip is the primary nav; would benefit from roving-tabindex + `role="tablist"`. |
| **Right panel** | `RightPanel`, `PickDetails`, `RegionDetails`, `RecordingDetails`, `CommentEditor`, `AssertionEditor`, `ReplayReportView` | Detail/editor surface; auto-opens on selection (nice). Editors are the densest text. |
| **Inspector layers** | `InspectorLayer`, `HighlightBorder`, `DrawRegionLayer`, `RelationsLayer`, `QuickCommentBox` | Full-viewport pointer surfaces. `InspectorLayer` has a static-element-interaction a11y warning. |
| **Recorder** | `FloatingRecorderToolbar` | Draggable chrome; now on the `--fp-z-chrome` tier. |
| **Dashboard** | `Dashboard`, `DashboardRow`, `DashboardSection` | about:blank landing; uses the `format` util (kept). |
| **Primitives** | `Dropdown`, `NodePicker`, `PickButton`, `PickPicker`, `StatPill`, `StatMetric` | `Dropdown` now on `--fp-z-popover` (above chrome). |

---

## 4. Recommended next concepts (roadmap)

Ordered by leverage. Each is regression-safe if done token-first + behind the
visual/axe harness now in place.

### 4.1 Semantic colour tokens + migration (highest leverage)
Promote the informal palette (§2.2) to `:host` semantic tokens —
`--fp-color-{accent,success,warning,error,info}` plus `-subtle`/`-strong`
steps — and migrate the 32 files onto them. One palette, themeable, contrast-
auditable. The visual baseline + axe catch any regression.

### 4.2 Typography scale
Define `--fp-text-{2xs…lg}` on `:host` (raise the floor to ~11px, line-height
tokens) and migrate the hardcoded sizes. Improves readability and rhythm.

### 4.3 Cohesive inline-SVG icon set
A small `Icon.svelte` + sprite of stroke-consistent 16px glyphs (record, stop,
pick, region, relation, comment, assert, settings, close). Replaces emoji;
gives uniform weight, `currentColor` theming, and `aria-hidden`/labelled use.

### 4.4 Command palette (⌘K) — convenience
A single fuzzy launcher over every overlay action (toggle inspector, start/stop
recording, quick-comment, open tab, toggle relations). High power-user payoff;
naturally keyboard-first. Mounts as a `--fp-z-popover` surface.

### 4.5 Density modes
`data-fp-density="comfortable|compact"` on `:host` switching spacing/type
tokens — lets the HUD breathe on large screens without losing the dense pro
layout. Pure-token, zero structural change.

### 4.6 a11y hardening
Give every icon-button an `aria-label`, add `role="tablist"`/roving-tabindex to
the tab strip, and `role="slider"` + `aria-valuenow` to `PanelResizer`. (The
nested-interactive pill from §2.5 is already fixed.)

---

## 5. Testing — what now exists and what's next

| Layer | State |
|---|---|
| Unit/component (vitest, jsdom) | 1182 green — strong on logic/DOM, **blind** to layout/CSS-cascade/contrast. |
| **Visual regression (Playwright)** | **Added.** Cold-boot baseline of the real overlay; deterministic. |
| **Accessibility (axe-core)** | **Added.** WCAG2 A/AA; gates on critical, logs serious. |
| Interaction/keyboard E2E | *Gap.* Playwright can now drive the harness (click laschen, ⌘K, pick flow). |
| Seeded-state visual variants | *Gap.* Feed `getState()` a real `StateSnapshot` to baseline populated panels. |
| Contrast assertions | *Gap.* Pairs naturally with §4.1 semantic tokens. |
| **Lighthouse** | **Intentionally not used** — the overlay is an injected shadow layer, not a route; Lighthouse would measure the host page. axe + pixel-diff are the on-target signals. (Lighthouse fits the standalone `site/`.) |

See `frontend/visual/README.md` for how to run the harness.
