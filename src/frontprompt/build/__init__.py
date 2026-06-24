"""Canonical build pipeline for the frontprompt overlay bundle.

Canonical build pipeline (see ARCHITECTURE.md): every build path runs codegen
first (Pydantic -> Zod) so the TS overlay never compiles against drifted schemas.

Pipeline (``python -m frontprompt.build``):
    1. pydantic-zod-codegen generate frontprompt.state.state    -> frontend/src/_generated/state.ts
    2. pydantic-zod-codegen generate frontprompt.bridge.messages -> frontend/src/_generated/schemas.ts
    3. write frontend/src/_generated/build-info.ts with build session + version
    4. bun run build (in frontend/) with FRONTPROMPT_BUILD_SESSION env set
    5. write frontend/dist/build-manifest.json
    6. embed overlay.iife.js + build-manifest.json into src/frontprompt/_overlay/
       (this is what ships inside the wheel — the loader prefers it at runtime)

With ``--wheel`` an additional step runs ``uv build --wheel`` to produce the
self-contained python package in ``dist/`` (frontend embedded; chromium is
installed separately at runtime via ``frontprompt bootstrap``).

Invoke via ``python -m frontprompt.build`` (or ``--wheel`` to package).
"""
