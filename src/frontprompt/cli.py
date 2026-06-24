"""frontprompt CLI — Click-Dispatcher.

Entry-point: ``frontprompt`` (via [project.scripts] in pyproject.toml).

Subcommands:
    frontprompt daemon    — Startet den Daemon mit MCP stdio-Server.
    frontprompt show <url> — Öffnet headful Chromium mit Overlay.
    frontprompt bootstrap — Installiert Laufzeit-Prereqs (Chromium) für ein installiertes Tool.
    frontprompt --help    — Zeigt alle Subcommands.

Signal-Handling (SIGINT/SIGTERM):
    ``anyio.open_signal_receiver`` in ``_daemon_async_main`` empfängt Signale.
    Bei Signal: TaskGroup-CancelScope canceln → sauberer Exit 0.
    Buffered IntentRequests in der Queue werden silently dropped (Skeleton-Policy:
    Drain-Logik kommt mit erstem echten Aggregate-Mutations-Bundle).

Design notes:
    - ``anyio.run()`` statt ``asyncio.run()`` am Entry-Point.
    - DaemonClock wird in ``_daemon_async_main`` mit ``SystemDaemonClock``
      instanziiert und an ``Daemon`` übergeben.
"""

from __future__ import annotations

import signal as _signal
from typing import TYPE_CHECKING

import anyio
import click
import structlog

if TYPE_CHECKING:
    from pathlib import Path

    from frontprompt.ipc import SessionMetadata


async def _wait_for_socket_listening(socket_path: Path, attempts: int = 100, delay: float = 0.02) -> None:
    """Poll until ``socket_path`` exists as a real unix-socket (``S_ISSOCK``).

    Required because :func:`run_socket_server` runs as a fire-and-forget
    task — by the time we want to print the ready-line for the MCP-daemon
    handshake, the listener may not yet have called ``bind()``. Polling
    keeps the show-process from racing with its own socket-server.
    """
    import stat as _stat

    for _ in range(attempts):
        try:
            mode = socket_path.stat().st_mode
            if _stat.S_ISSOCK(mode):
                return
        except OSError:
            pass
        await anyio.sleep(delay)
    # Best-effort — if we time out we still print ready-line so the MCP-daemon
    # gets a signal; first IPC connect will simply retry.


_LOG: structlog.stdlib.BoundLogger = structlog.get_logger("frontprompt.cli")


@click.group()
def main() -> None:
    """frontprompt — MCP-Server für Browser-Automation."""
    from frontprompt.logging import configure_logging

    # Role "cli" + pid-fallback. Long-lived roles (daemon, show) re-configure
    # with their own role/session below; short-lived query subcommands keep this.
    configure_logging(role="cli", session_id=None)
    _LOG.info("daemon.cli.startup")


@main.command("daemon")
def run_daemon_command() -> None:
    """Startet den frontprompt MCP-Daemon (per-daemon browser-session isolation).

    Spawnt eine eigene private Browser-Session als Child-Prozess (``python -m
    frontprompt show <url>``) und exponiert 5 read-only MCP-Tools über stdio
    JSON-RPC. Default-Start-URL: ``about:blank`` (override via env
    ``FRONTPROMPT_MCP_START_URL``).

    Lifecycle: daemon-exit (stdin EOF, SIGINT, SIGTERM) ⇒ SIGTERM an die
    Child-Process-Group ⇒ Browser tear down. Keine Cross-Daemon-Sichtbarkeit:
    jeder ``frontprompt daemon``-Aufruf besitzt seine eigene Session.
    """
    import os as _os

    start_url = _os.environ.get("FRONTPROMPT_MCP_START_URL", "about:blank")
    anyio.run(_mcp_daemon_async_main, start_url)


