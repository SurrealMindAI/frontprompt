"""frontprompt CLI — Click-Dispatcher.

Entry-point: ``frontprompt`` (via [project.scripts] in pyproject.toml).

Subcommands:
    frontprompt mcp             — Startet den MCP-stdio-Server (per-Prozess Browser-Isolation).
    frontprompt show <url>      — Öffnet headful Chromium mit Overlay (exposed unix-socket).
    frontprompt bootstrap       — Installiert Laufzeit-Prereqs (Chromium) für ein installiertes Tool.
    frontprompt sessions list   — Listet laufende show-Sessions (+ prune).
    frontprompt ping|state      — Liveness / vollen StateSnapshot einer Session lesen.
    frontprompt picks list|get  — Pick-flow-state lesen.
    frontprompt navigate <url>  — Session zu URL navigieren.
    frontprompt eval <js>       — JavaScript in der Session ausführen (Debug).
    frontprompt page-info       — Page-Metadaten der Session.
    frontprompt screenshot      — PNG-Screenshot der Session.
    frontprompt pick selector|text — Picks per CSS / sichtbarem Text erstellen.
    frontprompt --help          — Zeigt alle Subcommands.

    Die session/debug-Subcommands sprechen den IPC-unix-socket einer laufenden
    ``frontprompt show``-Instanz an (``--session`` wählt eine, sonst die neueste).

Signal-Handling (SIGINT/SIGTERM): der MCP-Server fängt die Signale ab, cancelt
seinen TaskGroup-CancelScope und exitet sauber (Exit 0).
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


def _run_mcp() -> None:
    import os as _os

    start_url = _os.environ.get("FRONTPROMPT_MCP_START_URL", "about:blank")
    anyio.run(_mcp_daemon_async_main, start_url)


@main.command("mcp")
def run_mcp_command() -> None:
    """Startet den frontprompt MCP-stdio-Server (per-Prozess Browser-Session-Isolation).

    Spawnt eine eigene private Browser-Session als Child-Prozess (``python -m
    frontprompt show <url>``) und exponiert die frontprompt-MCP-Tools über stdio
    JSON-RPC. Default-Start-URL: ``about:blank`` (override via env
    ``FRONTPROMPT_MCP_START_URL``).

    Lifecycle: stdin-EOF / SIGINT / SIGTERM ⇒ SIGTERM an die Child-Process-Group
    ⇒ Browser tear-down. Keine Cross-Prozess-Sichtbarkeit: jeder ``frontprompt
    mcp``-Aufruf besitzt seine eigene Session.
    """
    _run_mcp()


@main.command("daemon", hidden=True)
def run_daemon_alias() -> None:
    """Deprecated-Alias für ``mcp`` — aus Backward-Compat-Gründen erhalten."""
    _run_mcp()


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


def _query_session(session_id: str | None, request: object) -> object:
    """Resolve the target session, send ``request`` over its IPC socket, return ``response.data``.

    Shared plumbing for every socket-backed subcommand (DRY): resolves the session
    (explicit ``--session`` else latest via :func:`_resolve_session`), opens the unix
    socket and validates the response. A connection failure or an ``ok=False`` response
    prints the error to stderr and exits 3. The throwaway ``query``-boilerplate that was
    copy-pasted across every socket subcommand now lives here once.
    """
    from pathlib import Path as _Path

    from frontprompt.ipc import IpcConnectError, query

    target = _resolve_session(session_id)

    async def _run() -> object:
        try:
            response = await query(_Path(target.socket_path), request)  # type: ignore[arg-type]
        except IpcConnectError as exc:
            click.echo(f"ERR: {exc}", err=True)
            raise SystemExit(3) from exc
        if not response.ok:
            click.echo(f"ERR: {response.error}", err=True)
            raise SystemExit(3)
        return response.data

    return anyio.run(_run)


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
    from frontprompt.ipc import GetSnapshotRequest

    _emit_json(_query_session(session_id, GetSnapshotRequest()))


@main.group("picks")
def picks_group() -> None:
    """Inspect Pick-flow state of a running `frontprompt show`."""


@picks_group.command("list")
@click.option("--session", "session_id", default=None, help="Spezifische session-id; sonst latest.")
def picks_list_command(session_id: str | None) -> None:
    """Liste alle Picks der ausgewählten session als JSON-array."""
    from frontprompt.ipc import GetPicksRequest

    _emit_json(_query_session(session_id, GetPicksRequest()))


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


# ----------------------------------------------------------------------------
# Debug / write subcommands — drive a running `frontprompt show` session over the
# same IPC socket the MCP daemon uses. First-class replacement for ad-hoc socket
# scripts: navigate / eval / page-info / screenshot / pick mirror the MCP tools.
# ----------------------------------------------------------------------------


@main.command("navigate")
@click.argument("url")
@click.option("--session", "session_id", default=None, help="Spezifische session-id; sonst latest.")
def navigate_command(url: str, session_id: str | None) -> None:
    """Navigiere die ausgewählte session zu URL (latest wenn --session fehlt)."""
    from frontprompt.ipc import NavigateRequest

    _emit_json(_query_session(session_id, NavigateRequest(url=url)))


@main.command("eval")
@click.argument("expression")
@click.option("--session", "session_id", default=None, help="Spezifische session-id; sonst latest.")
@click.option("--pick", "pick_id", default=None, help="Bind live ElementHandle als `el` im JS-Kontext.")
@click.option("--mutating", is_flag=True, default=False, help="Invalidate snapshot nach Ausführung.")
def eval_command(expression: str, session_id: str | None, pick_id: str | None, mutating: bool) -> None:
    """Führe beliebiges JavaScript in der ausgewählten session aus (Debug-Tool)."""
    from frontprompt.ipc import EvalJsRequest

    _emit_json(
        _query_session(
            session_id,
            EvalJsRequest(expression=expression, pick_id_arg=pick_id, mutating=mutating),
        )
    )


@main.command("page-info")
@click.option("--session", "session_id", default=None, help="Spezifische session-id; sonst latest.")
def page_info_command(session_id: str | None) -> None:
    """Page-Metadaten (url, title, viewport, scroll, ready_state) der session."""
    from frontprompt.ipc import GetPageInfoRequest

    _emit_json(_query_session(session_id, GetPageInfoRequest()))


@main.command("screenshot")
@click.argument("path", required=False, type=click.Path(dir_okay=False))
@click.option("--session", "session_id", default=None, help="Spezifische session-id; sonst latest.")
@click.option("--full-page", is_flag=True, default=False, help="Ganze scrollbare Seite statt nur Viewport.")
def screenshot_command(path: str | None, session_id: str | None, full_page: bool) -> None:
    """PNG-Screenshot der session über den IPC-socket.

    Der show-Server schreibt das PNG und liefert seinen Pfad zurück. Ohne PATH wird
    die Server-Antwort als JSON ausgegeben; mit PATH wird das PNG dorthin kopiert.
    """
    import shutil as _shutil
    from pathlib import Path as _Path

    from frontprompt.ipc import ScreenshotPageRequest

    data = _query_session(session_id, ScreenshotPageRequest(full_page=full_page))
    if path and isinstance(data, dict) and data.get("path"):
        _shutil.copyfile(data["path"], path)
        _emit_json({**data, "path": str(_Path(path).resolve())})
    else:
        _emit_json(data)


@main.group("pick")
def pick_group() -> None:
    """Create picks in a running `frontprompt show` (selector / text)."""


@pick_group.command("selector")
@click.argument("selector")
@click.option("--comment", required=True, help="Base-Kommentar (auto-suffix '[match i/N]').")
@click.option("--limit", default=10, show_default=True, help="Max picks (1-50).")
@click.option("--parent", "parent_pick_id", default=None, help="Scope-query in einem parent-pick.")
@click.option("--session", "session_id", default=None, help="Spezifische session-id; sonst latest.")
def pick_selector_command(
    selector: str, comment: str, limit: int, parent_pick_id: str | None, session_id: str | None
) -> None:
    """Pick N Elemente per CSS-Selektor (mit Pflicht-Kommentar)."""
    from frontprompt.ipc import PickBySelectorRequest

    _emit_json(
        _query_session(
            session_id,
            PickBySelectorRequest(selector=selector, comment=comment, limit=limit, parent_pick_id=parent_pick_id),
        )
    )


@pick_group.command("text")
@click.argument("text")
@click.option("--comment", required=True, help="Base-Kommentar.")
@click.option("--role", default=None, help="Optionaler ARIA-role-Filter.")
@click.option("--limit", default=10, show_default=True, help="Max picks (1-50).")
@click.option("--parent", "parent_pick_id", default=None, help="Scope-query in einem parent-pick.")
@click.option("--session", "session_id", default=None, help="Spezifische session-id; sonst latest.")
def pick_text_command(
    text: str,
    comment: str,
    role: str | None,
    limit: int,
    parent_pick_id: str | None,
    session_id: str | None,
) -> None:
    """Pick N Elemente per sichtbarem Text (optional role-gefiltert)."""
    from frontprompt.ipc import PickByTextRequest

    _emit_json(
        _query_session(
            session_id,
            PickByTextRequest(text=text, comment=comment, role=role, limit=limit, parent_pick_id=parent_pick_id),
        )
    )


@main.command("bootstrap")
@click.option(
    "--chromium/--no-chromium",
    default=True,
    help="Install the Playwright Chromium driver (default: yes).",
)
def bootstrap_command(chromium: bool) -> None:
    """Pre-install runtime prerequisites for an installed frontprompt.

    The overlay frontend ships *inside* the package (embedded at build time), so
    a ``uv tool install`` of the wheel already carries it. What a wheel cannot
    bundle is the Chromium browser binary — this command installs it via
    Playwright.

    This is **optional**: ``frontprompt show`` / ``frontprompt mcp`` self-install
    Chromium on first launch if it is missing. Run ``bootstrap`` only to
    pre-install it eagerly (e.g. in CI or offline prep)::

        uv tool install ./dist/frontprompt-*.whl
        frontprompt bootstrap
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

    # MCP server has no session-id at boot (the show-child is spawned lazily on
    # the first tool-call), so log to the pid-fallback ``logs/<pid>-mcp.log``.
    log_path = configure_logging(role="mcp", session_id=None)
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
