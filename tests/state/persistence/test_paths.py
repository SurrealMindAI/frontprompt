"""Tests for frontprompt.state.persistence.paths — state_db_path() resolution."""

from __future__ import annotations

from pathlib import Path

import pytest


def test_paths_xdg_state_home(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> None:
    """state_db_path() uses XDG_STATE_HOME when set, under frontprompt/state.db."""
    monkeypatch.delenv("FRONTPROMPT_STATE_DB", raising=False)
    monkeypatch.delenv("FRONTPROMPT_STATE_DIR", raising=False)
    monkeypatch.setenv("XDG_STATE_HOME", str(tmp_path))

    from frontprompt.state.persistence.paths import state_db_path

    result = state_db_path()
    assert result == tmp_path / "frontprompt" / "state.db"


def test_paths_default_local_state(monkeypatch: pytest.MonkeyPatch) -> None:
    """state_db_path() falls back to ~/.local/state/frontprompt/state.db when XDG_STATE_HOME unset."""
    monkeypatch.delenv("FRONTPROMPT_STATE_DB", raising=False)
    monkeypatch.delenv("FRONTPROMPT_STATE_DIR", raising=False)
    monkeypatch.delenv("XDG_STATE_HOME", raising=False)

    from frontprompt.state.persistence.paths import state_db_path

    result = state_db_path()
    assert result == Path.home() / ".local" / "state" / "frontprompt" / "state.db"


def test_paths_override_env(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> None:
    """FRONTPROMPT_STATE_DB env var overrides all XDG resolution."""
    override = tmp_path / "custom" / "state.db"
    monkeypatch.setenv("FRONTPROMPT_STATE_DB", str(override))
    monkeypatch.setenv("XDG_STATE_HOME", str(tmp_path / "ignored"))

    from frontprompt.state.persistence.paths import state_db_path

    result = state_db_path()
    assert result == override


def test_paths_state_dir_override(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> None:
    """FRONTPROMPT_STATE_DIR derives state.db under the given dir, above XDG."""
    monkeypatch.delenv("FRONTPROMPT_STATE_DB", raising=False)
    state_dir = tmp_path / "run-isolated"
    monkeypatch.setenv("FRONTPROMPT_STATE_DIR", str(state_dir))
    monkeypatch.setenv("XDG_STATE_HOME", str(tmp_path / "ignored"))

    from frontprompt.state.persistence.paths import state_db_path

    result = state_db_path()
    assert result == state_dir / "state.db"


def test_paths_state_db_wins_over_state_dir(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> None:
    """FRONTPROMPT_STATE_DB (full file path) takes precedence over FRONTPROMPT_STATE_DIR."""
    override = tmp_path / "explicit" / "state.db"
    monkeypatch.setenv("FRONTPROMPT_STATE_DB", str(override))
    monkeypatch.setenv("FRONTPROMPT_STATE_DIR", str(tmp_path / "dir-ignored"))

    from frontprompt.state.persistence.paths import state_db_path

    result = state_db_path()
    assert result == override
