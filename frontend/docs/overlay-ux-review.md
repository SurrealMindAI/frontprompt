# Overlay UX/UI review & redesign concept

Evidence-based review of the frontprompt in-page HUD overlay (`frontend/src/`),
focused on the **control surface**: elegance, UX, accessibility, and a UI-test
strategy. Findings are tagged **[FIXED]** (landed on this branch) or
**[PROPOSED]** (designed here, not yet built). No findings are speculative —
each cites the evidence that motivated it.

## Method

Read every control component, the design-token layer, and the customElement
composition root; quantified the control surface with `grep`/`svelte-check`;
built a real-Chromium visual + a11y harness to verify the rendered result. The
baseline before this work: **1182 vitest tests green, svelte-check 0 errors**.

## Control surface (inventory)

The HUD is a 3×3 CSS grid (`top/left/center/right/bottom`) of `Panel`s inside a
shadow-DOM custom element. Controls, grouped:

- **Toolbar** (`components/Toolbar.svelte`) — brand mark + 4 clickable `StatPill`s
  (events / picks / regions / relations), each with an inline visibility toggle.
- **Left panel** — tool strip (`LeftPanelTools`) + tabbed lists
  (`TabbedPanel`): picks, regions, relations, events, recordings, settings.
- **Right panel** — context details + editors (`CommentEditor`,
  `AssertionEditor`, `PickDetails`, `RegionDetails`, `RecordingDetails`,
  `ReplayReportView`).
- **Inspector layers** (full-viewport) — `InspectorLayer` (pick), `DrawRegionLayer`
  (region draw), `QuickCommentBox`, `RelationsLayer`, `HighlightBorder`.
- **Floating recorder toolbar**, **DebugPanel**, **Dashboard** (about:blank).
- **Shared primitives** — `lib/primitives/` (Button, Badge, StatusDot) +
  `components/primitives/` (Dropdown, TabbedPanel, PickButton, NodePicker,
  StatMetric, StatPill).

Overall the surface is **mature and well-built**: the team already applies
strong a11y semantics by hand (`type="button"`, `aria-pressed`, `aria-label`,
`title` on toggles) and has a real token layer. The gaps below are systematic,
not sloppiness.

## Findings

### A. Keyboard focus is mostly invisible — [FIXED]

`:focus-visible` styling existed in only **5** components, while the surface has
**62 `<button>`s**. Keyboard users couldn't see where focus was (WCAG 2.4.7).
→ Added one branded `:global(:focus-visible)` outline on `.grid` in `App.svelte`,
driven by `--fp-focus-ring-*` tokens, scoped to the shadow root. Component-level
focus styles keep higher specificity and still win where present.

### B. Motion ignores `prefers-reduced-motion` — [FIXED]

Only **1** component guarded reduced motion, against **~50** transitions.
→ Added a `@media (prefers-reduced-motion: reduce)` guard on `.grid` that
collapses all transitions/animations to near-instant (WCAG 2.3.3).

### C. Icons are Unicode glyphs — [FIXED for toolbar, PROPOSED for the rest]

The visibility toggles used `◉`/`○`. Glyph "icons" render inconsistently across
OS/font and carry no semantics. → Introduced an `Icon` primitive
(`lib/icons/`, crisp lucide-style inline SVG, decorative-by-default a11y) and
migrated the toolbar toggles to `eye`/`eye-off` (clearer meaning *and* stable
rendering). **[PROPOSED]** migrate the remaining glyphs (`✕` close, `▾` chevron,
`●` status, `↻` etc.) icon-by-icon, updating the few tests that assert a glyph
(`LeftPanel.test.ts` asserts `●`).

### D. Inspector pick surface had no role/name — [FIXED]

`InspectorLayer`'s full-viewport `<div>` captured pointer events with no ARIA
role or name. → Added `role="application"` + an accessible name describing the
move/click/Escape interaction.

### E. Design tokens are duplicated, not shared — [PROPOSED, no-op justified]

`lib/tokens/*.css` + `theme/dark.css` are consumed by the **marketing site**
(`site/`), **not** the overlay — the overlay re-declares its tokens inline on
`.grid` because an injected IIFE bundle can't `@import` external CSS. This is a
*justified* divergence, not a bug; documenting it here so it isn't "fixed" by
deleting the files (which would break the site) or by a fragile shared import.

### F. Tooltips are native `title=` — [PROPOSED]

Discoverability relies on the browser's native tooltip (slow ~1s delay,
unstyled, invisible to touch/keyboard). A small branded `Tooltip` primitive (and
adopting it on icon-only controls) would improve affordance — but it touches many
call sites, so it's proposed, not landed, to keep this branch regression-free.

## Redesign concepts (new ideas, prioritized)

1. **Command palette** (`⌘K`) — a fuzzy launcher for every HUD action (toggle
   overlays, open tabs, start/stop recording, pick, draw region). Keyboard-first
   power-user surface; the HUD already has a keyboard service to build on.
2. **Density / compact mode** — a `--fp-density` token scaling spacing+font so the
   HUD shrinks on small viewports or when the user wants more page visible.
3. **`IconButton` primitive** — codify the icon + mandatory `aria-label` +
   focus-ring + tooltip pattern the team applies by hand, once the Icon and
   Tooltip primitives exist; then migrate icon-only controls onto it.
4. **Empty/loading states** — explicit, friendly empty states for the picks /
   regions / relations / recordings lists (currently terse).
5. **Keyboard-shortcut help** (`?`) — a discoverable cheatsheet overlay.

## UI testing strategy ("was gibt's noch?")

Built on this branch (see [`tests/browser/VISUAL_HARNESS.md`](../../tests/browser/VISUAL_HARNESS.md)):

- **Visual regression** — computed-style + geometry snapshot diff of the rendered
  chrome vs a committed JSON baseline (deterministic, no image lib).
- **Accessibility audit** — every control has an accessible name; focus-ring +
  reduced-motion present in the rendered shadow root.
- **Performance budget** — overlay bundle gzip/raw size ceiling.
- **Semantic/interaction** — the existing vitest + Testing Library layer.

Deliberately **not** classic Lighthouse: it scores host pages, not an injected
widget — rationale in the harness doc. Future layers worth adding: stateful
visual fixtures (storybook-style seeded states), cross-host-page contrast
checks, and a full keyboard-traversal map.
