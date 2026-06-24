"""IntentRequest + IntentRequestQueue — bounded cross-BC message stream.

Two Bounded Contexts (see ARCHITECTURE.md):

* The ``IntentRequest``-Queue is the **only** legitimate communication between the
  Programmatic Executor BC and the Interactive Surface BC.
* The queue is **bounded** (``max_buffer_size`` > 0). Full queue means the producer
  (Interactive Surface BC) blocks until space frees — explicit back-pressure.
* ``anyio.create_memory_object_stream`` is the underlying primitive.

``IntentRequest`` carries dehydrated identifiers — it does NOT
carry live objects or Aggregate references across the BC boundary.

No consumers are wired in this module. The nursery-topology connects
``send_stream`` and ``receive_stream`` to the BC nurseries.

Exported constant ``DEFAULT_BUFFER_SIZE`` is consumed by the BC nurseries to
construct the queue with a consistent default.
"""

from __future__ import annotations

import anyio
from anyio.streams.memory import MemoryObjectReceiveStream, MemoryObjectSendStream
from pydantic import BaseModel, Field

#: Default buffer size for the IntentRequest queue (the wire-boundary).
#: The BC nurseries import this constant to wire themselves.
#: Must be > 0 (bounded queue — full queue blocks the sender, not silently drops).
DEFAULT_BUFFER_SIZE: int = 32


class IntentRequest(BaseModel):
    """Typed message crossing the BC boundary from Interactive Surface → Programmatic Executor.

    All cross-BC Programmatic-Executor references are **dehydrated identifiers**
    (dehydrated identifier fields). No live objects, no Aggregate references.

    ``intent_type`` is the discriminator for the consuming BC's dispatch table.
    Known values (non-exhaustive at skeleton stage):

    * ``"request.pick"`` — PointingSession requests a DOM element pick from the user.
    * ``"notify.page_navigated"`` — Programmatic Executor notifies of a navigation event.
    * ``"notify.annotation_added"`` — Programmatic Executor notifies of a new Annotation.
    * ``"query.page_session_exists"`` — ACL read-only validation.
    * ``"query.interaction_flow_step_valid"`` — ACL read-only validation.
    """

    intent_type: str = Field(..., min_length=1, description="Discriminator for the consuming BC's dispatch table.")

    # Dehydrated identifiers — all optional; None means "not applicable".
    page_session_id: str | None = Field(
        default=None,
        description="ULID of the PageSession in the Programmatic Executor BC.",
    )
    interaction_flow_step_id: str | None = Field(
        default=None,
        description="ULID of the InteractionFlow step (dehydrated identifier).",
    )
    dom_snapshot_hash: str | None = Field(
        default=None,
        description="DOM structural fingerprint at pick-time (per-aggregate LSN / idempotency F-7 scope).",
    )

    model_config = {"frozen": True}


class IntentRequestQueue:
    """Bounded anyio MemoryObjectStream wrapper for cross-BC IntentRequest routing.

    Wraps ``anyio.create_memory_object_stream`` with a validated ``max_buffer_size``.
    Exposes ``send_stream`` and ``receive_stream`` for the BC nurseries.

    Construction is synchronous. The underlying anyio streams are created eagerly
    at ``__init__`` time — no async context required for construction.
    The nurseries must subscribe (open ``receive_stream``) **before** the first
    send to avoid the subscribe-after-publish race.
    """

    def __init__(self, max_buffer_size: int = DEFAULT_BUFFER_SIZE) -> None:
        if max_buffer_size <= 0:
            raise ValueError(f"max_buffer_size must be > 0, got {max_buffer_size!r}")
        self._max_buffer_size = max_buffer_size
        # `item_type=` ist seit anyio 4.0 deprecated. Moderne Form ist
        # Generic-Subscript auf der Factory:
        self.send_stream: MemoryObjectSendStream[IntentRequest]
        self.receive_stream: MemoryObjectReceiveStream[IntentRequest]
        self.send_stream, self.receive_stream = anyio.create_memory_object_stream[IntentRequest](
            max_buffer_size=max_buffer_size
        )

    @property
    def max_buffer_size(self) -> int:
        """Configured buffer size — accessible for assertions in tests."""
        return self._max_buffer_size
