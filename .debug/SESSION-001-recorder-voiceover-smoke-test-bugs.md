# Debug Session 001: Recorder / Voice-over dev-smoke-test bugs (4)

**Status**: resolved
**Started**: 2026-06-27
**Updated**: 2026-06-27
**Method**: Backtracking from symptom (per-bug) — all four are localized with explicit evidence pointers
**Branch**: feat/recorder (no new branch per orchestrator)

## Bug Report (4 bugs from manual dev-smoke-test)

1. `RecordingMeta.entry_count` stale (shows 0 although timeline has entries).
2. Settings shows "No backends registered." even on Apple Silicon.
3. Recorder must collapse the overlay on recording start (like pick/quick-comment), restore on stop.
4. name/description edit not discoverable from the timeline view.

## Classification

- **Category**: 1+2 logic (backend state), 3+4 UI/UX (frontend)
- **Severity**: medium (degraded UX / wrong metadata; no crash/data-loss)
- **Complexity**: 1+2 simple, 3+4 moderate (cross-component derived state)

## Method Selection

**Primary**: Backtracking from symptom. Each bug ships with a precise evidence
pointer (file + mechanism). The decision framework (reproducible + known location)
routes directly to backtracking + targeted probes; git bisect is unnecessary
(feature branch, not a regression).
**Research backing**: MIT 6.005 — "evidence before theories"; probes not premature
fixes. RCA at the end per Bugasura.

## Evidence Log

### E1 — BUG 1 root cause
`StateManager.start_recording` builds the meta via `_recording_to_meta` when
`entries` is still empty → `entry_count=0`. `append_timeline_entry` (PIT-105
non-broadcasting) mutates `_full_recordings[*].entries` but never the meta.
`_stop_recording_locked` updates `status`/`ended_at_ms` but NOT `entry_count`.
So `list_recordings_meta()` / the broadcast snapshot keeps `entry_count=0`.
- Source: `src/frontprompt/state/manager.py` `_recording_to_meta` (259), `start_recording` (909), `_stop_recording_locked` (961), `_append_timeline_entry_locked` (1039), `_post_mutate_locked` (1527).

### E2 — BUG 2 root cause
`MlxWhisperBackend` self-registers into `REGISTERED_BACKENDS` only when
`frontprompt.voice.backends` is imported. The daemon never imports that package,
and `ShowSession._build_state_manager` constructs `StateManager(...)` without a
`transcription_state`, so it defaults to empty `TranscriptionState()`. Registry
stays empty → Settings shows nothing.
- Source: `src/frontprompt/voice/backends/__init__.py:27`, `src/frontprompt/show_session.py:173` `_build_state_manager`, `manager.py:194`.

### E3 — BUG 3 root cause
Panels collapse to Laschen only when `pageTool.active` (full-viewport tools) or
`isAboutBlank` — see `App.svelte` gridTemplate + `Panel.svelte`/`PanelTab.svelte`
`effectiveOpenWith(id, pageTool.active)`. Nothing collapses on `recorder.isActive`.
The floating toolbar already shows on `recorder.isActive` (`App.svelte:272`).
- Source: `frontend/src/local-state/page-tool.svelte.ts`, `App.svelte:119-124`, `Panel.svelte:38`, `PanelTab.svelte:38`.

### E4 — BUG 4 root cause
Clicking a recording row sends `selectRecording(id)` → Python sets
`active_detail_recording_id` + `detail_recording` → `RightPanel` shows
`RecordingDetails` (which HAS the name/desc editor). BUT (a) there is no
auto-open-right-panel effect for recordings (picks/regions have one in
`App.svelte:150`), so if the right panel is closed the editor is invisible; and
(b) the timeline-view header (`RecordingsTab.svelte:125`) shows the name as
static text with no edit affordance.
- Source: `App.svelte:150-163`, `RecordingsTab.svelte:121-126`, `RightPanel.svelte:28`, `RecordingDetails.svelte`.

## Hypotheses

### H1 (BUG1): syncing meta.entry_count from `_full_recordings` at every broadcast fixes it
- Test: start → append N → stop → snapshot/list shows entry_count == N. CONFIRMED (see Fix).

### H2 (BUG2): importing voice.backends at daemon start + deriving TranscriptionState from the registry populates Settings; construction works without mlx
- Test: daemon-start path populates REGISTERED_BACKENDS + builds a non-empty TranscriptionState; MlxWhisperBackend() constructs with mlx absent. CONFIRMED.

### H3 (BUG3): a dedicated collapse aggregator (pageTool.active || recorder.isActive) collapses on record, restores on stop, keeping floating toolbar
- Test: panelCollapse.active reflects recorder.isActive. CONFIRMED.

### H4 (BUG4): auto-open right panel for recordings + ✎ affordance in timeline header makes editing discoverable, reusing RecordingDetails editor (DRY)
- Test: ✎ control present in timeline header; clicking it opens the right panel. CONFIRMED.

## Fix — see per-bug sections in final report. Files changed:
- `src/frontprompt/state/manager.py` (BUG1)
- `src/frontprompt/show_session.py` (BUG2)
- `frontend/src/local-state/panel-collapse.svelte.ts` (new, BUG3)
- `frontend/src/components/Panel.svelte`, `PanelTab.svelte`, `App.svelte` (BUG3+4)
- `frontend/src/components/left-panel/tabs/RecordingsTab.svelte` (BUG4)
- tests for each.

## Regression Prevention
- BUG1: `tests/state/test_state_manager_recordings.py` entry_count-after-append test.
- BUG2: `tests/show/test_show_session_voice_over.py` daemon-start registry test.
- BUG3: `frontend/src/local-state/panel-collapse.svelte.test.ts`.
- BUG4: `RecordingsTab.test.ts` edit-affordance test.
