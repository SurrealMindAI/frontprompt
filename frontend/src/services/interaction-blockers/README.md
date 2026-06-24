# interaction-blockers — overlay-reachability diagnostics

## What it does

Detects mechanisms in the host page that would **block normal interaction** with
our overlay. Three signals tracked:

1. **`inert` attribute** on ancestors of our overlay host element.
2. **`aria-hidden="true"`** on ancestors.
3. **Focus theft** — events where the focus moves to elements outside our overlay
   while the user is interacting with us.

When at least one signal flips state, a diagnostic line is logged to the page's
console (DevTools console). Format: `[fp interaction-blockers] {...}`.

## Why "blockers", not "hostile"

The name is **intentionally intent-neutral**. A page might set `<body inert>` for
many legit reasons:

- Modal dialog opens (Material Design pattern — sets inert on background so
  focus + clicks can't escape the modal).
- ARIA-modal pattern for accessibility.
- Loading overlay during async operations.

The page is not "hostile" — it's following standard web platform conventions.
But the **effect on us** is the same as if it were: our textarea becomes
unfocusable, our keyboard input goes nowhere.

So we detect the mechanism, not the intent. "Hostile environment" was the
original name and was overly dramatic. `interaction-blockers` describes what
gets blocked (our interaction surface).

## What each signal means

### `inert` ancestor

Per HTML spec: any element inside an `inert` subtree is **non-interactive**:

> The element and its flat tree descendants are to be made inert by the user
> agent. Inert elements receive no events, focus is impossible, and pointer
> interactions are suppressed.

The HTML spec explicitly states that inert **inherits** with no opt-out for
descendants. If the page sets `<body inert>`, our overlay (a child of body)
becomes inert — even with shadow DOM CSS isolation. We mount our host on
`<html>` (`documentElement`) instead of body to escape this case.

**Common triggers**: MD dialogs, MUI Modal component, aria-modal libraries.

### `aria-hidden="true"` ancestor

ARIA convention to hide content from assistive technologies. Modern modal
patterns also use it together with `inert` or as a fallback.

**Effect on us**: screen readers ignore our overlay, but visual + keyboard
interaction often still works. Less catastrophic than `inert` but reportable.

### Focus theft

A page-level focus trap (e.g., custom `focusin` listener that re-focuses the
modal) will move focus away from our textarea right after the user clicks it.
We count events where focus shifts outside our overlay's subtree while we
expected to keep it.

**Effect on us**: keystrokes go to the page (or nowhere). Textarea can't accept
input.

## When to enable

Default: **off**. Diagnostic output is noisy (logs every 2s on state change)
and never helps a regular user — it's purely a developer-side investigation
tool.

Enable for one of these:

- Page won't accept our textarea input → check if any ancestor is `inert`.
- Page seems to refuse focus → check focus-theft counter.
- Suspected accessibility-blocked overlay → check `aria-hidden`.

Activation: `localStorage.setItem('fp-dev', '1')` in DevTools console, then
reload the page. State is per-origin, persists across navigations.

## Output format

Every 2 seconds, IF state changed since last report:

```
[fp interaction-blockers] {
  inertAncestors: ["body", "html"],
  ariaHiddenAncestors: ["body"],
  activeElementTag: "textarea#fp-comment",
  focusStolenEventsSinceLast: 0,
  ts: "2026-01-01T12:34:56.789Z"
}
```

Empty arrays = no blockers detected. `activeElementTag` shows where focus is
right now (useful to detect focus-trap states).

## How it's wired

`main.ts` calls `startInteractionBlockersMonitor(host)` after overlay mounts,
ONLY when DEV-flag is on. Service installs:

- `setInterval(snapshot, 2000)` — periodic state check.
- `document.addEventListener('focusin', ..., { capture: true })` — for theft counter.

Never cleaned up — lives for page lifetime. Harmless (single interval +
single capture-phase listener).
