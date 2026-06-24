"""State DB path resolution — XDG-aware with env-override support.

Resolution order (first match wins):

1. ``FRONTPROMPT_STATE_DB`` — full path to the ``state.db`` file. Most explicit.
2. ``FRONTPROMPT_STATE_DIR`` — a directory; ``state.db`` is derived under it.
   This is the **preferred** override (e.g. the pytest autouse fixture points it
   at a per-run tmp dir so no test ever writes the user's real DB, and the
   ``frontprompt show`` subprocess inherits it via the spawned child's env).
3. ``$XDG_STATE_HOME/frontprompt/state.db`` — when XDG_STATE_HOME is set.
4. ``~/.local/state/frontprompt/state.db`` — XDG default fallback.

When none of the override env vars are set the resolution is unchanged.
"""

from __future__ import annotations

import os
from pathlib import Path


def state_dir() -> Path:
    """Resolve the directory that holds ``state.db``.

    Honours ``FRONTPROMPT_STATE_DIR`` (preferred override), then XDG, then the
    ``~/.local/state`` default. ``FRONTPROMPT_STATE_DB`` is handled one level up
    in :func:`state_db_path` because it names the file directly, not the dir.

    Returns:
        Absolute :class:`~pathlib.Path` to the ``frontprompt`` state directory.
        Not guaranteed to exist — callers that need it must ``mkdir`` themselves.
    """
    state_dir_override = os.environ.get("FRONTPROMPT_STATE_DIR")
    if state_dir_override:
        return Path(state_dir_override)

    xdg_state = os.environ.get("XDG_STATE_HOME")
    base = Path(xdg_state) if xdg_state else Path.home() / ".local" / "state"
    return base / "frontprompt"


def state_db_path() -> Path:
    """Resolve the SQLite state database path.

    Honour environment overrides so tests can redirect to a tmp_path without
    patching home-directory resolution. See module docstring for the full
    resolution order.

    Returns:
        Absolute :class:`~pathlib.Path` to the state.db file. The path is not
        guaranteed to exist yet — callers that need the directory must call
        ``path.parent.mkdir(parents=True, exist_ok=True)`` themselves.
    """
    db_override = os.environ.get("FRONTPROMPT_STATE_DB")
    if db_override:
        return Path(db_override)

    return state_dir() / "state.db"


__all__ = ["state_db_path", "state_dir"]
