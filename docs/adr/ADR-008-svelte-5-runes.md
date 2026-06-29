# ADR-008 — Svelte 5 mit Runes als Frontend-Framework

> Part of the frontprompt [Architecture Decision Records](./index.md).

**Status**: accepted with amendment (2026-05-18: SvelteKit Static-SPA-Build explizit erlaubt)
**Date**: 2026-05-14
**Amendment-Date**: 2026-05-18
**Cross-References**: [ADR-003 Stack](./ADR-003-python-svelte-stack.md), `../user-directive-corrections.md` Korrektur 3, [ADR-010 Codegen-Pipeline](./ADR-010-codegen-pipeline.md), [ADR-015 Overlay in Page Main World](./ADR-015-overlay-in-page-main-world.md), 2026-05-18 Architecture Reset

---

## Context

Das Frontend des frontprompt-Successors ist das **Annotation UI**, das im externen Browser-Tab (nicht im automatisierten Tab) läuft. Es ist eine fokussierte Single-Purpose-Surface mit klar abgegrenzten Aufgaben:

- Empfang von WS-Push-Frames (Page-State-Updates, Annotation-Events, PointingSession-Lifecycle).
- HTTP-POST-Mutations zum Daemon (Pick-Submit, Comment-Submit, Idempotency-Key im Header).
- Visualisierung des aktuellen Page-State (DOM-Snapshot via Server-Side-Rendered Preview oder native iframe-Embed).
- Annotation-Workflow (User wählt ein Element, kommentiert es; das fließt zurück zum Daemon).

User-Korrektur 3 (`../user-directive-corrections.md`) hat das Framework auf **Svelte 5 mit Runes** festgelegt — autoritativ, gegen die Konsortiums-Empfehlung SolidJS.

---

## Decision

**Svelte 5** mit Runes (`$state`, `$derived`, `$effect`) ist das Frontend-Framework. Build-Tool: Bun 1.2.x (FE-only). Wire-Schemas: aus Pydantic generiertes Zod ([ADR-010](./ADR-010-codegen-pipeline.md)).

**Reaktivitäts-Modell**:

- WS-Push-Frames werden in `$state`-Cells dekodiert. Validierung via Zod auf Frame-Empfang (das ist der einzige Wire-Trust-Boundary auf Frontend-Seite).
- `$derived` propagiert Page-State-Updates in UI-State (z.B. "ist Pick-Modus aktiv?").
- `$effect` triggert Side-Effects: HTTP-POST bei Pick-Submit, UI-Highlight bei DOM-Update, Toast bei Error.

**Persistierter State**:

- **Keiner** im Frontend. Beim Tab-Reload geht der lokale UI-State verloren; die Wahrheit lebt im Daemon. WS-Reconnect mit Cursor (`../12-hub-final-synthesis.md` Phase 1 Protocol-Synthese, HISTORICAL) holt den State erneut.
- Bewusste Architektur-Entscheidung: der Frontend ist **Stateless-Client**, der Daemon ist die Truth-Quelle. Das vermeidet die "Local-vs-Remote-State-Drift"-Klasse, die im Patient (`OverlayState`-Pydantic-Aggregate-Singleton mit Browser-Side-Mirror) eine Bug-Quelle war.

---

## Consequences

**Begründung gegen SolidJS** (das war die Konsortiums-Empfehlung):

- **Team-Erfahrung**: das SurrealMind-Team hat Svelte 5 produktiv eingesetzt. SolidJS hätte ein neues Framework eingeführt mit einem Onboarding-Tax, der die Bundle-Size-Argumente (15 kB vs vergleichbarer Svelte-5-Bundle-Size) nicht aufwiegt.
- **Atlas-interne Knowledge-Base**: Svelte 5 hat mehrere existierende Research-Topics im Atlas (svelte-5-ecosystem, svelte-runes-extension-rules, svelte5-runes-external-state-bridge, svelte5-microtask-proxy-interaction, tiptap-svelte5-prosemirror-bridge, sveltekit-vite-bench-hydration-silent-failure, svelte-component-library-best-practices). SolidJS hat keine Atlas-Knowledge.
- **Reaktivitäts-Modell-Parität**: Runes sind Signal-basiert (gleicher Mechanismus wie SolidJS). Push-only WS-Subscriptions sind mit `$state` + `$effect` direkt ausdrückbar — keine Funktions-Asymmetrie gegenüber SolidJS.

