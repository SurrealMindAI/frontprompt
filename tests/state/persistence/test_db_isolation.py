"""Regression: the test suite must never touch the user's production state DB.

The autouse ``_isolate_state_db`` fixture in the top-level ``tests/conftest.py``
points ``FRONTPROMPT_STATE_DIR`` at a per-run tmp dir for the ENTIRE suite, so
no test — including browser/overlay integration tests that spawn
``frontprompt show`` subprocesses (which inherit ``os.environ``) — can write the
real ``~/.local/state/frontprompt/state.db``.
"""

from __future__ import annotations

import os
from pathlib import Path

from frontprompt.state.persistence.paths import state_db_path


def _production_db_path() -> Path:
    """The path the suite must NOT resolve to nor create: the real XDG default."""
    xdg = os.environ.get("XDG_STATE_HOME")
    base = Path(xdg) if xdg else Path.home() / ".local" / "state"
    return base / "frontprompt" / "state.db"


def test_state_db_path_redirected_away_from_production() -> None:
    """Under the autouse fixture, state_db_path() resolves into the tmp override."""
    override_dir = os.environ.get("FRONTPROMPT_STATE_DIR")
    assert override_dir, "autouse fixture must set FRONTPROMPT_STATE_DIR"

    resolved = state_db_path()
    assert resolved == Path(override_dir) / "state.db"
    assert resolved != _production_db_path()


def test_production_db_not_created_by_suite() -> None:
    """The real production DB file must not be created while running tests.

    Only asserts non-creation when the prod file did not already exist — we never
    delete a pre-existing user DB. The override redirect (asserted above) is what
    actually guarantees isolation; this is the belt-and-braces file check.
    """
    prod = _production_db_path()
    if prod.exists():
        # Pre-existing user DB — can't distinguish suite-writes here; the
        # redirect assertion in the sibling test already proves isolation.
        return
    state_db_path()  # resolve under the fixture
    assert not prod.exists(), f"suite must not create production DB at {prod}"
