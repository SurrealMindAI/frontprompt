"""InMemoryPersistence — no-op default persistence implementation.

State classification. Phase-1-default: kein disk-write, kein cross-restart-survival.
Implements :class:`~frontprompt.state.persistence.protocol.StatePersistence`;
structlog-logged for visibility.
"""

from __future__ import annotations

from typing import TYPE_CHECKING

import structlog

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

_LOG = structlog.get_logger(__name__)


class InMemoryPersistence:
    """Phase-1-default: kein disk-write, kein cross-restart-survival.

    Folgt :class:`~frontprompt.state.persistence.protocol.StatePersistence`
    protocol; structlog-logged für visibility.

    Recording-domain (sub-plan 01): in-memory dict-based storage for tests.
    StateManager uses this as the default when no SqlitePersistence is injected.
    """

    def __init__(self) -> None:
        self._log = _LOG.bind(impl="in_memory")
        # Recording in-memory store: recording_id -> Recording
        self._recordings: dict[str, "Recording"] = {}
        # Replay report in-memory store: replay_id -> ReplayReport
        self._replay_reports: dict[str, "ReplayReport"] = {}
        # Model selection in-memory store (Schema 0.11.0+)
        self._mlx_whisper_model_id: str | None = None

    def load_panel_state(self) -> PanelStateView | None:
        self._log.info("state.persistence.load_panel.in_memory_no_op")
        return None

    def save_panel_state(self, panel_state: PanelStateView) -> None:
        # accept the arg so the signature matches — but no-op
        del panel_state
        self._log.debug("state.persistence.save_panel.in_memory_no_op")

    def load_inspector_state(self) -> InspectorState | None:
        self._log.info("state.persistence.load_inspector.in_memory_no_op")
        return None

    def save_inspector_state(self, inspector_state: InspectorState) -> None:
        # accept the arg so the signature matches — but no-op
        del inspector_state
        self._log.debug("state.persistence.save_inspector.in_memory_no_op")

    # ----- Per-entity write-through (no-op mirror of the protocol) ------------

    def upsert_pick(self, pick: Pick) -> None:
        del pick
        self._log.debug("state.persistence.upsert_pick.in_memory_no_op")

    def delete_pick(self, pick_id: str) -> None:
        del pick_id
        self._log.debug("state.persistence.delete_pick.in_memory_no_op")

    def upsert_region(self, region: Region) -> None:
        del region
        self._log.debug("state.persistence.upsert_region.in_memory_no_op")

    def delete_region(self, region_id: str) -> None:
        del region_id
        self._log.debug("state.persistence.delete_region.in_memory_no_op")

    def upsert_relation(self, relation: Relation) -> None:
        del relation
        self._log.debug("state.persistence.upsert_relation.in_memory_no_op")

    def delete_relation(self, relation_id: str) -> None:
        del relation_id
        self._log.debug("state.persistence.delete_relation.in_memory_no_op")

    # ----- Recording write-through (sub-plan 01) --- in-memory dict store -----

    def upsert_recording(self, recording: "Recording") -> None:
        """In-memory upsert — last-write-wins by recording_id."""
        self._recordings[recording.recording_id] = recording.model_copy(deep=True)
        self._log.debug("state.persistence.upsert_recording.in_memory", recording_id=recording.recording_id)

    def delete_recording(self, recording_id: str) -> None:
        """In-memory delete. Idempotent."""
        self._recordings.pop(recording_id, None)
        self._log.debug("state.persistence.delete_recording.in_memory", recording_id=recording_id)

    def load_recordings(self) -> "list[Recording]":
        """Return all in-memory recordings sorted by started_at_ms."""
        return sorted(self._recordings.values(), key=lambda r: r.started_at_ms)

    def append_timeline_entry(self, recording_id: str, entry: "TimelineEntry") -> None:
        """Append entry to the in-memory recording's entries list."""
        if recording_id not in self._recordings:
            self._log.warning("state.persistence.append_timeline_entry.unknown", recording_id=recording_id)
            return
        self._recordings[recording_id].entries.append(entry)
        self._log.debug(
            "state.persistence.append_timeline_entry.in_memory",
            recording_id=recording_id,
            seq=entry.seq,
        )

    def update_recording_meta(self, recording_id: str, name: str, description: str) -> None:
        """Update name + description in-memory."""
        if recording_id not in self._recordings:
            self._log.warning("state.persistence.update_recording_meta.unknown", recording_id=recording_id)
            return
        rec = self._recordings[recording_id]
        rec.name = name
        rec.description = description
        self._log.debug("state.persistence.update_recording_meta.in_memory", recording_id=recording_id)

    def mark_recording_stopped(self, recording_id: str, ended_at_ms: int) -> None:
        """Set status='stopped' and ended_at_ms in-memory."""
        if recording_id not in self._recordings:
            self._log.warning("state.persistence.mark_recording_stopped.unknown", recording_id=recording_id)
            return
        rec = self._recordings[recording_id]
        rec.status = "stopped"
        rec.ended_at_ms = ended_at_ms
        self._log.debug("state.persistence.mark_recording_stopped.in_memory", recording_id=recording_id)

    # ----- Voice-over settings persistence (sub-plan 01) --- no-op stubs -----

    def save_settings(self, settings: "SettingsState") -> None:
        """No-op — InMemoryPersistence does not persist settings across restarts."""
        del settings
        self._log.debug("state.persistence.save_settings.in_memory_no_op")

    def load_settings(self) -> "SettingsState | None":
        """Returns None — no persistent settings in InMemoryPersistence."""
        self._log.debug("state.persistence.load_settings.in_memory_no_op")
        return None

    def save_mic_device_id(self, device_id: int | None) -> None:
        """No-op — InMemoryPersistence does not persist mic device id."""
        del device_id
        self._log.debug("state.persistence.save_mic_device_id.in_memory_no_op")

    def load_mic_device_id(self) -> int | None:
        """Returns None — no persistent mic device id in InMemoryPersistence."""
        self._log.debug("state.persistence.load_mic_device_id.in_memory_no_op")
        return None

    def save_mlx_whisper_model_id(self, model_id: str | None) -> None:
        """Persist mlx-whisper model id in-memory. Schema 0.11.0+."""
        self._mlx_whisper_model_id = model_id
        self._log.debug("state.persistence.save_mlx_whisper_model_id.in_memory", model_id=model_id)

    def load_mlx_whisper_model_id(self) -> str | None:
        """Return in-memory mlx-whisper model id (None when not set). Schema 0.11.0+."""
        self._log.debug("state.persistence.load_mlx_whisper_model_id.in_memory")
        return self._mlx_whisper_model_id

    # ----- Replay-report write-through (sub-plan 01) --- in-memory dict store -----

    def save_replay_report(self, report: "ReplayReport") -> None:
        """In-memory upsert — last-write-wins by replay_id."""
        self._replay_reports[report.replay_id] = report.model_copy(deep=True)
        self._log.debug("state.persistence.save_replay_report.in_memory", replay_id=report.replay_id)

    def get_replay_report(self, replay_id: str) -> "ReplayReport | None":
        """Retrieve by replay_id. Returns None when not found."""
        return self._replay_reports.get(replay_id)

    def list_replay_reports_meta(self, recording_id: str | None = None) -> "list[ReplayReportMeta]":
        """Return lightweight ReplayReportMeta list, optionally filtered by recording_id."""
        from frontprompt.state.state import ReplayReportMeta

        reports = list(self._replay_reports.values())
        if recording_id is not None:
            reports = [r for r in reports if r.recording_id == recording_id]

        results: list[ReplayReportMeta] = []
        for report in sorted(reports, key=lambda r: r.started_at_ms):
            passed = sum(1 for s in report.step_results if s.assertion_passed is True)
            failed = sum(1 for s in report.step_results if s.assertion_passed is False)
            results.append(
                ReplayReportMeta(
                    replay_id=report.replay_id,
                    recording_id=report.recording_id,
                    status=report.status,
                    started_at_ms=report.started_at_ms,
                    ended_at_ms=report.ended_at_ms,
                    step_count=len(report.step_results),
                    passed_assertions=passed,
                    failed_assertions=failed,
                )
            )
        return results


__all__ = ["InMemoryPersistence"]
