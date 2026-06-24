"""Session metadata + lifecycle + discovery.

Eine Session = eine running ``frontprompt show <url>`` instance. Hat:
    - session_id (timestamp + random)
    - pid (für liveness-check via os.kill(pid, 0))
    - url (was wir gerade rendern)
    - started_at (ISO timestamp UTC)
    - socket_path (wo client connecten kann)

Lifecycle (siehe :func:`session_lifecycle`):
    1. ``mkdir`` session-dir
    2. ``write`` session.json mit pid + url + started_at
    3. yield Session (caller startet socket-server + browser)
    4. cleanup: rm socket + rm session.json + rmdir session-dir

Discovery (siehe :func:`discover_sessions` / :func:`pick_latest_session`):
    Enumeriert :func:`paths.sessions_root`, parsed session.json, prüft pid alive.
    Tote sessions werden geskipped (caller kann via :func:`prune_dead_sessions`
    aufräumen).
"""

from __future__ import annotations

import os
from collections.abc import AsyncIterator
from contextlib import asynccontextmanager
from datetime import UTC, datetime
from pathlib import Path

import structlog
from pydantic import BaseModel, ConfigDict, Field, ValidationError

from frontprompt.ipc.paths import (
    metadata_path_for,
    new_session_id,
    session_dir,
    sessions_root,
    socket_path_for,
)

_LOG = structlog.get_logger(__name__)


# ----------------------------------------------------------------------------
# Ready-line (MCP-daemon ↔ show-child discovery)
# ----------------------------------------------------------------------------

_READY_PREFIX = "frontprompt:ready "


def format_ready_line(session_id: str) -> str:
    """Build the machine-readable ready-line printed by ``frontprompt show`` on stdout.

    The MCP-daemon parses this line from its spawned show-child's stdout to learn
    the child's session-id, then reads ``session.json`` for the full metadata.
    Format is intentionally minimal: the session-id alone is enough to locate
    everything else on disk.
    """
    return f"{_READY_PREFIX}{session_id}"


def parse_ready_line(line: str) -> str | None:
    """Inverse of :func:`format_ready_line`. Returns ``None`` for non-matching lines."""
    stripped = line.rstrip("\r\n")
    if not stripped.startswith(_READY_PREFIX):
        return None
    sid = stripped[len(_READY_PREFIX) :].strip()
    return sid or None


# ----------------------------------------------------------------------------
# Models
# ----------------------------------------------------------------------------


class SessionMetadata(BaseModel):
    """Persistierter session-state auf disk (session.json)."""

    model_config = ConfigDict(extra="forbid")

    session_id: str = Field(description="Vollständige session-id (ts + rand).")
    pid: int = Field(description="OS-PID des running ``frontprompt show``-process.")
    url: str = Field(
        description=(
            "Geöffnete URL. Unsanitised — passed directly from CLI arg / browser navigation. "
            "TODO(Phase-2 web UI): HTML-escape before rendering in any server-generated HTML surface."
        ),
    )
    started_at_iso: str = Field(description="ISO-8601 UTC timestamp des starts.")
    socket_path: str = Field(description="Voller pfad zum unix-socket.")

    @classmethod
    def for_current_process(cls, *, session_id: str, url: str) -> SessionMetadata:
        return cls(
            session_id=session_id,
            pid=os.getpid(),
            url=url,
            started_at_iso=datetime.now(UTC).isoformat(timespec="seconds"),
            socket_path=str(socket_path_for(session_id)),
        )


# ----------------------------------------------------------------------------
# Lifecycle (für `frontprompt show`)
# ----------------------------------------------------------------------------