@main.command("show")
@click.argument("url")
def show_command(url: str) -> None:
    """Öffnet headful Chromium auf URL, bleibt offen bis Tab-Close oder Ctrl+C.

    Pro show-instance wird ein eindeutiges session-dir unter
    ``~/.cache/frontprompt/sessions/<ts>-<rand>/`` angelegt — multi-instance-fähig.
    Eine read-only IPC-API wird via unix-socket exposed; siehe ``frontprompt sessions``,
    ``frontprompt picks``, ``frontprompt state``.
    """
    anyio.run(_show_async_main, url)


# ----------------------------------------------------------------------------
# Read-only IPC subcommands — query running `frontprompt show` instances
# ----------------------------------------------------------------------------


def _emit_json(data: object) -> None:
    """Pretty-print JSON to stdout (UTF-8, indent=2)."""
    import json as _json

    click.echo(_json.dumps(data, indent=2, ensure_ascii=False))


def _resolve_session(session_id: str | None) -> SessionMetadata:
    """Resolve `--session` flag → SessionMetadata, OR latest, OR error-exit."""
    from frontprompt.ipc import discover_sessions, pick_latest_session

    if session_id is not None:
        for sess in discover_sessions():
            if sess.session_id == session_id:
                return sess
        click.echo(
            f"ERR: session {session_id!r} nicht gefunden (oder PID nicht mehr alive). "
            f"`frontprompt sessions` zeigt die laufenden.",
            err=True,
        )
        raise SystemExit(2)

    latest = pick_latest_session()
    if latest is None:
        click.echo(
            "ERR: keine laufende `frontprompt show` instance gefunden. Starte eine via `frontprompt show <url>`.",
            err=True,
        )
        raise SystemExit(2)
    return latest


@main.group("sessions")
def sessions_group() -> None:
    """Discover + manage running `frontprompt show` instances."""


@sessions_group.command("list")
def sessions_list_command() -> None:
    """Liste alle alive sessions (newest first)."""
    from frontprompt.ipc import discover_sessions

    sessions = discover_sessions()
    _emit_json([s.model_dump(mode="json") for s in sessions])


@sessions_group.command("prune")
def sessions_prune_command() -> None:
    """Entferne dead session-dirs (PID gone). Returns list of pruned ids."""
    from frontprompt.ipc import prune_dead_sessions

    pruned = prune_dead_sessions()
    _emit_json({"pruned": pruned})


@main.command("state")
@click.option("--session", "session_id", default=None, help="Spezifische session-id; sonst latest.")
def state_command(session_id: str | None) -> None:
    """Drucke vollen StateSnapshot der ausgewählten session (oder latest)."""
    from pathlib import Path as _Path

    from frontprompt.ipc import GetSnapshotRequest, IpcConnectError, query

    target = _resolve_session(session_id)

    async def _run() -> None:
        try:
            response = await query(_Path(target.socket_path), GetSnapshotRequest())
        except IpcConnectError as exc:
            click.echo(f"ERR: {exc}", err=True)
            raise SystemExit(3) from exc
        if not response.ok:
            click.echo(f"ERR: {response.error}", err=True)
            raise SystemExit(3)
        _emit_json(response.data)

    anyio.run(_run)


@main.group("picks")
def picks_group() -> None:
    """Inspect Pick-flow state of a running `frontprompt show`."""


@picks_group.command("list")
@click.option("--session", "session_id", default=None, help="Spezifische session-id; sonst latest.")
def picks_list_command(session_id: str | None) -> None:
    """Liste alle Picks der ausgewählten session als JSON-array."""
    from pathlib import Path as _Path

    from frontprompt.ipc import GetPicksRequest, IpcConnectError, query

    target = _resolve_session(session_id)

    async def _run() -> None:
        try:
            response = await query(_Path(target.socket_path), GetPicksRequest())
        except IpcConnectError as exc:
            click.echo(f"ERR: {exc}", err=True)
            raise SystemExit(3) from exc
        if not response.ok:
            click.echo(f"ERR: {response.error}", err=True)
            raise SystemExit(3)
        _emit_json(response.data)

    anyio.run(_run)


