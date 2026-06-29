# Changelog

All notable changes to frontprompt are documented here. The format follows
[Keep a Changelog](https://keepachangelog.com/en/1.1.0/), and the project adheres
to [Semantic Versioning](https://semver.org/spec/v2.0.0.html).

The on-the-wire **state-schema** and **MCP-tool-schema** evolve independently of
the package version; their full per-version history lives in
[ARCHITECTURE.md § State schema history](ARCHITECTURE.md#state-schema-history) and
[§ IPC (tool) schema history](ARCHITECTURE.md#ipc-tool-schema-history).

## [Unreleased]

_Nothing yet._

## [0.1.0] — 2026-06-28

The "capture & replay" release: frontprompt can now record an annotation session,
replay it with assertions, and narrate it with voice-over.

### Added

- **Recorder.** A floating toolbar records a timeline of page events, picks,
  regions, relations, and navigations into a `Recording` aggregate. Recordings
  tab with timeline view and per-entry detail. (state schema 0.8.0)
- **Replay & assertions.** Author assertion checkpoints inside a recording,
  replay it with named parameters, and read a structured `ReplayReport` of every
  step result. Agent-facing write surface over MCP/CLI. (state schema 0.9.0)
- **Voice-over.** Capture microphone audio for a recording, watch device
  topology, and transcribe locally via `mlx-whisper` (Apple Silicon). Transcript
  segments land as timeline entries. Settings tab with a microphone picker.
  (state schema 0.10.0)
- **Transcription model catalog.** Select the local Whisper model (base by
  default, large-v3-turbo available); selection persists and re-probes backend
  readiness. (state schema 0.11.0)
- **Coverage tooling.** `pytest-cov` + `@vitest/coverage-v8` with a 90% floor on
  both stacks.

### Changed

- `mlx-whisper`, `sounddevice`, and `huggingface_hub` are now core dependencies
  (voice-over is a first-class feature, not an extra). `mlx-whisper` is gated to
  arm64 macOS via a PEP 508 environment marker.

## [0.0.6] — 2026-06-25

### Changed

- Release consolidation: `uv.lock` synced and the version smoke-test made
  bump-proof.

## [0.0.5] — 2026-06-25

### Added

- Deterministic version consistency: the plugin's `uvx --from frontprompt==X.Y.Z`
  launch is pinned, and `scripts/check_versions.py` enforces a single version
  across `pyproject.toml`, `__init__.py`, both `plugin.json` files, the
  marketplace manifest, and the pinned plugin launch — in the pre-push hook, CI,
  and the release workflow.

## [0.0.4] — 2026-06-25

### Added

- Professional CI: Python 3.13 + 3.14 test matrix, split jobs, and targeted
  reruns for the inherently flaky real-Chromium-under-xvfb integration tests.
- Slim bootstrap path for the Chromium driver install.

## Initial public release — 2026-06-25

The first public cut of the greenfield rewrite (the predecessor
`frontprompt-legacy` was archived 2026-05-13 and rebuilt from first principles —
see the [Architecture Decision Records](docs/adr/index.md)).

### Added

- **In-page inspector overlay.** A shadow-DOM HUD injected into any page: click to
  **pick** elements, drag to capture **regions** (with auto-picked members and
  derived relations), and draw typed **relations** between picks and regions.
- **Cross-origin survival.** Annotation state is authoritative in the Python
  process, so picks persist across cross-origin navigation. See
  [ARCHITECTURE.md](ARCHITECTURE.md).
- **MCP server.** `frontprompt mcp` exposes navigation, page-query / element-reader
  tools (`get_page_outline`, `find_one`/`find_first`/`find_similar`, `pick_from_ref`,
  …), screenshots, and read-only state access (`get_state_summary`, `get_snapshot`,
  `get_picks`). Each invocation owns a private, lazily-spawned browser session.
- **SQLite persistence** (WAL, JSON-blob) so annotations outlive the process.
- **Playwright** drives the headful browser; **Scrapling** (pinned `==0.4.8`) is an
  isolated, parser-only dependency for DOM fingerprint matching.
- **Self-contained wheel.** The Svelte overlay is built and embedded into the
  package, so the installed tool needs no Bun or Node at runtime.

[Unreleased]: https://github.com/SurrealMindAI/frontprompt/compare/v0.1.0...HEAD
[0.1.0]: https://github.com/SurrealMindAI/frontprompt/compare/v0.0.6...v0.1.0
[0.0.6]: https://github.com/SurrealMindAI/frontprompt/compare/v0.0.5...v0.0.6
[0.0.5]: https://github.com/SurrealMindAI/frontprompt/compare/v0.0.4...v0.0.5
[0.0.4]: https://github.com/SurrealMindAI/frontprompt/releases/tag/v0.0.4
