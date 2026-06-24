"""InMemoryPersistence — no-op default persistence implementation.

State classification. Phase-1-default: kein disk-write, kein cross-restart-survival.
Implements :class:`~frontprompt.state.persistence.protocol.StatePersistence`;
structlog-logged for visibility.
"""

from __future__ import annotations

from typing import TYPE_CHECKING

import structlog

if TYPE_CHECKING:
    from frontprompt.state.state import InspectorState, PanelStateView, Pick, Region, Relation

_LOG = structlog.get_logger(__name__)


class InMemoryPersistence:
    """Phase-1-default: kein disk-write, kein cross-restart-survival.

    Folgt :class:`~frontprompt.state.persistence.protocol.StatePersistence`
    protocol; structlog-logged für visibility.
    """

    def __init__(self) -> None:
        self._log = _LOG.bind(impl="in_memory")

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


__all__ = ["InMemoryPersistence"]
