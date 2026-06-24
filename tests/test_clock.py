"""Tests for DaemonClock — synchronous, no pytest-anyio needed."""

from __future__ import annotations

import time
from datetime import UTC, datetime

import pytest

from frontprompt.clock import DaemonClock, FrozenClock, MonotonicSnapshot, SystemDaemonClock

# ---------------------------------------------------------------------------
# MonotonicSnapshot
# ---------------------------------------------------------------------------


def test_monotonic_snapshot_is_frozen_dataclass() -> None:
    """MonotonicSnapshot muss immutable sein (frozen=True)."""
    snap = MonotonicSnapshot(value=42)
    with pytest.raises((AttributeError, TypeError)):
        snap.value = 99  # type: ignore[misc]


def test_monotonic_snapshot_equality() -> None:
    assert MonotonicSnapshot(value=0) == MonotonicSnapshot(value=0)
    assert MonotonicSnapshot(value=1) != MonotonicSnapshot(value=2)


# ---------------------------------------------------------------------------
# SystemDaemonClock
# ---------------------------------------------------------------------------


def test_system_clock_now_returns_utc_datetime() -> None:
    clock = SystemDaemonClock()
    result = clock.now()
    assert isinstance(result, datetime)
    assert result.tzinfo is UTC


def test_system_clock_monotonic_returns_snapshot() -> None:
    clock = SystemDaemonClock()
    snap = clock.monotonic()
    assert isinstance(snap, MonotonicSnapshot)
    assert snap.value > 0


def test_system_clock_monotonic_is_nondecreasing() -> None:
    """Zwei aufeinander folgende Aufrufe liefern einen nicht-abnehmenden Wert."""
    clock = SystemDaemonClock()
    a = clock.monotonic()
    b = clock.monotonic()
    assert b.value >= a.value


def test_system_clock_idempotency_ttl_not_expired() -> None:
    clock = SystemDaemonClock()
    snapshot = clock.monotonic()
    # Unmittelbar danach: noch nicht abgelaufen (TTL = 300 Sekunden)
    ttl_ns = 300 * 1_000_000_000
    assert clock.idempotency_ttl_expired(snapshot, ttl_ns) is False


def test_system_clock_idempotency_ttl_expired_for_past_snapshot() -> None:
    """Snapshot der 400 Sekunden in der Vergangenheit liegt → expired."""
    clock = SystemDaemonClock()
    past_ns = time.monotonic_ns() - 400 * 1_000_000_000
    snapshot = MonotonicSnapshot(value=past_ns)
    ttl_ns = 300 * 1_000_000_000
    assert clock.idempotency_ttl_expired(snapshot, ttl_ns) is True


# ---------------------------------------------------------------------------
# FrozenClock — test-double
# ---------------------------------------------------------------------------


def test_frozen_clock_now_returns_configured_wall() -> None:
    wall = datetime(2026, 1, 1, tzinfo=UTC)
    clock = FrozenClock(monotonic_ns=0, wall=wall)
    assert clock.now() == wall


def test_frozen_clock_monotonic_returns_configured_ns() -> None:
    clock = FrozenClock(monotonic_ns=12345, wall=datetime(2026, 1, 1, tzinfo=UTC))
    snap = clock.monotonic()
    assert snap.value == 12345


def test_frozen_clock_ttl_not_expired_when_equal() -> None:
    """Genau gleich: (current - snapshot) == ttl_ns → noch NICHT expired (strict >)."""
    clock = FrozenClock(monotonic_ns=1_000)
    snapshot = MonotonicSnapshot(value=700)
    ttl_ns = 300
    # current - snapshot = 300 == ttl_ns → NOT expired (strict >, kein >=)
    assert clock.idempotency_ttl_expired(snapshot, ttl_ns) is False


def test_frozen_clock_ttl_expired_after_boundary() -> None:
    """current - snapshot = 301 > ttl_ns=300 → expired."""
    clock = FrozenClock(monotonic_ns=1_001)
    snapshot = MonotonicSnapshot(value=700)
    ttl_ns = 300
    assert clock.idempotency_ttl_expired(snapshot, ttl_ns) is True


def test_frozen_clock_substitutable_as_daemon_clock() -> None:
    """Structural Protocol-Konformität: FrozenClock erfüllt DaemonClock ohne explizite Vererbung."""

    def accepts_clock(clock: DaemonClock) -> MonotonicSnapshot:
        return clock.monotonic()

    frozen: DaemonClock = FrozenClock(monotonic_ns=999)
    snap = accepts_clock(frozen)
    assert snap.value == 999


def test_system_clock_substitutable_as_daemon_clock() -> None:
    def accepts_clock(clock: DaemonClock) -> datetime:
        return clock.now()

    system: DaemonClock = SystemDaemonClock()
    result = accepts_clock(system)
    assert result.tzinfo is UTC
