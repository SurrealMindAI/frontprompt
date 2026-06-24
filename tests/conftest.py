"""Shared pytest fixtures for frontprompt tests."""

from __future__ import annotations

import os
from collections.abc import Iterator
from pathlib import Path

import pytest


@pytest.fixture(scope="session", autouse=True)
def _isolate_state_db(tmp_path_factory: pytest.TempPathFactory) -> Iterator[Path]:
    """Redirect the state DB to a per-run tmp dir for the ENTIRE suite.

    Sets ``FRONTPROMPT_STATE_DIR`` (resolved by
    :func:`frontprompt.state.persistence.paths.state_db_path`) so NO test —
    including browser/overlay integration tests that spawn ``frontprompt show``
    subprocesses — ever writes the user's real
    ``~/.local/state/frontprompt/state.db``. The spawned child inherits the var
    via ``os.environ`` (``anyio.open_process`` passes the parent environment
    when no explicit ``env=`` is given), so isolation reaches into subprocesses.

    Mutates ``os.environ`` directly (not ``monkeypatch``) because the override
    must outlive function-scoped fixtures and be visible to subprocess spawns
    across the whole session.
    """
    state_dir = tmp_path_factory.mktemp("frontprompt-state")
    previous = os.environ.get("FRONTPROMPT_STATE_DIR")
    os.environ["FRONTPROMPT_STATE_DIR"] = str(state_dir)
    try:
        yield state_dir
    finally:
        if previous is None:
            os.environ.pop("FRONTPROMPT_STATE_DIR", None)
        else:
            os.environ["FRONTPROMPT_STATE_DIR"] = previous


@pytest.fixture
def anyio_backend() -> str:
    """Pin pytest-anyio backend to asyncio.

    Override per-test via
    ``@pytest.mark.parametrize("anyio_backend", ["asyncio", "trio"])``
    for backend-portability checks.
    """
    return "asyncio"