@picks_group.command("get")
@click.argument("pick_id")
@click.option("--session", "session_id", default=None, help="Spezifische session-id; sonst latest.")
def picks_get_command(pick_id: str, session_id: str | None) -> None:
    """Drucke einzelnen Pick by ID."""
    from pathlib import Path as _Path

    from frontprompt.ipc import GetPickRequest, IpcConnectError, query

    target = _resolve_session(session_id)

    async def _run() -> None:
        try:
            response = await query(_Path(target.socket_path), GetPickRequest(pick_id=pick_id))
        except IpcConnectError as exc:
            click.echo(f"ERR: {exc}", err=True)
            raise SystemExit(3) from exc
        if not response.ok:
            click.echo(f"ERR: {response.error}", err=True)
            raise SystemExit(4)  # 4 = pick_not_found vs 3 = connection
        _emit_json(response.data)

    anyio.run(_run)


@main.command("ping")
@click.option("--session", "session_id", default=None, help="Spezifische session-id; sonst latest.")
def ping_command(session_id: str | None) -> None:
    """Liveness-check der ausgewählten session."""
    from pathlib import Path as _Path

    from frontprompt.ipc import IpcConnectError, PingRequest, query

    target = _resolve_session(session_id)

    async def _run() -> None:
        try:
            response = await query(_Path(target.socket_path), PingRequest())
        except IpcConnectError as exc:
            click.echo(f"ERR: {exc}", err=True)
            raise SystemExit(3) from exc
        if not response.ok:
            click.echo(f"ERR: {response.error}", err=True)
            raise SystemExit(3)
        _emit_json({"session_id": target.session_id, "data": response.data})

    anyio.run(_run)


def _resolve_run_mcp_path() -> str | None:
    """Return the absolute path to ``run-mcp.sh`` or ``None`` if unresolvable.

    Resolution order (mirrors ``run-mcp.sh`` own ``$DIR`` logic):

    1. ``~/.frontprompt/install.path`` sentinel written by ``setup.sh``.
    2. Derive from this package's location (``__file__``).
    """
    from pathlib import Path as _Path

    # 1. Sentinel
    sentinel = _Path.home() / ".frontprompt" / "install.path"
    if sentinel.exists():
        try:
            repo_root = _Path(sentinel.read_text().strip())
            candidate = repo_root / "run-mcp.sh"
            if candidate.exists():
                return str(candidate)
        except OSError:
            pass

    # 2. Derive from package location
    #    src/frontprompt/cli.py → repo root is 3 parents up (src/frontprompt → src → repo)
    try:
        pkg_file = _Path(__file__).resolve()
        repo_root = pkg_file.parents[2]
        candidate = repo_root / "run-mcp.sh"
        if candidate.exists():
            return str(candidate)
    except (IndexError, OSError):
        pass

    return None