@asynccontextmanager
async def session_lifecycle(*, url: str) -> AsyncIterator[SessionMetadata]:
    """Async-context-manager: create session-dir + metadata, yield, cleanup.

    Verwendung in :func:`frontprompt.cli._show_async_main`::

        async with session_lifecycle(url=url) as session:
            tg.start_soon(run_socket_server, state_manager, Path(session.socket_path))
            ...
    """
    session_id = new_session_id()
    sdir = session_dir(session_id)
    # session.json contains PID and URL — must not be world-readable.
    # mkdir mode=0o700 alone is subject to the process umask on macOS and may
    # produce 0o755 instead of 0o700. We therefore always follow with os.chmod
    # to guarantee the permission bits regardless of umask (Linux + macOS safe).
    sdir.mkdir(parents=True, exist_ok=True)
    os.chmod(sdir, 0o700)
    meta = SessionMetadata.for_current_process(session_id=session_id, url=url)
    # atomic write via tempfile+rename — prune_dead_sessions reads session.json
    # and misidentifying a live session as dead would be catastrophic. A partial write
    # during startup could produce invalid JSON. Using Path.replace() which is atomic
    # on POSIX (rename syscall, same filesystem guaranteed since .tmp is a sibling).
    metadata_path = metadata_path_for(session_id)
    metadata_tmp = metadata_path.with_suffix(".tmp")
    metadata_tmp.write_text(meta.model_dump_json(indent=2), encoding="utf-8")
    metadata_tmp.replace(metadata_path)
    _LOG.info(
        "ipc.session.started",
        session_id=session_id,
        pid=meta.pid,
        socket=meta.socket_path,
        url=url,
    )
    try:
        yield meta
    finally:
        for path in (Path(meta.socket_path), metadata_path_for(session_id)):
            if path.exists():
                try:
                    path.unlink()
                except OSError as exc:
                    _LOG.warning("ipc.session.cleanup_failed", path=str(path), error=str(exc))
        try:
            sdir.rmdir()
        except OSError:
            # Dir nicht leer (z.B. ein anderer process hat was reingelegt) — OK.
            pass
        _LOG.info("ipc.session.stopped", session_id=session_id)


# ----------------------------------------------------------------------------
# Discovery (für `frontprompt picks` / `state` / `sessions list`)
# ----------------------------------------------------------------------------


def _pid_alive(pid: int) -> bool:
    """``os.kill(pid, 0)`` — kein signal, nur permission/existence-check."""
    try:
        os.kill(pid, 0)
        return True
    except ProcessLookupError:
        return False
    except PermissionError:
        # PID existiert aber gehört anderem user — treat as alive (kann nicht killen aber läuft)
        return True


def _read_metadata(metadata_file: Path) -> SessionMetadata | None:
    try:
        return SessionMetadata.model_validate_json(metadata_file.read_text(encoding="utf-8"))
    except (ValidationError, OSError) as exc:
        _LOG.warning("ipc.session.metadata_unreadable", path=str(metadata_file), error=str(exc))
        return None


def discover_sessions() -> list[SessionMetadata]:
    """Enumeriere alle LEBENDEN sessions (sortiert nach started_at_iso, newest first).

    Tote sessions (PID nicht mehr da) werden geskipped — aber NICHT aufgeräumt;
    dafür ist :func:`prune_dead_sessions`.

    Scale note: calls os.kill(pid, 0) once per session directory entry -- O(n)
    syscalls where n = number of directories in sessions_root. Acceptable at
    current scale (typically 0-3 concurrent sessions). Phase-2 optimisation if
    needed: batch-resolve via /proc on Linux or psutil.process_iter() if psutil
    is available; or cache results for the duration of a single CLI invocation.
    """
    root = sessions_root()
    if not root.exists():
        return []
    sessions: list[SessionMetadata] = []
    for entry in root.iterdir():
        if not entry.is_dir():
            continue
        meta_file = entry / "session.json"
        if not meta_file.is_file():
            continue
        meta = _read_metadata(meta_file)
        if meta is None:
            continue
        if not _pid_alive(meta.pid):
            continue
        sessions.append(meta)
    sessions.sort(key=lambda m: m.started_at_iso, reverse=True)
    return sessions


def pick_latest_session() -> SessionMetadata | None:
    """Convenience: newest alive session, oder None wenn keine läuft."""
    sessions = discover_sessions()
    return sessions[0] if sessions else None


def prune_dead_sessions() -> list[str]:
    """Removes orphan session-dirs (PID gone / metadata corrupt).

    Returns list von session-ids die entfernt wurden.
    """
    root = sessions_root()
    if not root.exists():
        return []
    pruned: list[str] = []
    for entry in root.iterdir():
        if not entry.is_dir():
            continue
        meta_file = entry / "session.json"
        meta = _read_metadata(meta_file) if meta_file.is_file() else None
        if meta is not None and _pid_alive(meta.pid):
            continue
        # Dead or unreadable → prune
        for child in entry.iterdir():
            try:
                child.unlink()
            except OSError:
                pass
        try:
            entry.rmdir()
            pruned.append(entry.name)
        except OSError as exc:
            _LOG.warning("ipc.session.prune_failed", path=str(entry), error=str(exc))
    return pruned


__all__ = [
    "SessionMetadata",
    "discover_sessions",
    "format_ready_line",
    "parse_ready_line",
    "pick_latest_session",
    "prune_dead_sessions",
    "session_lifecycle",
]
