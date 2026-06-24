"""Central log configuration — per-session on-disk file sink + stderr console.

frontprompt logs via **structlog**. Historically every entry-point
(``frontprompt.cli.main``, ``frontprompt.build.main``) configured structlog to
render straight to stderr via ``PrintLoggerFactory`` + ``ConsoleRenderer``. When
the daemon / show-child runs under the MCP runner, stderr is swallowed — leaving
us with no on-disk record to debug hangs (e.g. ``frontprompt_get_page_info``
hanging with no trailing log line).

This module adds a **per-session on-disk JSON-lines sink** without removing the
stderr console output. A single structlog event now fans out to two stdlib
handlers:

1. stderr — :class:`structlog.dev.ConsoleRenderer` (unchanged dev experience)
2. file   — :class:`structlog.processors.JSONRenderer` (one JSON object per line)

The file lands at::

    ~/.cache/frontprompt/sessions/<session_id>/<role>.log   (session known)
    ~/.cache/frontprompt/logs/<pid>-<role>.log              (fallback)

— so a daemon writes ``daemon.log`` and a show-child writes ``show.log`` next to
the existing ``session.json`` + ``show.sock``. A hang leaves a dangling
``*.start`` line with no matching ``*.done`` as the last line of the file.

The fan-out is implemented by routing structlog through the stdlib ``logging``
module (``ProcessorFormatter`` pattern): the shared processor chain runs once,
then each handler applies its own renderer. This is the canonical structlog
recipe for "console + JSON file at the same time" and keeps a single logging
framework (no second framework introduced).
"""

from __future__ import annotations

import logging
import os
from pathlib import Path

import structlog

from frontprompt.ipc.paths import logs_root, session_log_path

# Logger name of the root stdlib logger we attach handlers to. All structlog
# events ultimately flow through stdlib logging via the LoggerFactory below.
_ROOT_LOGGER_NAME = "frontprompt"

#: Shared processors applied to every event before it reaches a per-handler
#: renderer. ``ProcessorFormatter.wrap_for_formatter`` MUST be the last entry so
#: the record is handed to the stdlib formatter for final rendering.
_SHARED_PROCESSORS: list[structlog.typing.Processor] = [
    structlog.contextvars.merge_contextvars,
    structlog.stdlib.add_log_level,
    structlog.stdlib.add_logger_name,
    structlog.processors.TimeStamper(fmt="iso", utc=True),
    structlog.processors.StackInfoRenderer(),
    structlog.processors.format_exc_info,
]


def _log_file_path(role: str, session_id: str | None) -> Path:
    """Resolve the on-disk log-file path for this process.

    ``session_id`` known  → ``<session-dir>/<role>.log``
    ``session_id`` is None → ``<logs-root>/<pid>-<role>.log``
    """
    if session_id is not None:
        return session_log_path(session_id, role)
    return logs_root() / f"{os.getpid()}-{role}.log"


def configure_logging(*, role: str, session_id: str | None = None) -> Path:
    """Install the dual stderr-console + per-session JSON-file logging config.

    Idempotent-ish: clears any previously installed handlers on the frontprompt
    root logger first, so calling it again (e.g. once a session_id becomes
    available) re-points the file sink cleanly.

    Args:
        role: process role — ``"daemon"`` or ``"show"`` — used in the file name.
        session_id: authoritative session-id if known at init; ``None`` falls
            back to a stable ``<pid>-<role>.log`` under ``logs/``.

    Returns:
        The resolved on-disk log-file path (also created on disk).
    """
    log_path = _log_file_path(role, session_id)
    log_path.parent.mkdir(parents=True, exist_ok=True)

    # structlog → stdlib bridge. The shared chain runs once per event; the final
    # ProcessorFormatter on each handler picks the per-handler renderer.
    structlog.configure(
        processors=[
            *_SHARED_PROCESSORS,
            structlog.stdlib.ProcessorFormatter.wrap_for_formatter,
        ],
        wrapper_class=structlog.stdlib.BoundLogger,
        context_class=dict,
        logger_factory=structlog.stdlib.LoggerFactory(),
        cache_logger_on_first_use=False,
    )

    console_formatter = structlog.stdlib.ProcessorFormatter(
        foreign_pre_chain=_SHARED_PROCESSORS,
        processors=[
            structlog.stdlib.ProcessorFormatter.remove_processors_meta,
            structlog.dev.ConsoleRenderer(colors=False),
        ],
    )
    file_formatter = structlog.stdlib.ProcessorFormatter(
        foreign_pre_chain=_SHARED_PROCESSORS,
        processors=[
            structlog.stdlib.ProcessorFormatter.remove_processors_meta,
            structlog.processors.JSONRenderer(),
        ],
    )

    stderr_handler = logging.StreamHandler()  # defaults to sys.stderr
    stderr_handler.setFormatter(console_formatter)

    file_handler = logging.FileHandler(str(log_path), encoding="utf-8")
    file_handler.setFormatter(file_formatter)

    root = logging.getLogger(_ROOT_LOGGER_NAME)
    # Replace any handlers from a prior configure_logging call.
    for handler in list(root.handlers):
        root.removeHandler(handler)
        try:
            handler.close()
        except Exception:  # best-effort handler cleanup
            pass
    root.addHandler(stderr_handler)
    root.addHandler(file_handler)
    root.setLevel(logging.DEBUG)
    # Don't double-emit through the python root logger.
    root.propagate = False

    return log_path


def reset_logging() -> None:
    """Tear down handlers installed by :func:`configure_logging`.

    Closes file handles and detaches them from the frontprompt root logger.
    Intended for test isolation; harmless in production teardown.
    """
    root = logging.getLogger(_ROOT_LOGGER_NAME)
    for handler in list(root.handlers):
        root.removeHandler(handler)
        try:
            handler.close()
        except Exception:  # best-effort handler cleanup
            pass
    structlog.reset_defaults()


__all__ = ["configure_logging", "reset_logging"]
