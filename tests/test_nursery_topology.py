"""Tests for the anyio nursery topology — outer TG → BC-TGs."""

from __future__ import annotations

import anyio
import pytest


@pytest.mark.anyio
async def test_both_bc_nurseries_start_under_daemon() -> None:
    """Both BC-nurseries must be started when run_daemon() runs."""
    import frontprompt.bc.interactive_surface.nursery as is_mod
    import frontprompt.bc.programmatic_executor.nursery as pe_mod

    started: list[str] = []

    original_pe = pe_mod.run_programmatic_executor_bc
    original_is = is_mod.run_interactive_surface_bc

    async def _patched_pe(queue_recv: object, clock: object, event_bus: object) -> None:
        started.append("pe")
        await original_pe(queue_recv, clock, event_bus)  # type: ignore[arg-type]

    async def _patched_is(queue_send: object, clock: object) -> None:
        started.append("is")
        await original_is(queue_send, clock)  # type: ignore[arg-type]

    pe_mod.run_programmatic_executor_bc = _patched_pe  # type: ignore[assignment]
    is_mod.run_interactive_surface_bc = _patched_is  # type: ignore[assignment]

    from frontprompt.daemon import Daemon, run_daemon

    try:
        with anyio.move_on_after(0.5):
            await run_daemon(daemon=Daemon(http_port=0))
    finally:
        pe_mod.run_programmatic_executor_bc = original_pe  # type: ignore[assignment]
        is_mod.run_interactive_surface_bc = original_is  # type: ignore[assignment]

    assert "pe" in started, "run_programmatic_executor_bc was not started"
    assert "is" in started, "run_interactive_surface_bc was not started"


@pytest.mark.anyio
async def test_outer_cancellation_propagates_to_bc_nurseries() -> None:
    """Cancel of the outer daemon scope cancels both BC-TaskGroups deterministically — no zombie."""
    import frontprompt.bc.interactive_surface.nursery as is_mod
    import frontprompt.bc.programmatic_executor.nursery as pe_mod

    cancelled: list[str] = []

    original_pe = pe_mod.run_programmatic_executor_bc
    original_is = is_mod.run_interactive_surface_bc

    async def _tracking_pe(queue_recv: object, clock: object, event_bus: object) -> None:
        try:
            await anyio.sleep_forever()
        except anyio.get_cancelled_exc_class():
            cancelled.append("pe")
            raise

    async def _tracking_is(queue_send: object, clock: object) -> None:
        try:
            await anyio.sleep_forever()
        except anyio.get_cancelled_exc_class():
            cancelled.append("is")
            raise

    pe_mod.run_programmatic_executor_bc = _tracking_pe  # type: ignore[assignment]
    is_mod.run_interactive_surface_bc = _tracking_is  # type: ignore[assignment]

    from frontprompt.daemon import Daemon, run_daemon

    try:
        with anyio.move_on_after(0.3):
            await run_daemon(daemon=Daemon(http_port=0))
    finally:
        pe_mod.run_programmatic_executor_bc = original_pe  # type: ignore[assignment]
        is_mod.run_interactive_surface_bc = original_is  # type: ignore[assignment]

    assert "pe" in cancelled, "run_programmatic_executor_bc was not cancelled"
    assert "is" in cancelled, "run_interactive_surface_bc was not cancelled"
