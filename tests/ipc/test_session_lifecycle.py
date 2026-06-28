"""Session lifecycle + discovery tests.

Nutzen ``FRONTPROMPT_CACHE_DIR`` env-override für isolation pro test.
"""

from __future__ import annotations

import os
from pathlib import Path

import pytest

from frontprompt.ipc import (
    SessionMetadata,
    discover_sessions,
    pick_latest_session,
    prune_dead_sessions,
    session_lifecycle,
)


@pytest.fixture
def isolated_cache(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> Path:
    """Pro test eigenes cache-dir via env-override."""
    monkeypatch.setenv("FRONTPROMPT_CACHE_DIR", str(tmp_path))
    return tmp_path


def test_no_sessions_returns_empty_list(isolated_cache: Path) -> None:
    """Frisches cache-dir → keine sessions."""
    assert discover_sessions() == []
    assert pick_latest_session() is None


@pytest.mark.anyio
async def test_session_lifecycle_creates_dir_and_metadata(isolated_cache: Path) -> None:
    async with session_lifecycle(url="https://example.com") as session:
        sdir = isolated_cache / "sessions" / session.session_id
        assert sdir.is_dir()
        assert (sdir / "session.json").is_file()
        meta = SessionMetadata.model_validate_json((sdir / "session.json").read_text())
        assert meta.session_id == session.session_id
        assert meta.pid == os.getpid()
        assert meta.url == "https://example.com"


@pytest.mark.anyio
async def test_session_lifecycle_cleans_up_on_exit(isolated_cache: Path) -> None:
    sdir_path: Path | None = None
    async with session_lifecycle(url="https://example.com") as session:
        sdir_path = isolated_cache / "sessions" / session.session_id
        assert sdir_path.is_dir()
    assert sdir_path is not None
    assert not sdir_path.exists(), "session-dir sollte nach lifecycle-exit weg sein"


@pytest.mark.anyio
async def test_discover_sees_alive_session(isolated_cache: Path) -> None:
    async with session_lifecycle(url="https://x/") as session:
        found = discover_sessions()
        assert len(found) == 1
        assert found[0].session_id == session.session_id
        assert found[0].url == "https://x/"
        # latest convenience returns same
        latest = pick_latest_session()
        assert latest is not None
        assert latest.session_id == session.session_id


@pytest.mark.anyio
async def test_multiple_parallel_sessions_each_distinct(isolated_cache: Path) -> None:
    """Multi-instance — verschiedene session-ids, verschiedene socket-paths."""
    async with session_lifecycle(url="https://a/") as s1:
        async with session_lifecycle(url="https://b/") as s2:
            assert s1.session_id != s2.session_id
            assert s1.socket_path != s2.socket_path
            found = discover_sessions()
            ids = {s.session_id for s in found}
            assert {s1.session_id, s2.session_id} <= ids


def test_prune_dead_session_dir(isolated_cache: Path) -> None:
    """Wenn metadata-file PID nicht alive zeigt → prune cleant den dir."""
    sessions_dir = isolated_cache / "sessions"
    sessions_dir.mkdir(parents=True)
    fake_dir = sessions_dir / "20200101T000000-deaddead"
    fake_dir.mkdir()
    # Erfundenes PID (sehr unwahrscheinlich dass das gerade läuft)
    fake_pid = 999_999
    (fake_dir / "session.json").write_text(
        '{"session_id":"20200101T000000-deaddead","pid":999999,'
        '"url":"x","started_at_iso":"2020-01-01T00:00:00+00:00",'
        '"socket_path":"/tmp/x.sock"}',
        encoding="utf-8",
    )
    # Sicherstellen dass die fake-pid wirklich nicht läuft
    try:
        os.kill(fake_pid, 0)
        pytest.skip(f"PID {fake_pid} läuft zufällig — test skip")
    except (ProcessLookupError, PermissionError):
        pass

    pruned = prune_dead_sessions()
    assert "20200101T000000-deaddead" in pruned
    assert not fake_dir.exists()


def test_prune_skips_corrupt_metadata(isolated_cache: Path) -> None:
    """Metadata-Datei broken/JSON-invalid → behandle wie tote session, prune."""
    sessions_dir = isolated_cache / "sessions"
    sessions_dir.mkdir(parents=True)
    corrupt = sessions_dir / "broken-session"
    corrupt.mkdir()
    (corrupt / "session.json").write_text("not valid json {{", encoding="utf-8")

    pruned = prune_dead_sessions()
    assert "broken-session" in pruned


# ---------------------------------------------------------------------------
# session directory permissions
# ---------------------------------------------------------------------------


@pytest.mark.anyio
async def test_session_dir_has_0o700_permissions(isolated_cache: Path) -> None:
    """Session-dir muss 0o700 haben (nicht world-readable)."""
    import stat as _stat

    async with session_lifecycle(url="https://example.com") as session:
        sdir = isolated_cache / "sessions" / session.session_id
        mode = _stat.S_IMODE(sdir.stat().st_mode)
        assert mode == 0o700, f"Expected 0o700, got {oct(mode)}"


# ---------------------------------------------------------------------------
# atomic session.json write + prune-liveness invariant
# ---------------------------------------------------------------------------


@pytest.mark.anyio
async def test_session_metadata_write_is_valid_json(isolated_cache: Path) -> None:
    """session.json muss nach lifecycle valides SessionMetadata-JSON enthalten."""
    async with session_lifecycle(url="https://example.com") as session:
        sdir = isolated_cache / "sessions" / session.session_id
        raw = (sdir / "session.json").read_text(encoding="utf-8")
        meta = SessionMetadata.model_validate_json(raw)
        assert meta.session_id == session.session_id


@pytest.mark.anyio
async def test_prune_does_not_delete_live_session_dir(isolated_cache: Path) -> None:
    """prune_dead_sessions() darf eine lebende session NICHT löschen."""
    async with session_lifecycle(url="https://example.com") as session:
        sdir = isolated_cache / "sessions" / session.session_id
        pruned = prune_dead_sessions()
        assert session.session_id not in pruned, "live session must not be pruned"
        assert sdir.is_dir(), "live session dir must still exist after prune"


# ---------------------------------------------------------------------------
# discover_sessions edge cases — cover missing branch statements
# ---------------------------------------------------------------------------


def test_discover_skips_non_dir_entries_in_sessions_root(isolated_cache: Path) -> None:
    """Non-directory entries in sessions_root are skipped (line 202 continue)."""
    sessions_dir = isolated_cache / "sessions"
    sessions_dir.mkdir(parents=True)
    # Create a plain file (not a dir) inside sessions_root
    orphan_file = sessions_dir / "not-a-dir.txt"
    orphan_file.write_text("irrelevant", encoding="utf-8")

    result = discover_sessions()
    assert result == []


def test_discover_skips_dirs_without_session_json(isolated_cache: Path) -> None:
    """Dirs without session.json are skipped (line 205 continue)."""
    sessions_dir = isolated_cache / "sessions"
    sessions_dir.mkdir(parents=True)
    orphan_dir = sessions_dir / "20200101T000000-nosessionjson"
    orphan_dir.mkdir()
    # No session.json written

    result = discover_sessions()
    assert result == []


def test_discover_skips_dirs_with_corrupt_metadata(isolated_cache: Path) -> None:
    """Dirs with unreadable session.json are skipped (line 208 continue)."""
    sessions_dir = isolated_cache / "sessions"
    sessions_dir.mkdir(parents=True)
    corrupt_dir = sessions_dir / "20200101T000000-corrupt"
    corrupt_dir.mkdir()
    (corrupt_dir / "session.json").write_text("not valid json {{{", encoding="utf-8")

    result = discover_sessions()
    assert result == []


def test_discover_skips_dead_pid_sessions(isolated_cache: Path) -> None:
    """Sessions with dead PIDs are skipped in discover_sessions (line 210 continue)."""
    sessions_dir = isolated_cache / "sessions"
    sessions_dir.mkdir(parents=True)
    dead_dir = sessions_dir / "20200101T000000-deadpid"
    dead_dir.mkdir()
    # PID 999_999 is almost certainly not alive
    fake_pid = 999_999
    try:
        os.kill(fake_pid, 0)
        pytest.skip(f"PID {fake_pid} happens to be alive — skip")
    except (ProcessLookupError, PermissionError):
        pass
    (dead_dir / "session.json").write_text(
        '{"session_id":"20200101T000000-deadpid","pid":999999,'
        '"url":"https://x","started_at_iso":"2020-01-01T00:00:00+00:00",'
        '"socket_path":"/tmp/x.sock"}',
        encoding="utf-8",
    )

    result = discover_sessions()
    assert result == []


# ---------------------------------------------------------------------------
# prune_dead_sessions edge cases
# ---------------------------------------------------------------------------


def test_prune_returns_empty_list_when_sessions_root_missing(isolated_cache: Path) -> None:
    """prune_dead_sessions returns [] when sessions_root doesn't exist (line 229 return [])."""
    # isolated_cache exists but has no "sessions" subdir
    assert not (isolated_cache / "sessions").exists()
    pruned = prune_dead_sessions()
    assert pruned == []


def test_prune_skips_non_dir_entries_in_sessions_root(isolated_cache: Path) -> None:
    """Non-directory entries in sessions_root are skipped by prune (line 233 continue)."""
    sessions_dir = isolated_cache / "sessions"
    sessions_dir.mkdir(parents=True)
    orphan_file = sessions_dir / "file-not-dir.txt"
    orphan_file.write_text("garbage", encoding="utf-8")

    pruned = prune_dead_sessions()
    assert pruned == []
    assert orphan_file.exists(), "non-dir file must not be removed"


def test_prune_handles_rmdir_failure_gracefully(isolated_cache: Path) -> None:
    """prune_dead_sessions logs warning when entry.rmdir fails (lines 247-248)."""
    sessions_dir = isolated_cache / "sessions"
    sessions_dir.mkdir(parents=True)
    # Create a dead session dir
    dead_dir = sessions_dir / "20200101T000000-rmdir-fail"
    dead_dir.mkdir()
    fake_pid = 999_999
    try:
        os.kill(fake_pid, 0)
        pytest.skip(f"PID {fake_pid} happens to be alive")
    except (ProcessLookupError, PermissionError):
        pass
    (dead_dir / "session.json").write_text(
        '{"session_id":"20200101T000000-rmdir-fail","pid":999999,'
        '"url":"https://x","started_at_iso":"2020-01-01T00:00:00+00:00",'
        '"socket_path":"/tmp/x.sock"}',
        encoding="utf-8",
    )
    # Add a sub-file that can't be deleted to force rmdir failure,
    # then monkeypatch rmdir to raise
    extra_file = dead_dir / "extra.txt"
    extra_file.write_text("block", encoding="utf-8")

    # prune tries to unlink children first (line 240: child.unlink()),
    # then rmdir. If children unlink succeeds but rmdir still somehow fails,
    # lines 247-248 fire. We simulate by monkeypatching Path.rmdir on the
    # specific path via a wrapper approach.
    original_rmdir = Path.rmdir

    def failing_rmdir(self: Path) -> None:
        if self == dead_dir:
            raise OSError("simulated rmdir failure")
        original_rmdir(self)

    import unittest.mock as _mock

    with _mock.patch.object(Path, "rmdir", failing_rmdir):
        pruned = prune_dead_sessions()

    # rmdir failed → session-id NOT added to pruned but function completes
    assert "20200101T000000-rmdir-fail" not in pruned


# ---------------------------------------------------------------------------
# _pid_alive PermissionError branch
# ---------------------------------------------------------------------------


def test_pid_alive_permission_error_returns_true(monkeypatch: pytest.MonkeyPatch) -> None:
    """os.kill raising PermissionError → _pid_alive returns True (lines 171-173).

    A PermissionError means the PID exists but belongs to another user — alive.
    """
    import frontprompt.ipc.session as _session_mod

    def _raising_kill(pid: int, sig: int) -> None:
        raise PermissionError("not owner")

    monkeypatch.setattr(_session_mod.os, "kill", _raising_kill)
    # Access the private function via module for testing
    result = _session_mod._pid_alive(12345)
    assert result is True
