"""frontprompt.state.persistence — persistence package.

Public surface:

- :class:`StatePersistence` — the Protocol (interface)
- :class:`InMemoryPersistence` — no-op default / test double
- :class:`SqlitePersistence` — disk-backed SQLite implementation
- :func:`make_persistence` — factory: returns SqlitePersistence or falls back to InMemoryPersistence
- :func:`state_db_path` — XDG-aware DB path resolver
"""

from __future__ import annotations

from frontprompt.state.persistence.in_memory import InMemoryPersistence
from frontprompt.state.persistence.paths import state_db_path
from frontprompt.state.persistence.protocol import StatePersistence
from frontprompt.state.persistence.sqlite import SqlitePersistence, make_persistence

__all__ = [
    "InMemoryPersistence",
    "SqlitePersistence",
    "StatePersistence",
    "make_persistence",
    "state_db_path",
]
