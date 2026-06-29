# ADR-017 — Canonical Build Pipeline mit Env-Guard

> Part of the frontprompt [Architecture Decision Records](./index.md).

**Status**: accepted
**Date**: 2026-05-18
**Cross-References**: [ADR-008 Svelte 5 (amended)](./ADR-008-svelte-5-runes.md), [ADR-015 Overlay in Main World](./ADR-015-overlay-in-page-main-world.md), [ADR-016 Bridge via expose_function](./ADR-016-expose-function-bridge.md), 2026-05-18 Architecture Reset

---

## Context

Der initiale Overlay-Loader (`src/frontprompt/overlay/loader.py`) hatte eine auto-rebuild-Logik mit:

- mtime-check auf alle src-files
- Auto-cache-clear + bun-install + bun-build
- Skip-rebuild via env-var

Diese Magic-Pipeline hat zwei Probleme:

1. **Build-State-Drift**: wer "kennt" den Build? CLI calls können den Build triggern; `bun run build` kann direkt aufgerufen werden; Tests können den built bundle laden. Drei Pfade die zum Bundle führen, drei mögliche Drift-Quellen.
2. **Watch-Mode-Illusion**: Auto-rebuild bei jedem CLI-call suggeriert Hot-Reload-UX. Aber Overlay läuft im injected Page-Context — re-build heißt nicht re-inject. User muss `frontprompt show ...` neu aufrufen → kein echter dev-loop, nur künstliche Latenz.

User-Direktive 2026-05-18 hat die Vereinfachung gefordert: **eine canonical build pipeline mit Env-Guard, kein magic, kein watch-mode.**

Plus: ab ADR-016 kommt ein neuer pre-build-Schritt dazu (Pydantic → Zod codegen via `pydantic-zod-codegen`). Drei build-pfade × zwei build-stages = sechs Fehler-Pfade. Müssen konsolidieren.

---

## Decision

**Eine canonical entry point: `uv run python -m frontprompt.build`. Diese Pipeline ist die EINZIGE supported Methode den Overlay-Bundle zu produzieren. Direkter `bun run build` aborted mit hartem Error wenn nicht via canonical pipeline aufgerufen. CLI (`frontprompt show ...`) liest pre-built bundle und failed hart wenn fehlt.**

### Build-Pipeline-Steps

`python -m frontprompt.build` (implementiert in `src/frontprompt/build/__main__.py`):

```
Step 1 — generate build-session identity
    FRONTPROMPT_BUILD_SESSION = <ULID>
    FRONTPROMPT_BUILD_VERSION = <isoformat-utc>
    FRONTPROMPT_BUILD_GIT_SHA = <short sha or "dirty">

Step 2 — codegen (pydantic → zod + TS types)
    `python -m frontprompt.bridge.codegen`
    writes: frontend/src/_generated/schemas.ts
            frontend/src/_generated/build-info.ts (contains the env vars as const exports)

Step 3 — bun build (spawned subprocess)
    env passes through (FRONTPROMPT_BUILD_SESSION etc.)
    spawned cmd: `bun run build` in frontend/
    vite.config.ts has a guard at top: if (!process.env.FRONTPROMPT_BUILD_SESSION) throw

Step 4 — write build-manifest
    frontend/dist/build-manifest.json with:
      { build_session, build_version, build_git_sha, bundle_size_bytes,
        schema_version, generated_at_iso }
```

### Vite-Config-Guard

`frontend/vite.config.ts`-Top:

```ts
if (!process.env.FRONTPROMPT_BUILD_SESSION) {
  throw new Error(
    'frontend MUST be built via "uv run python -m frontprompt.build". ' +
    'Direct "bun run build" / "vite build" is not supported — codegen + ' +
    'env-vars would be missing. See ADR-017.'
  );
}
```

Konsequenz: niemand kann den Build "halb" machen (nur bun, ohne codegen). Garantiert dass build-bundle und generated/-files in-sync sind.

### CLI-Side: kein Auto-Rebuild

`frontprompt show ...`:

```python
from frontprompt.overlay import load_overlay_bundle
try:
    bundle = load_overlay_bundle()  # reads dist/overlay.iife.js
    manifest = load_build_manifest() # reads dist/build-manifest.json
except FileNotFoundError:
    raise SystemExit(
        "Overlay-bundle not found. Run `uv run python -m frontprompt.build` "
        "first (or re-run after editing frontend/src/* or "
        "src/frontprompt/bridge/messages.py)."
    )
```

