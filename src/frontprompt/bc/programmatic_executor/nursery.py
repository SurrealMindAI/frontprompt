# Phase-2: Two-BC nursery code, dormant since the architecture reset (see ARCHITECTURE.md).
"""Programmatic Executor BC — outer nursery (Skeleton).

A later phase nests the concrete aggregate-tasks here (PageSession, InteractionFlow).
This file is the ownership-anchor: all tasks in the Programmatic-Executor-scope
start as children of this anyio TaskGroup.

No Lock imports allowed (single-writer discipline, AST-Test).
No asyncio.create_task() allowed (anyio-only concurrency, AST-Test).
"""

from __future__ import annotations

from typing import TYPE_CHECKING

import anyio

from frontprompt.wire.ws_server import run_ws_push_server

if TYPE_CHECKING:
    from anyio.streams.memory import MemoryObjectReceiveStream

    from frontprompt.clock import DaemonClock
    from frontprompt.queue import IntentRequest
    from frontprompt.wire.event_bus import InProcessEventBus


async def run_programmatic_executor_bc(
    queue_recv: MemoryObjectReceiveStream[IntentRequest],
    clock: DaemonClock,
    event_bus: InProcessEventBus,
) -> None:
    """Start the Programmatic-Executor-BC nursery.

    Receives IntentRequests from the queue — in the skeleton they are
    silently dropped. A later phase adds aggregate-task-starts here.

    Also starts the WS-Push-Server (Channel 2) as a sibling task
    in the same anyio TaskGroup — sharing lifetime with the BC.

    Args:
        queue_recv: Receive-end of the IntentRequestQueue.
        clock: DaemonClock — passed to the aggregate-tasks added later.
        event_bus: InProcessEventBus — WS-Push-Server subscribes here.
    """
    async with anyio.create_task_group() as tg:
        tg.start_soon(run_ws_push_server, event_bus)  # WS-Push-Server im PE-BC-Nursery
        # A later phase calls tg.start_soon(run_page_session, ...) here.
        # Skeleton: queue-drain-loop as no-op so the receive-end
        # does not block and the stream can be closed cleanly.
        async with queue_recv:
            async for _request in queue_recv:
                pass  # intentional drop — a later phase processes here
        tg.cancel_scope.cancel()
