# Phase-2: Two-BC nursery code, dormant since the architecture reset (see ARCHITECTURE.md).
"""InteractionFlow — Aggregate Root der Programmatic-Executor-BC.

Symmetrisch zu ``PageSession``: ein Single-Writer-geschütztes Aggregat, das
eine geordnete Sequenz von Browser-Interaktions-Schritten (Capture-Vorgänge)
repräsentiert.

Wie ``PageSession``: KEINE Mutations-Methoden in diesem Sub-Plan.
"""

from __future__ import annotations

from pydantic import BaseModel, ConfigDict, PrivateAttr

from frontprompt.types import InteractionFlowId, TaskId


class InteractionFlow(BaseModel):
    """Aggregate Root: eine Capture-Session für Interaktions-Sequenzen.

    Lebenszyklus: ``open`` → ``capturing`` → ``closed`` (Zustände kommen in
    späteren Bundles). Single-Writer ist der Task der ProgrammaticExecutorNursery.
    """

    model_config = ConfigDict(frozen=False, arbitrary_types_allowed=False)

    id: InteractionFlowId
    """Stabile ULID-Identity. Unveränderlich nach Konstruktion."""

    _owner_task_id: TaskId | None = PrivateAttr(default=None)
    """anyio-Task-ID des Single-Writers. Framework-intern — nicht serialisiert."""

    def assert_owner(self, current_task_id: TaskId) -> None:
        """Wirft ``PermissionError`` wenn ``current_task_id`` nicht der Owner ist.

        Raises:
            PermissionError: wenn Owner nicht gesetzt oder Mismatch.
        """
        if self._owner_task_id is None:
            raise PermissionError(f"InteractionFlow {self.id}: kein Owner-Task gesetzt")
        if self._owner_task_id != current_task_id:
            raise PermissionError(
                f"InteractionFlow {self.id}: Owner-Task-Mismatch — "
                f"erwartet {self._owner_task_id!r}, got {current_task_id!r}"
            )
