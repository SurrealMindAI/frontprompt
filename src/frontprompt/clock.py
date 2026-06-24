"""DaemonClock — single source of truth for time inside the frontprompt daemon.

Daemon wall-clock as idempotency-truth (see ARCHITECTURE.md):

* **Wall-clock** (``datetime`` UTC) is for display only (audit logs, MCP responses).
* **Monotonic clock** (``time.monotonic_ns``) is the truth for TTL math: NTP jumps
  cannot move it backwards, DST transitions cannot skew it.
* **ULID time-prefix** is a sort-hint, not an ordering truth. Hard ordering
  invariants live in per-aggregate LSNs — out of scope for this lib.

Pattern from a WebSocket+JSON-RPC server library — do not diverge signatures.

Production default is :class:`SystemDaemonClock`. Test-doubles implement the
Protocol structurally — no inheritance required (see :class:`FrozenClock`).
"""

from __future__ import annotations

import time
from dataclasses import dataclass, field
from datetime import UTC, datetime
from typing import Protocol


@dataclass(frozen=True, slots=True)
class MonotonicSnapshot:
    """Opaque snapshot of the daemon's monotonic clock at one instant.

    Compared via ``other.value - self.value`` (nanoseconds), never serialised over
    the wire — monotonic time has no meaning across processes.
    """

    value: int  # nanoseconds, opaque epoch (do not interpret as wall-clock)


class DaemonClock(Protocol):
    """Protocol the daemon holds. Default impl is ``SystemDaemonClock``; tests
    swap in ``FrozenClock`` via constructor arguments.
    """

    def now(self) -> datetime:
        """Wall-clock UTC, ISO 8601 display-only. **Never** for TTL math."""
        ...

    def monotonic(self) -> MonotonicSnapshot:
        """Monotonic snapshot. The truth for TTL / Idempotency-Key validation."""
        ...

    def idempotency_ttl_expired(
        self,
        snapshot: MonotonicSnapshot,
        ttl_ns: int,
    ) -> bool:
        """Return True iff (current_monotonic - snapshot) > ttl_ns."""
        ...


class SystemDaemonClock:
    """Production :class:`DaemonClock` — wraps stdlib ``time`` / ``datetime``.

    Hot-path: :meth:`monotonic` allocates one :class:`MonotonicSnapshot` per call
    and :meth:`idempotency_ttl_expired` does one subtraction + comparison. No I/O.
    """

    def now(self) -> datetime:
        """Wall-clock UTC, ISO 8601 display-only. **Never** for TTL math."""
        return datetime.now(tz=UTC)

    def monotonic(self) -> MonotonicSnapshot:
        """Monotonic snapshot. The truth for TTL / Idempotency-Key validation."""
        return MonotonicSnapshot(value=time.monotonic_ns())

    def idempotency_ttl_expired(
        self,
        snapshot: MonotonicSnapshot,
        ttl_ns: int,
    ) -> bool:
        """Return True iff (current_monotonic - snapshot) > ttl_ns."""
        return (time.monotonic_ns() - snapshot.value) > ttl_ns


@dataclass
class FrozenClock:
    """Deterministic :class:`DaemonClock` test-double.

    Structurally conforms to the ``DaemonClock`` Protocol — mypy strict verifies
    this when callers type-annotate ``clock: DaemonClock``.

    Time is **frozen**: ``now()`` and ``monotonic()`` return the same value on
    every call unless the caller mutates ``wall`` or ``monotonic_ns``. This is
    what unit tests want — assert exact timestamps without race windows.

    Default state mirrors a conftest FrozenClock:
    ``monotonic_ns=0``, ``wall=2026-01-01T00:00:00+00:00``.
    """

    monotonic_ns: int = 0
    wall: datetime = field(default_factory=lambda: datetime(2026, 1, 1, tzinfo=UTC))

    def now(self) -> datetime:
        return self.wall

    def monotonic(self) -> MonotonicSnapshot:
        return MonotonicSnapshot(value=self.monotonic_ns)

    def idempotency_ttl_expired(
        self,
        snapshot: MonotonicSnapshot,
        ttl_ns: int,
    ) -> bool:
        """Return True iff (self.monotonic_ns - snapshot.value) > ttl_ns."""
        return (self.monotonic_ns - snapshot.value) > ttl_ns
