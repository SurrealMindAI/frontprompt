"""Tests for run_daemon() — cancellation behaviour and startup logging."""

from __future__ import annotations

import anyio
import pytest


@pytest.mark.anyio
async def test_daemon_starts_and_stops_cleanly() -> None:
    """run_daemon() must cancel within 1 s without Exception or zombie-task."""
    from frontprompt.daemon import Daemon, run_daemon

    # http_port=0: OS picks a free port — avoids OSError: Address already in use
    # when multiple daemon tests run sequentially on the same port.
    daemon = Daemon(http_port=0)
    with anyio.move_on_after(1.0):
        await run_daemon(daemon=daemon)
    # move_on_after cancels scope; no exception exit = test green


@pytest.mark.anyio
async def test_daemon_accepts_frozen_clock() -> None:
    """run_daemon(Daemon(clock=FrozenClock())) must start and cancel cleanly."""
    from frontprompt.clock import FrozenClock
    from frontprompt.daemon import Daemon, run_daemon

    daemon = Daemon(clock=FrozenClock(), http_port=0)
    with anyio.move_on_after(1.0):
        await run_daemon(daemon=daemon)


@pytest.mark.anyio
async def test_daemon_binds_daemon_id_in_structlog() -> None:
    """daemon.startup log-event must contain daemon_id, python_version, clock_type."""
    import structlog.testing

    from frontprompt.daemon import Daemon, run_daemon

    with structlog.testing.capture_logs() as cap:
        with anyio.move_on_after(0.2):
            await run_daemon(daemon=Daemon(http_port=0))

    startup = [e for e in cap if e.get("event") == "daemon.startup"]
    assert len(startup) >= 1, "daemon.startup event not found"
    ev = startup[0]
    assert "daemon_id" in ev
    assert "python_version" in ev
    assert "clock_type" in ev
