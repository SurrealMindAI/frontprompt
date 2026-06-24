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
