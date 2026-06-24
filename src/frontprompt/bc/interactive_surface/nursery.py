# Phase-2: Two-BC nursery code, dormant since the architecture reset (see ARCHITECTURE.md).
"""Interactive Surface BC — outer nursery (Skeleton).

A later phase nests the PointingSession aggregate-tasks here.
This file is the ownership-anchor: all tasks in the Interactive-Surface-scope
start as children of this anyio TaskGroup.

No Lock imports allowed (single-writer discipline, AST-Test).
No asyncio.create_task() allowed (anyio-only concurrency, AST-Test).
"""

from __future__ import annotations

from typing import TYPE_CHECKING

import anyio

if TYPE_CHECKING:
    from anyio.streams.memory import MemoryObjectSendStream

    from frontprompt.clock import DaemonClock
    from frontprompt.queue import IntentRequest


async def run_interactive_surface_bc(
    queue_send: MemoryObjectSendStream[IntentRequest],
    clock: DaemonClock,
) -> None:
    """Start the Interactive-Surface-BC nursery.

    Holds the send-end of the IntentRequestQueue. In the skeleton this
    nursery sends nothing — a later phase adds PointingSession aggregate-tasks
    that react to MCP-tool-calls and enqueue IntentRequests.

    Args:
        queue_send: Send-end of the IntentRequestQueue.
        clock: DaemonClock — passed to the aggregate-tasks added later.
    """
    async with anyio.create_task_group() as tg:
        # A later phase calls tg.start_soon(run_pointing_session, ...) here.
        # Skeleton: keep the queue send-end open until outer-cancel.
        async with queue_send:
            await anyio.sleep_forever()
        tg.cancel_scope.cancel()