**Bezug zur Codegen-Pipeline**:

- Frontend importiert Zod-Schemas ausschließlich aus `_generated/` (siehe [ADR-010](./ADR-010-codegen-pipeline.md)). Hand-Edits sind durch pre-commit-Hook verboten.
- Brand-Augmentation für Frontend-spezifische Type-Extensions lebt in **separaten** Files außerhalb `_generated/`. Beispiel: ein UI-Hilfs-Type für "Pick im Auswahl-Modus" ist Frontend-spezifisch und gehört nicht in den generierten Code.

**Bundle-Größe**:

- Svelte 5 Compiled Output ist im selben Größen-Bereich wie SolidJS — sub-30-kB-gzipped für die Annotation-UI ist ein realistisches Ziel.
- Kein Dead-Code-Concern: Bun-Build mit Tree-Shaking eliminiert ungenutzten Runes-Compile-Output.

**Was diese ADR NICHT macht**:

- Sie schreibt kein UI-Komponenten-Library vor (Skeleton, Carbon, etc.). Annotation-UI ist Single-Purpose und kommt mit einem dedizierten CSS-Layer aus.
- Sie löst nicht die SSR-vs-CSR-Frage. Annotation-UI ist CSR (Client-Side-Rendering); SSR ist nicht erforderlich (Single-User, lokales Tool).
- Sie macht kein Routing-Statement. Annotation-UI hat eine Page; falls Routes notwendig werden, ist Svelte 5 mit SvelteKit-Lite das Default-Add-on.

---

## Related ADRs

- [ADR-003 Stack](./ADR-003-python-svelte-stack.md) — die Stack-Wahl, in der diese ADR sitzt.
- [ADR-010 Codegen-Pipeline](./ADR-010-codegen-pipeline.md) — die Zod-Schemas, die Svelte 5 konsumiert.

---

## Amendment 2026-05-18 — SvelteKit Static-SPA-Build explizit erlaubt

Originalfassung (§Consequences):

> "Sie macht kein Routing-Statement. Annotation-UI hat eine Page; falls Routes notwendig werden, ist Svelte 5 mit SvelteKit-Lite das Default-Add-on."

Diese Formulierung war defensiv gemeint ("kein SvelteKit erzwungen, optional"), wurde aber von Sub-Plan-Writer-Agenten in Wave A (Bundle `frontprompt-frontend-skeleton`) als "kein SvelteKit, plain Svelte default" missverstanden — was zu einer fragwürdigen Mission-Control-SPA-Architektur führte (siehe Architecture-Reset 2026-05-18 §Root-Cause #4).

**Ab 2026-05-18 gilt**: SvelteKit (`@sveltejs/kit`) ist explizit erlaubt und der **Default** für das `overlay/`-Frontend. Konkret:

- **Build-Adapter**: `@sveltejs/adapter-static` für Static-SPA-Build (kein SSR, kein Node-Server zur Runtime)
- **Routing**: SvelteKit-Routes (`src/routes/`) erlaubt, wenn die Overlay-UI mehrere Views bekommt
- **Post-Build-Bundling**: `vite-plugin-singlefile` für IIFE-Single-File-Output, der via Playwright `page.add_init_script` in jede Page injectiert wird (siehe [ADR-015](./ADR-015-overlay-in-page-main-world.md))
- **Distribution**: das gebündelte IIFE wird via `importlib.resources` ins Python-Package eingebettet (`src/frontprompt/_assets/overlay.iife.js`) und vom Daemon at-startup geladen

Der Stateless-Client-Aspekt (§Persistierter State: "Keiner im Frontend") bleibt gültig — die SvelteKit-Routes sind UI-State only, keine Tab-Reload-Persistierung.

**Was sich nicht ändert**:

- Svelte 5 mit Runes bleibt die Framework-Decision
- Bun bleibt das Build-Tool
- Zod-Schema-Konsumierung aus `_generated/` bleibt verpflichtend
- Sub-30-KB-gzipped war ursprüngliche Zielgröße für eine plain-Svelte-App; mit SvelteKit-Static-SPA-Build sind ~30-60 KB realistisch — akzeptabel weil das Overlay nicht aus einem Netzwerk-Round-Trip lädt sondern als Inline-IIFE injectiert wird
