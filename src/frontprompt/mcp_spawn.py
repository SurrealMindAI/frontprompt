"""Spawn a `frontprompt show` child for the MCP daemon.

Each MCP-daemon process owns exactly one private Browser-Session
that it spawns as a child via the `frontprompt show` CLI. This helper handles
the spawn handshake:

1. launch ``python -m frontprompt show <url>`` as a subprocess in its own session
   (``start_new_session=True``) so its process-group can be killed with one signal
2. read stdout line-by-line until the machine-readable ready-line matches
   (``frontprompt:ready <session_id>``, format defined in
   :func:`frontprompt.ipc.session.format_ready_line`)
3. load the child's full :class:`~frontprompt.ipc.session.SessionMetadata` from
   ``<cache>/sessions/<session_id>/session.json``
4. yield ``(process, metadata)`` for the daemon's MCP-tool layer to use as the
   IPC target for the lifetime of the MCP-session
5. on context exit: SIGTERM the child's process-group, wait bounded for clean exit

Anti-zombie property: ``start_new_session=True`` makes the child the leader of a
new process-group; ``os.killpg`` cascades the signal to the child plus its own
spawned chromium without leaking processes when the daemon exits.
"""

from __future__ import annotations

import os
import signal
import subprocess
import sys
from collections.abc import AsyncIterator
from contextlib import asynccontextmanager

import anyio
import anyio.abc
import structlog

from frontprompt.ipc.paths import session_dir
from frontprompt.ipc.session import SessionMetadata, parse_ready_line

_LOG = structlog.get_logger(__name__)

#: Maximum wait for the child's ready-line on stdout, in seconds. Generous default
#: — Playwright cold-boot plus overlay-bundle load can take a few seconds on first
#: invocation. Tests override to a small value.
READY_TIMEOUT_S: float = 30.0

#: Bound for waiting on child exit during teardown after SIGTERM.
TERM_WAIT_S: float = 5.0


class ShowSpawnError(RuntimeError):
    """Spawning the show-child or reading its ready-line failed."""


def _build_show_cmd(start_url: str) -> list[str]:
    """Build the subprocess argv for `frontprompt show <url>`.

    Uses ``python -m frontprompt`` rather than the bare ``frontprompt`` script so
    the daemon doesn't depend on the entry-point script being on PATH (the daemon
    may run from ``uv tool install`` where the script lives outside PATH).
    """
    return [sys.executable, "-m", "frontprompt", "show", start_url]


async def _read_ready_session_id(stdout: anyio.abc.ByteReceiveStream, timeout_s: float) -> str:
    """Read stdout line-by-line until a ready-line matches; return its session-id.

    Lines preceding the ready-line are forwarded as DEBUG log (typically structlog
    ConsoleRenderer output from the show-child's own boot).
    """
    buf = bytearray()
    with anyio.fail_after(timeout_s):
        while True:
            try:
                chunk = await stdout.receive(4096)
            except anyio.EndOfStream as exc:
                raise ShowSpawnError("show-child closed stdout before printing ready-line") from exc
            buf.extend(chunk)
            while b"\n" in buf:
                line_bytes, _, rest = buf.partition(b"\n")
                buf = bytearray(rest)
                line = line_bytes.decode("utf-8", errors="replace")
                sid = parse_ready_line(line)
                if sid is not None:
                    return sid
                _LOG.debug("mcp_spawn.show_stdout_pre_ready", line=line)


async def _read_stderr_tail(stderr: anyio.abc.ByteReceiveStream, max_wait_s: float = 0.5) -> str:
    """Best-effort read of pending stderr; returns the tail for error diagnosis.

    Used after a spawn failure to enrich the :class:`ShowSpawnError` message with
    the child's stderr (typical causes: missing overlay bundle, playwright not
    installed, package import failures). Bounded by ``max_wait_s`` so we don't
    block forever if the child is still alive but quiet.
    """
    buf = bytearray()
    with anyio.move_on_after(max_wait_s):
        try:
            while True:
                chunk = await stderr.receive(4096)
                buf.extend(chunk)
                if len(buf) > 4096:
                    break
        except anyio.EndOfStream:
            pass
    text = bytes(buf).decode("utf-8", errors="replace").strip()
    if not text:
        return "(empty)"
    if len(text) > 1500:
        return "..." + text[-1500:]
    return text


