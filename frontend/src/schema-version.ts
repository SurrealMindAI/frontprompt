/**
 * schema-version.ts — shared overlay-envelope SCHEMA_VERSION constant.
 *
 * This is the envelope-level schema version (currently '0.10.0'), distinct from
 * the per-sub-store intent-message versions in inspector-state.svelte.ts ('0.5.0')
 * and panel-state.svelte.ts ('0.1.0').
 *
 * SSoT: src/frontprompt/bridge/messages.py:SCHEMA_VERSION (Pydantic).
 * Extracted here so that main.ts and any consumer (e.g. Dashboard.svelte) import
 * a single value rather than duplicating the string literal. A prior incident
 * showed the hardcode in main.ts drifting stale to '0.3.0' — this module is the
 * single place to update when the Python SSoT bumps.
 */
export const SCHEMA_VERSION = '0.11.0';