def _print_mcp_snippet(run_mcp_path: str | None, *, write_mcp_json: bool = False) -> None:
    """Print (and optionally write) the Claude-Code MCP registration snippet.

    Parameters
    ----------
    run_mcp_path:
        Absolute path to ``run-mcp.sh``, or ``None`` if unresolvable.
    write_mcp_json:
        When ``True``, merge-write the entry into ``~/.mcp.json``.
    """
    import json as _json
    from pathlib import Path as _Path

    click.echo("  [..] MCP setup ......... generating snippet...")

    if run_mcp_path is None:
        cmd_value = "<path-to-run-mcp.sh>"
        click.echo("  [!!] MCP setup ......... sentinel not found — run frontprompt setup to write the sentinel")
    else:
        cmd_value = run_mcp_path

    snippet: dict[str, object] = {
        "mcpServers": {
            "frontprompt": {
                "command": cmd_value,
                "args": [],
            }
        }
    }
    snippet_text = _json.dumps(snippet, indent=2)

    click.echo("")
    click.echo("  Add to ~/.mcp.json (or project .mcp.json):")
    click.echo("")
    for line in snippet_text.splitlines():
        click.echo(f"  {line}")
    click.echo("")
    click.echo("  Or register via CLI:")
    click.echo("")
    click.echo(f"    claude mcp add frontprompt {cmd_value}")
    click.echo("")

    if write_mcp_json and run_mcp_path is not None:
        mcp_json_path = _Path.home() / ".mcp.json"
        existing: dict[str, object] = {}
        if mcp_json_path.exists():
            try:
                existing = _json.loads(mcp_json_path.read_text())
            except (_json.JSONDecodeError, OSError):
                existing = {}

        mcp_servers = existing.get("mcpServers", {})
        assert isinstance(mcp_servers, dict)
        current_entry = mcp_servers.get("frontprompt", {})
        assert isinstance(current_entry, dict)

        if current_entry.get("command") == run_mcp_path and current_entry.get("args") == []:
            click.echo("  [ok] MCP setup ......... ~/.mcp.json already up-to-date")
            return

        mcp_servers["frontprompt"] = {"command": run_mcp_path, "args": []}
        existing["mcpServers"] = mcp_servers
        mcp_json_path.write_text(_json.dumps(existing, indent=2))
        click.echo("  [ok] MCP setup ......... wrote ~/.mcp.json")
        return

    click.echo("  [ok] MCP setup ......... snippet ready")


@main.command("bootstrap")
@click.option(
    "--chromium/--no-chromium",
    default=True,
    help="Install the Playwright Chromium driver (default: yes).",
)
@click.option(
    "--write-mcp-json",
    is_flag=True,
    default=False,
    help="Merge-write the MCP registration entry into ~/.mcp.json.",
)
def bootstrap_command(chromium: bool, write_mcp_json: bool) -> None:
    """Install runtime prerequisites for an installed frontprompt.

    The overlay frontend ships *inside* the package (embedded at build time), so
    a ``uv tool install`` of the wheel already carries it. What a wheel cannot
    bundle is the Chromium browser binary — this command installs it via
    Playwright. Run once after installing the tool::

        uv tool install ./dist/frontprompt-*.whl
        frontprompt bootstrap

    Verifies the embedded overlay bundle is present, then (unless
    ``--no-chromium``) runs ``python -m playwright install chromium``.
    Prints the Claude-Code MCP registration snippet so the daemon can be
    wired without manual diagnosis.
    """
    import subprocess as _subprocess
    import sys as _sys

    from frontprompt.overlay.loader import load_build_manifest

    click.echo("frontprompt bootstrap")

    # 1. Verify the embedded overlay bundle (frontend) is present.
    try:
        manifest = load_build_manifest()
        click.echo(
            f"  [ok] overlay bundle .. embedded (schema {manifest.schema_version}, {manifest.bundle_size_bytes} bytes)"
        )
    except FileNotFoundError as exc:
        click.echo(f"  [!!] overlay bundle .. MISSING\n{exc}", err=True)
        raise SystemExit(1) from exc

    # 2. Install the Chromium driver (cannot be shipped in a wheel).
    if chromium:
        click.echo("  [..] chromium ....... installing via playwright...")
        result = _subprocess.run(
            [_sys.executable, "-m", "playwright", "install", "chromium"],
            check=False,
        )
        if result.returncode != 0:
            click.echo("  [!!] chromium ....... playwright install failed", err=True)
            raise SystemExit(result.returncode)
        click.echo("  [ok] chromium ....... installed")
    else:
        click.echo("  [--] chromium ....... skipped (--no-chromium)")

    # 3. Print MCP registration snippet.
    run_mcp_path = _resolve_run_mcp_path()
    _print_mcp_snippet(run_mcp_path, write_mcp_json=write_mcp_json)

    click.echo("bootstrap complete — `frontprompt show <url>` is ready.")


