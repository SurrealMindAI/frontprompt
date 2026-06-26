"""Filesystem-Pfade für IPC-sessions.

Layout:

    ~/.cache/frontprompt/
        sessions/
            20260519T170245-a1b2c3d4/       ← eine running session
                show.sock                   ← unix-socket
                session.json                ← metadata (pid, url, started_at)
            20260519T180110-1e2f3a4b/       ← parallele zweite session
                show.sock
                session.json

Multi-instance: jede ``frontprompt show``-instance kriegt ein eigenes
session-id (ISO-timestamp + 8-hex-random). Sortier-stabil chronologisch,
collision-frei (selbst beim selben sekundengenauen start).

Cleanup: bei ordentlichem exit löscht die session ihren eigenen ordner.
Bei kill -9 / OOM bleibt der ordner liegen — :func:`discover_sessions` skipped
ihn weil der PID nicht mehr läuft. Optional explicit cleanup via
:func:`prune_dead_sessions`.

Override via env:
    - ``FRONTPROMPT_CACHE_DIR`` — overrides ``~/.cache/frontprompt`` (tests)
"""

from __future__ import annotations

import os
import secrets
from datetime import UTC, datetime
from pathlib import Path

# ----------------------------------------------------------------------------
# Cache-root + sessions-root
# ----------------------------------------------------------------------------


def cache_root() -> Path:
    """Resolve frontprompt cache-root.

    Order: ``$FRONTPROMPT_CACHE_DIR`` → ``$XDG_CACHE_HOME/frontprompt`` →
    ``~/.cache/frontprompt``.
    """
    override = os.environ.get("FRONTPROMPT_CACHE_DIR")
    if override:
        return Path(override).expanduser()
    xdg = os.environ.get("XDG_CACHE_HOME")
    if xdg:
        return Path(xdg).expanduser() / "frontprompt"
    return Path.home() / ".cache" / "frontprompt"


def sessions_root() -> Path:
    """Root für alle session-dirs."""
    return cache_root() / "sessions"


def logs_root() -> Path:
    """Root für pid-fallback log-files (wenn keine session-id verfügbar ist).

    Wird genutzt wenn ein Prozess bei log-init noch keine session-id kennt
    (z.B. der MCP-Daemon, dessen show-child erst lazy beim ersten Tool-Call
    gespawnt wird). Layout: ``<cache-root>/logs/<pid>-<role>.log``.
    """
    return cache_root() / "logs"


# ----------------------------------------------------------------------------
# Per-session paths
# ----------------------------------------------------------------------------


def new_session_id() -> str:
    """Generate fresh session-id: ``YYYYMMDDTHHMMSS-<8 hex chars>``.

    Sortier-stabil + collision-frei (selbst bei gleichzeitigen starts).
    """
    ts = datetime.now(UTC).strftime("%Y%m%dT%H%M%S")
    rand = secrets.token_hex(4)
    return f"{ts}-{rand}"


def session_dir(session_id: str) -> Path:
    return sessions_root() / session_id


def socket_path_for(session_id: str) -> Path:
    return session_dir(session_id) / "show.sock"


def metadata_path_for(session_id: str) -> Path:
    return session_dir(session_id) / "session.json"


def session_log_path(session_id: str, role: str) -> Path:
    """On-disk log-file for a session-aware process: ``<session-dir>/<role>.log``.

    Lives alongside ``session.json`` + ``show.sock`` so all per-session artefacts
    are colocated. ``role`` is the process role (e.g. ``"daemon"``, ``"show"``).
    """
    return session_dir(session_id) / f"{role}.log"


def audio_path_for(session_id: str, recording_id: str) -> Path:
    """WAV audio path for a voice-over recording inside a session dir.

    Returns ``<session-dir>/recording-<recording_id>.wav``.

    The WAV is a durable source artifact — kept for mlx-whisper transcription
    after stop. Reclamation deferred to a future ``recordings clean-audio``
    command (COL-8: retention decision).
    """
    return session_dir(session_id) / f"recording-{recording_id}.wav"


__all__ = [
    "audio_path_for",
    "cache_root",
    "logs_root",
    "metadata_path_for",
    "new_session_id",
    "session_dir",
    "session_log_path",
    "sessions_root",
    "socket_path_for",
]
