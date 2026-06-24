"""Bounded page-op timeouts — never let a wedged page hang a tool call.

At spawn the show-child loads persistence (~hundreds of picks) and pushes a
large StateSnapshot through the expose_function bridge on every state change,
re-rendering dozens of overlay boxes. During such bulk operations the page JS
thread is pinned, so a ``page.evaluate`` roundtrip can never complete — leaving
the daemon's IPC recv blocked forever.

Every page op (page_info, navigate, scroll, eval_js, dom_patch, screenshots,
xpath) is bounded by :func:`with_page_op_timeout`. On timeout the helper raises
the typed :class:`PageOpTimeoutError`, which the IPC dispatcher catches and turns
into a clean ``IpcResponse(ok=False, error="page_op_timeout: <op>")`` — so the
show-side always replies and the dispatch slot frees.
"""

from __future__ import annotations

from collections.abc import Awaitable, Callable

import anyio
import structlog

_LOG = structlog.get_logger(__name__)

#: Finite wall-clock bound for a single Playwright page operation, in seconds.
#: Runtime-latency constant (not magic number): a healthy page.evaluate roundtrip
#: completes in milliseconds; 10s only ever fires on a genuinely wedged page.
PAGE_OP_TIMEOUT_S: float = 10.0


class PageOpTimeoutError(RuntimeError):
    """A bounded page operation exceeded its timeout.

    Carries ``op`` (the page-op name) so the dispatcher can surface a precise
    ``page_op_timeout: <op>`` error to the MCP caller.
    """

    def __init__(self, op: str, timeout: float) -> None:
        self.op = op
        self.timeout = timeout
        super().__init__(f"page op {op!r} exceeded {timeout}s timeout")


async def with_page_op_timeout[T](
    op: str,
    op_fn: Callable[[], Awaitable[T]],
    *,
    timeout: float = PAGE_OP_TIMEOUT_S,
) -> T:
    """Run ``op_fn()`` under a bounded timeout.

    On timeout, logs a structured ``page_op.timeout`` event and raises
    :class:`PageOpTimeoutError` (caught by the IPC dispatcher).
    """
    try:
        with anyio.fail_after(timeout):
            return await op_fn()
    except TimeoutError as exc:
        _LOG.warning("page_op.timeout", op=op, timeout_s=timeout)
        raise PageOpTimeoutError(op, timeout) from exc


__all__ = ["PAGE_OP_TIMEOUT_S", "PageOpTimeoutError", "with_page_op_timeout"]