async def _show_async_main(url: str) -> None:
    """Delegates to ShowSession — thin entry-point for `frontprompt show`.

    The full browser lifecycle (bridge, overlay, state, heartbeat, IPC) is
    orchestrated by :class:`frontprompt.show_session.ShowSession`. This function
    exists to maintain the ``anyio.run(_show_async_main, url)`` call-site in
    :func:`show_command` (backward compat for tests that import by name).
    """
    from frontprompt.show_session import ShowSession

    async with ShowSession(url=url) as s:
        await s.run()


async def _mcp_daemon_async_main(start_url: str) -> None:
    """Async-Root des MCP-Daemons (per-daemon browser-session isolation).

    Topologie::

        LazyBrowserSessionProvider(start_url)
          └── anyio.create_task_group()
                ├── _signal_watcher()         (SIGINT/SIGTERM → cancel scope)
                └── serve_mcp_stdio(provider) (stdio JSON-RPC; spawns browser-child
                                               lazily on first tool-call)

    Browser-spawn is **deferred until the first MCP-tool-call**: the daemon
    starts instantly, no chromium window appears at Claude-Code session-boot.
    A user actually invoking a frontprompt tool triggers the spawn.

    Spawn failures (timeout, missing session.json, early child exit) surface as
    MCP-tool errors with stderr-tail diagnostics, not daemon-exit — that way
    Claude Code stays connected and the user sees the cause.

    On stdio-EOF (Claude Code disconnects) or SIGINT/SIGTERM, ``serve_mcp_stdio``
    invokes ``provider.close()`` in its ``finally`` block, which SIGTERMs the
    spawned chromium's process-group.
    """
    from frontprompt.logging import configure_logging
    from frontprompt.mcp_server import LazyBrowserSessionProvider, serve_mcp_stdio

    # MCP-daemon has no session-id at boot (the show-child is spawned lazily on
    # the first tool-call), so log to the pid-fallback ``logs/<pid>-daemon.log``.
    log_path = configure_logging(role="daemon", session_id=None)
    _LOG.info("mcp_daemon.startup", start_url=start_url, log_file=str(log_path))

    provider = LazyBrowserSessionProvider(start_url)

    async with anyio.create_task_group() as tg:

        async def _signal_watcher() -> None:
            with anyio.open_signal_receiver(_signal.Signals.SIGINT, _signal.Signals.SIGTERM) as signals:
                async for sig in signals:
                    _LOG.info("mcp_daemon.shutdown.signal", signal=sig.name)
                    tg.cancel_scope.cancel()
                    return

        tg.start_soon(_signal_watcher)
        tg.start_soon(serve_mcp_stdio, provider)


async def _daemon_async_main() -> None:
    """Async-Root des historischen Two-BC + HTTP/WS-Daemons (NICHT vom daemon-Command aufgerufen).

    Dormant code — die Two-BC-Nursery + HTTP-Mutation-Endpoint + WS-Push
    bleiben im Repo erhalten als Phase-2-Reaktivierungs-Pfad, werden vom aktuellen
    ``frontprompt daemon``-Command aber nicht mehr referenziert.
    """
    from frontprompt.clock import SystemDaemonClock
    from frontprompt.daemon import Daemon, run_daemon

    clock = SystemDaemonClock()
    daemon = Daemon(clock=clock)

    async with anyio.create_task_group() as tg:
        tg.start_soon(run_daemon, daemon)

        async def _signal_watcher() -> None:
            with anyio.open_signal_receiver(_signal.Signals.SIGINT, _signal.Signals.SIGTERM) as signals:
                async for sig in signals:
                    _LOG.info(
                        "daemon.shutdown.signal",
                        signal=sig.name,
                    )
                    tg.cancel_scope.cancel()
                    return

        tg.start_soon(_signal_watcher)
