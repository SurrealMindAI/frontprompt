"""Daemon — outer anyio-TaskGroup ownership and startup logging.

run_daemon() is the single entry-point. It builds the IntentRequestQueue
(the wire-boundary), logs daemon.startup via structlog, and starts
both BC-nurseries as TaskGroup children.

Cancellation semantics:
    Outer-scope-cancel (e.g. SIGINT via anyio.from_thread or move_on_after)
    propagates deterministically into both BC-TaskGroups — no zombie-tasks,
    no drain-timeout (skeleton; buffered IntentRequests are dropped).

No asyncio.create_task() in this file (anyio-only concurrency).
No threading.Lock / asyncio.Lock (single-writer discipline).
"""

from __future__ import annotations

import sys
import uuid
from dataclasses import dataclass, field
from typing import TYPE_CHECKING, Any

import anyio
import structlog

import frontprompt.bc.interactive_surface.nursery as _is_nursery
import frontprompt.bc.programmatic_executor.nursery as _pe_nursery
from frontprompt.clock import SystemDaemonClock
from frontprompt.queue import DEFAULT_BUFFER_SIZE, IntentRequest
from frontprompt.wire.event_bus import InProcessEventBus
from frontprompt.wire.http_server import run_http_server  # HTTP Mutation Endpoint

if TYPE_CHECKING:
    from frontprompt.clock import DaemonClock

_LOG = structlog.get_logger(__name__)


@dataclass
class Daemon:
    """Runtime handle of the frontprompt daemon.

    Instantiated by run_daemon(); holds no mutable fields besides the
    bound-logger (immutable after bind()).

    ``http_host`` / ``http_port``: bind address for the HTTP Mutation Endpoint.
    Tests that start the daemon multiple times should use ``http_port=0``
    to let the OS pick a free port and avoid ``OSError: Address already in use``.
    """

    daemon_id: str = field(default_factory=lambda: str(uuid.uuid4()))
    clock: DaemonClock = field(default_factory=SystemDaemonClock)
    http_host: str = "127.0.0.1"
    http_port: int = 7178
    _log: Any = field(init=False, repr=False)

    def __post_init__(self) -> None:
        self._log = _LOG.bind(daemon_id=self.daemon_id)


async def run_daemon(daemon: Daemon | None = None) -> None:
    """Start the frontprompt daemon.

    Logs ``daemon.startup``, builds the IntentRequestQueue, starts both
    BC-nurseries as anyio TaskGroup children. Blocks until the outer
    cancellation scope signals (SIGINT, move_on_after, program exit).

    Buffered IntentRequests are silently dropped on cancellation —
    drain logic comes in the bundle that introduces the first real
    aggregate-mutations.

    Args:
        daemon: Daemon instance (carries clock + daemon_id + logger). Default:
            freshly constructed Daemon with SystemDaemonClock — convenient for
            CLI boot and smoke-tests; production callers pass their own
            instance for injected clock and stable daemon_id.
    """
    # The signature accepts a Daemon instance instead of a raw clock. Production
    # callers pass their pre-constructed Daemon instance with injected clock;
    # without argument we construct a default Daemon.
    if daemon is None:
        daemon = Daemon(clock=SystemDaemonClock())

    active_clock = daemon.clock

    daemon._log.info(
        "daemon.startup",
        python_version=sys.version,
        clock_type=type(active_clock).__name__,
    )

    send_stream, recv_stream = anyio.create_memory_object_stream[IntentRequest](
        max_buffer_size=DEFAULT_BUFFER_SIZE,
    )

    event_bus = InProcessEventBus()  # Daemon-scoped EventBus, lebt so lang wie der Daemon

    async with anyio.create_task_group() as tg:
        tg.start_soon(_pe_nursery.run_programmatic_executor_bc, recv_stream, active_clock, event_bus)
        tg.start_soon(_is_nursery.run_interactive_surface_bc, send_stream, active_clock)
        # run_ws_push_server lebt im PE-BC-Nursery (intern in run_programmatic_executor_bc gespawnt).
        # send_stream.clone() — IS-BC-Nursery macht `async with queue_send:` was die
        # send-end beim Verlassen schließt; HTTP-Endpoint braucht eigene Clone-Ref.
        tg.start_soon(run_http_server, send_stream.clone(), active_clock, daemon.http_host, daemon.http_port)