`load_overlay_bundle()` wird drastisch reduziert: read file, return string. Kein mtime, kein subprocess, kein cache-clear-magic.

Build-manifest wird an die Bridge weitergegeben (vom CLI in den Init-State) → Overlay-Side debug-panel zeigt die version-info.

### Dev-Workflow

Es gibt keinen Watch-Mode. Workflow für Änderungen:

```
# editor change in frontend/src/ or src/frontprompt/bridge/messages.py
uv run python -m frontprompt.build
uv run frontprompt show https://example.com
```

Zwei commands. Klar wer was tut, kein Drift, kein "warum sehe ich meine änderung nicht".

---

## Consequences

### Positive

- **Single source of truth für Builds**: `python -m frontprompt.build` und nichts anderes
- **Codegen + bundle always in-sync** durch env-guard
- **CLI startet schnell**: kein subprocess-spawn, kein mtime-check
- **Explicit dev-loop**: User weiß genau wann er rebuilden muss
- **Build-manifest macht versions reproduzierbar**: jeder Bundle trägt seine Session-ID
- **Tests können bundle-state assumen** (oder explizit pre-build im fixture)

### Negative

- **Kein Hot-Reload**: jede Änderung braucht expliziten rebuild + re-show. Akzeptiert weil:
  - Wir injecten ins Page-Context — re-build ohne re-inject sieht User nicht
  - Im dev-flow ist `python -m frontprompt.build && frontprompt show ...` 5-10s overhead
- **Erste-mal-User muss build explizit triggern**: vs vorher "frontprompt show baut wenn nötig". Doku/README muss das klar machen.
- **CI muss build-step machen vor tests**: pytest-fixture oder Makefile-target. Acceptable.

### Was NICHT mehr supported wird

- `cd frontend && bun run build` — fails mit env-guard-error
- `cd frontend && bun run dev` — Vite-dev-server macht sowieso keinen Sinn für inject-bundle, wird auch geguarded
- Auto-rebuild im `frontprompt show` flow — entfernt aus `overlay/loader.py`
- `FRONTPROMPT_OVERLAY_SKIP_REBUILD` env var — irrelevant, weil kein auto-rebuild mehr
- mtime-checks im overlay-loader — entfernt

---

## Migration

Existing code:

- `src/frontprompt/overlay/loader.py` → drastisch reduziert (read-only)
- `tests/overlay/test_injector.py` → fixture muss `python -m frontprompt.build` vorab callen (oder skipif-no-bundle)
- `frontend/vite.config.ts` → env-guard top-of-file
- Neue Files:
  - `src/frontprompt/build/__init__.py`
  - `src/frontprompt/build/__main__.py`
  - `src/frontprompt/bridge/codegen.py` (gehört konzeptuell zum bridge-modul aber wird vom build aufgerufen)

---

## Alternativen erwogen

### Alt 1 — mtime-basiertes Auto-Rebuild (ruled out, der status quo vor 2026-05-18)

**Pro**: User-friendly, vergessenes rebuild kann nicht passieren.
**Con**: Magic-Layer der zur Build-State-Drift einlädt. User-Direktive: keine Magic. **Ruled out**.

### Alt 2 — Hatch-Build-Hook (ruled out für jetzt)

Build als Teil von `uv tool install frontprompt` / `pip install` via custom hatch-build-hook der bei sdist/wheel-Build den Overlay-Build triggert.

**Pro**: würde production-distribution sauber machen (wheel enthält pre-built bundle).
**Con**: Phase-1-fokus ist dev-loop. Hatch-Hook ist phase-2+ Distribution-Detail.

**Aufgeschoben, nicht abgelehnt**: wird bei erster echter Distribution-Release implementiert.

### Alt 3 — Makefile/Justfile statt python-modul (ruled out)

`make build` als orchestrator.

**Pro**: traditionell für solche pipelines.
**Con**: noch ein weiteres tool im stack. `python -m frontprompt.build` ist atlas-konform (PEP 723 / uv-first). **Ruled out**.

---

## Related ADRs

- [ADR-008 Svelte 5 (amended)](./ADR-008-svelte-5-runes.md) — Build-Output-Target ist `dist/overlay.iife.js`
- [ADR-015 Overlay in Main World](./ADR-015-overlay-in-page-main-world.md) — Bundle wird via `add_init_script` injected
- [ADR-016 Bridge via expose_function](./ADR-016-expose-function-bridge.md) — codegen-pipeline ist Voraussetzung für typed bridge
- 2026-05-18 Architecture Reset
