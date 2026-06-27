"""StatePersistence Protocol — the persistence interface.

State classification. Broadened from Phase-1 panel-only to include inspector state (Task 2).
SqlitePersistence (Task 3+) will be a second concrete impl; InMemoryPersistence
is the no-op default for tests and phase-1 runtime.
"""

from __future__ import annotations

from typing import TYPE_CHECKING, Protocol

if TYPE_CHECKING:
    from frontprompt.state.state import (
        InspectorState,
        PanelStateView,
        Pick,
        Recording,
        Region,
        Relation,
        ReplayReport,
        ReplayReportMeta,
        SettingsState,
        TimelineEntry,
    )


class StatePersistence(Protocol):
    """Persistenz-interface — load init-state, save mutations.

    Phase-1-impl :class:`~frontprompt.state.persistence.in_memory.InMemoryPersistence`
    is no-op (alles geht beim process-exit verloren). Phase-2 ist SQLite-backed.

    Two write surfaces:

    - **Panel** is a singleton (id=0 row), so :meth:`save_panel_state` is a full
      overwrite — no accumulation hazard.
    - **Inspector entities** (picks / regions / relations) are written
      **per-entity** via the targeted ``upsert_*`` / ``delete_*`` methods, NOT as
      a whole-set overwrite. The disk is the source of truth for "what exists";
      a session never rewrites the full set from its (possibly stale) in-memory
      copy. This is what keeps deletes durable and prevents the cross-session
      accumulation bug — see ``tests/state/persistence/test_sqlite_accumulation.py``.

    All methods are called by :class:`~frontprompt.state.manager.StateManager`
    and must be implemented by any concrete persistence provider.
    """

    def load_panel_state(self) -> PanelStateView | None:
        """Returns persisted panel state oder None für default-init."""
        ...

    def save_panel_state(self, panel_state: PanelStateView) -> None:
        """Persist panel state (singleton). Idempotent full overwrite."""
        ...

    def load_inspector_state(self) -> InspectorState | None:
        """Returns persisted inspector state oder None für default-init."""
        ...

    def save_inspector_state(self, inspector_state: InspectorState) -> None:
        """Bulk-seed the inspector entities (upsert-all + prune-missing).

        Seed/initialisation helper only — used by tests and one-shot imports
        where a single writer owns the whole set. **Runtime mutations must NOT
        use this** (it overwrites the full set from in-memory and would
        resurrect rows other sessions deleted); they use the per-entity
        ``upsert_*`` / ``delete_*`` methods below.
        """
        ...

    # ----- Per-entity write-through (authoritative + idempotent on id) --------

    def upsert_pick(self, pick: Pick) -> None:
        """Insert-or-replace one pick keyed on ``pick_id``. Idempotent."""
        ...

    def delete_pick(self, pick_id: str) -> None:
        """Delete one pick by ``pick_id``. Idempotent (no-op if absent)."""
        ...

    def upsert_region(self, region: Region) -> None:
        """Insert-or-replace one region keyed on ``region_id``. Idempotent."""
        ...

    def delete_region(self, region_id: str) -> None:
        """Delete one region by ``region_id``. Idempotent (no-op if absent)."""
        ...

    def upsert_relation(self, relation: Relation) -> None:
        """Insert-or-replace one relation keyed on ``relation_id``. Idempotent."""
        ...

    def delete_relation(self, relation_id: str) -> None:
        """Delete one relation by ``relation_id``. Idempotent (no-op if absent)."""
        ...

    # ----- Recording write-through (sub-plan 01) ---------------------------------

    def upsert_recording(self, recording: "Recording") -> None:
        """Insert-or-replace one recording keyed on ``recording_id``. Idempotent.

        Bulk helper for tests and one-shot imports. Runtime mutations use the
        targeted methods below (append_timeline_entry / update_recording_meta /
        mark_recording_stopped) — not this full-recording overwrite, which would
        risk resurrecting deleted entries.
        """
        ...

    def delete_recording(self, recording_id: str) -> None:
        """Delete recording + all its timeline entries (cascade). Idempotent."""
        ...

    def load_recordings(self) -> "list[Recording]":
        """Return all recordings with their timeline entries, ordered by started_at_ms."""
        ...

    def append_timeline_entry(self, recording_id: str, entry: "TimelineEntry") -> None:
        """Append a single timeline entry to an existing recording. Append-only."""
        ...

    def update_recording_meta(self, recording_id: str, name: str, description: str) -> None:
        """Update only name + description of an existing recording."""
        ...

    def mark_recording_stopped(self, recording_id: str, ended_at_ms: int) -> None:
        """Set status='stopped' and ended_at_ms. Idempotent."""
        ...

    # ----- Voice-over settings persistence (sub-plan 01) -------------------------

    def save_settings(self, settings: "SettingsState") -> None:
        """Persist durable voice-over settings (voice_over_enabled + selected_transcription_backend_id).

        Uses a key-value ``settings`` table. Idempotent — overwrites existing keys.
        """
        ...

    def load_settings(self) -> "SettingsState | None":
        """Load persisted voice-over settings. Returns None when no settings row exists yet."""
        ...

    def save_mic_device_id(self, device_id: int | None) -> None:
        """Persist selected microphone device id to the settings key-value table.

        ``None`` = system default. Idempotent. Separate from :meth:`save_settings`
        because the mic preference co-locates with MicrophoneState (not SettingsState).
        """
        ...

    def load_mic_device_id(self) -> int | None:
        """Load the persisted microphone device id. Returns None when not set."""
        ...

    def save_mlx_whisper_model_id(self, model_id: str | None) -> None:
        """Persist selected mlx-whisper model id to the settings key-value table.

        ``None`` = revert to default model. Idempotent. Separate from
        :meth:`save_settings` because the model selection is a per-backend concern.
        Schema 0.11.0+.
        """
        ...

    def load_mlx_whisper_model_id(self) -> str | None:
        """Load the persisted mlx-whisper model id. Returns None when not set.

        Schema 0.11.0+.
        """
        ...

    # ----- Replay-report write-through (sub-plan 01) -------------------------

    def save_replay_report(self, report: "ReplayReport") -> None:
        """Insert-or-replace one ReplayReport keyed on replay_id. Idempotent."""
        ...

    def get_replay_report(self, replay_id: str) -> "ReplayReport | None":
        """Retrieve a ReplayReport by replay_id. Returns None when not found."""
        ...

    def list_replay_reports_meta(self, recording_id: str | None = None) -> "list[ReplayReportMeta]":
        """Return lightweight ReplayReportMeta list, optionally filtered by recording_id."""
        ...


__all__ = ["StatePersistence"]
