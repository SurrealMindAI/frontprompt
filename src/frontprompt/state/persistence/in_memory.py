"""InMemoryPersistence — no-op default persistence implementation.

State classification. Phase-1-default: kein disk-write, kein cross-restart-survival.
Implements :class:`~frontprompt.state.persistence.protocol.StatePersistence`;
structlog-logged for visibility.
"""

from __future__ import annotations

from typing import TYPE_CHECKING

import structlog

if TYPE_CHECKING:
    from frontprompt.state.state import InspectorState, PanelStateView, Pick, Recording, Region, Relation, TimelineEntry

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


__all__ = ["InMemoryPersistence"]