async def spawn_show_child_unmanaged(
    start_url: str,
) -> tuple[anyio.abc.Process, SessionMetadata]:
    """Spawn `frontprompt show <start_url>` and return its handle and metadata.

    Caller is responsible for the process lifetime — typically by calling
    :func:`terminate_show_child` when done. For RAII-style usage prefer the
    :func:`spawn_show_child` async context manager.

    Raises :class:`ShowSpawnError` if the child fails to print a ready-line
    within :data:`READY_TIMEOUT_S` seconds, or if the resulting session.json
    cannot be located on disk. The child's stderr tail is appended on error
    paths so callers can diagnose root-cause without digging into log files.
    """
    cmd = _build_show_cmd(start_url)
    _LOG.info("mcp_spawn.starting", cmd=cmd)
    process = await anyio.open_process(
        cmd,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        start_new_session=True,
    )
    try:
        assert process.stdout is not None and process.stderr is not None
        try:
            session_id = await _read_ready_session_id(process.stdout, READY_TIMEOUT_S)
        except TimeoutError as exc:
            stderr_tail = await _read_stderr_tail(process.stderr)
            raise ShowSpawnError(
                f"Timeout after {READY_TIMEOUT_S}s waiting for show-child ready-line. child stderr tail: {stderr_tail}"
            ) from exc
        except ShowSpawnError as exc:
            stderr_tail = await _read_stderr_tail(process.stderr)
            raise ShowSpawnError(f"{exc}. child stderr tail: {stderr_tail}") from exc

        meta_path = session_dir(session_id) / "session.json"
        if not meta_path.is_file():
            raise ShowSpawnError(f"show-child reported session {session_id!r} but session.json missing at {meta_path}")
        metadata = SessionMetadata.model_validate_json(meta_path.read_text(encoding="utf-8"))
        _LOG.info(
            "mcp_spawn.ready",
            session_id=metadata.session_id,
            socket=metadata.socket_path,
            child_pid=process.pid,
        )
        return process, metadata
    except BaseException:
        # On any failure path, the caller never gets the process handle — so
        # terminate it here, otherwise we leak a chromium that no one owns.
        await terminate_show_child(process)
        raise


async def terminate_show_child(process: anyio.abc.Process) -> None:
    """SIGTERM the child's process-group (lifetime coupling) and wait briefly.

    ``start_new_session=True`` at spawn time made the child its own session
    leader, so ``os.killpg`` cascades the signal to chromium and any other
    descendants. Bounded wait so we don't block daemon-exit forever.
    """
    try:
        os.killpg(os.getpgid(process.pid), signal.SIGTERM)
    except (ProcessLookupError, PermissionError):
        pass
    with anyio.move_on_after(TERM_WAIT_S):
        await process.wait()


@asynccontextmanager
async def spawn_show_child(
    start_url: str,
) -> AsyncIterator[tuple[anyio.abc.Process, SessionMetadata]]:
    """RAII wrapper around :func:`spawn_show_child_unmanaged` + :func:`terminate_show_child`.

    **Role: canonical test-layer entry-point for spawn-handshake unit tests.**

    The production code path does NOT use this function directly. Instead,
    :class:`~frontprompt.mcp_server.LazyBrowserSessionProvider` calls
    :func:`spawn_show_child_unmanaged` and :func:`terminate_show_child` directly
    so that it can manage the process lifetime independently of a context-manager
    scope. This RAII wrapper exists for the test layer:

    - All 5 tests in ``tests/test_mcp_spawn.py`` use ``async with spawn_show_child(...)``
      as their entry-point. It calls :func:`spawn_show_child_unmanaged` internally and
      always runs :func:`terminate_show_child` on context exit, eliminating manual
      teardown boilerplate in every test case.

    **This function is intentionally retained and is not dead code.**
    The premise that this is "obsolete after LazyBrowserSessionProvider"
    confused "not called by production code" with "dead code". Removing this wrapper
    would require rewriting all 5 spawn-handshake tests with explicit teardown or
    deleting them — neither is correct.

    See: docs/plans/2026-06-01-mcp-daemon-deadcode-cleanup/01-spawn-show-child-premise-verdict.md
    """
    process, metadata = await spawn_show_child_unmanaged(start_url)
    try:
        yield process, metadata
    finally:
        await terminate_show_child(process)


__all__ = [
    "READY_TIMEOUT_S",
    "ShowSpawnError",
    "spawn_show_child",
    "spawn_show_child_unmanaged",
    "terminate_show_child",
]
