"""ShowSession — browser lifecycle orchestrator for `frontprompt show`.

Extracted from the inline closure factory in cli.py._show_async_main.
Owns:
  - All 17 bridge handler methods (_on_<message_type>)
  - _send_snapshot helper
  - _heartbeat_sender coroutine
  - The run() lifecycle (browser → bridge → overlay → socket server)

Bridge design: expose_function registered via BridgeManager.__aenter__ before navigate.
State classification: state_manager is the authoritative backend; overlay is a read-mirror.
Single-writer: all mutations via StateManager (single-writer, anyio.Lock).

Window-namespace discipline (see ARCHITECTURE.md):
    expose_function("__fp_internal_state_getter", ...) is used here as a Playwright-
    scaffold-global. Migrated by overlay's setupBridge() to window.__fp.getState and
    deleted from the window-namespace immediately. End-state: only window.__fp exists.
    See frontend/src/bridge/bridge.svelte.ts:setupBridge for the migration+delete.
    Allowlisted in tests/arch/test_window_fp_namespace.py ALLOW_LIST["show_session.py"]
    (extraction from cli.py).
"""

from __future__ import annotations

import secrets
import signal as _signal
import time
from pathlib import Path
from typing import TYPE_CHECKING

import anyio
import click
import structlog

from frontprompt.bridge import BridgeManager
from frontprompt.bridge.messages import (
    Heartbeat,
    HideAllPanelsRequested,
    InspectorActivateRequested,
    InspectorCanceledRequested,
    InspectorPickMadeRequested,
    OverlayReady,
    PanelResizeRequested,
    PanelToggleRequested,
    PickCommentUpdatedRequested,
    PickDeletedRequested,
    PickSelectedRequested,
    RecordedEventCapturedRequested,
    RecordingRenameRequested,
    RecordingSelectedRequested,
    RecordingStartRequested,
    RecordingStopRequested,
    RegionCreatedRequested,
    RegionDeletedRequested,
    RegionSelectedRequested,
    RegionUpdatedRequested,
    RelationCreatedRequested,
    RelationDeletedRequested,
    RelationUpdatedRequested,
    StateSnapshotMessage,
)
from frontprompt.browser import BrowserSessionManager
from frontprompt.ipc import run_socket_server, session_lifecycle
from frontprompt.ipc.playwright_controller import ElementResolver, PlaywrightPageController
from frontprompt.ipc.session import format_ready_line
from frontprompt.overlay import (
    OverlayInjector,
    OverlayNotMountedError,
    load_build_manifest,
    load_overlay_bundle,
)
from frontprompt.state import StateManager, StateSnapshot
from frontprompt.state.state import NavigationEntry
from frontprompt.state.persistence import make_persistence

if TYPE_CHECKING:
    import anyio.abc

    from frontprompt.ipc.session import SessionMetadata

_LOG = structlog.get_logger("frontprompt.show_session")


class ShowSession:
    """Orchestrates headful Chromium session with overlay + bridge + state.

    Async context manager + run() entry point. Extracts the full browser lifecycle
    that was previously inline in cli.py._show_async_main.

    Usage::

        async with ShowSession(url=url) as s:
            await s.run()

    Or equivalently via ShowSession.run() which sets up the context internally.

    The class stores self._tg (anyio TaskGroup) once entered, giving handler
    methods natural access for tg.start_soon routing.
    """

    def __init__(
        self,
        url: str,
        *,
        state_manager: StateManager | None = None,
    ) -> None:
        self.url = url
        # SSoT: session identity is produced exactly once, by session_lifecycle /
        # SessionMetadata.session_id (ipc/session.py). ShowSession is a pure consumer.
        # When no manager is injected we DEFER construction to run(), where we enter
        # session_lifecycle and obtain the authoritative session_id — no fabricated
        # id here. Tests may still inject a pre-built manager.
        self.state_manager: StateManager | None = state_manager
        self._tg: anyio.abc.TaskGroup | None = None
        self._log = _LOG.bind(url=url)
        # Count how many handlers will be registered (for test_show_session_registers_handlers_count)
        self._registered_handler_count = 0
        # Nav observation: last known URL, tracked in OverlayReady handler (sub-plan 04).
        self._last_url: str | None = None

    def handler_count(self) -> int:
        """Return the number of bridge handler types this session registers."""
        # 22 handler types:
        # OverlayReady, PanelToggleRequested, PanelResizeRequested, HideAllPanelsRequested,
        # InspectorActivateRequested, InspectorCanceledRequested, InspectorPickMadeRequested,
        # PickSelectedRequested, PickCommentUpdatedRequested, PickDeletedRequested,
        # RelationCreatedRequested, RelationDeletedRequested, RelationUpdatedRequested,
        # RegionCreatedRequested, RegionDeletedRequested, RegionUpdatedRequested, RegionSelectedRequested
        # + 5 recording handlers (sub-plan 04):
        # RecordingStartRequested, RecordingStopRequested, RecordingRenameRequested,
        # RecordingSelectedRequested, RecordedEventCapturedRequested
        return 22

    @property
    def _sm(self) -> StateManager:
        """The active StateManager — built in run() from the lifecycle SSoT.

        Handlers only fire after run() has entered session_lifecycle and assigned
        self.state_manager, so this is always non-None on the handler path.
        """
        if self.state_manager is None:  # pragma: no cover - defensive, handlers run post-build
            raise RuntimeError("state_manager not yet built — run() must enter session_lifecycle first")
        return self.state_manager

    def _build_state_manager(self, session: SessionMetadata) -> StateManager:
        """Construct the authoritative StateManager from the lifecycle SSoT.

        ``session.session_id`` is the single source of truth for session identity
        (produced by ``session_lifecycle`` in ``ipc/session.py``); this method only
        consumes it. Persistence is the disk-backed default via ``make_persistence()``.
        """
        return StateManager(session_id=session.session_id, persistence=make_persistence())

    async def __aenter__(self) -> ShowSession:
        return self

    async def __aexit__(self, *_args: object) -> None:
        pass

    def _register_handlers(self, bridge: BridgeManager) -> None:
        """Register all 17 bridge handler methods on the bridge instance."""
        bridge.on(OverlayReady, self._on_overlay_ready)
        bridge.on(PanelToggleRequested, self._on_panel_toggle)
        bridge.on(PanelResizeRequested, self._on_panel_resize)
        bridge.on(HideAllPanelsRequested, self._on_hide_all)
        bridge.on(InspectorActivateRequested, self._on_inspector_activate)
        bridge.on(InspectorCanceledRequested, self._on_inspector_canceled)
        bridge.on(InspectorPickMadeRequested, self._on_inspector_pick_made)
        bridge.on(PickSelectedRequested, self._on_pick_selected)
        bridge.on(PickCommentUpdatedRequested, self._on_pick_comment_updated)
        bridge.on(PickDeletedRequested, self._on_pick_deleted)
        bridge.on(RelationCreatedRequested, self._on_relation_created)
        bridge.on(RelationDeletedRequested, self._on_relation_deleted)
        bridge.on(RelationUpdatedRequested, self._on_relation_updated)
        bridge.on(RegionCreatedRequested, self._on_region_created)
        bridge.on(RegionDeletedRequested, self._on_region_deleted)
        bridge.on(RegionUpdatedRequested, self._on_region_updated)
        bridge.on(RegionSelectedRequested, self._on_region_selected)

    # ----- Bridge handler methods (re-homed from cli.py closures) -----

    async def _send_snapshot(
        self,
        bridge: BridgeManager,
        snapshot: StateSnapshot | None = None,
        integrity_token: str | None = None,
    ) -> None:
        """Send authoritative state snapshot to overlay.

        Phase-1: snapshot size bounded by Pick.comment/Region.note max_length.
        Phase-2: replace full-snapshot broadcast with delta/patch protocol via a WebSocket+JSON-RPC client library.
        """
        snap = snapshot if snapshot is not None else self._sm.snapshot()
        try:
            await bridge.send(StateSnapshotMessage(snapshot=snap, integrity_token=integrity_token))
        except Exception as exc:
            self._log.warning("show.state.broadcast_failed", error=str(exc))

    async def _on_overlay_ready(self, _msg: OverlayReady, *, _bridge: BridgeManager | None = None) -> None:
        # Note: _bridge is injected by the run() setup via closure
        self._log.info("show.state.rehydrate_on_overlay_ready")

    async def _on_panel_toggle(self, msg: PanelToggleRequested) -> None:
        await self._sm.toggle_panel(msg.panel_id)

    async def _on_panel_resize(self, msg: PanelResizeRequested) -> None:
        await self._sm.resize_panel(msg.panel_id, msg.new_size)

    async def _on_hide_all(self, msg: HideAllPanelsRequested) -> None:
        await self._sm.set_all_panels_open(msg.target_open)

    async def _on_inspector_activate(self, _msg: InspectorActivateRequested) -> None:
        await self._sm.set_inspector_active(True)

    async def _on_inspector_canceled(self, _msg: InspectorCanceledRequested) -> None:
        await self._sm.set_inspector_active(False)

    async def _on_inspector_pick_made(self, msg: InspectorPickMadeRequested) -> None:
        await self._sm.add_pick(msg.pick)

    async def _on_pick_selected(self, msg: PickSelectedRequested) -> None:
        await self._sm.select_pick(msg.pick_id)

    async def _on_pick_comment_updated(self, msg: PickCommentUpdatedRequested) -> None:
        await self._sm.update_pick_comment(msg.pick_id, msg.comment)

    async def _on_pick_deleted(self, msg: PickDeletedRequested) -> None:
        await self._sm.delete_pick(msg.pick_id)

    async def _on_relation_created(self, msg: RelationCreatedRequested) -> None:
        await self._sm.add_relation(msg.relation)

    async def _on_relation_deleted(self, msg: RelationDeletedRequested) -> None:
        await self._sm.delete_relation(msg.relation_id)

    async def _on_relation_updated(self, msg: RelationUpdatedRequested) -> None:
        await self._sm.update_relation(msg.relation_id, msg.relation_kind, msg.note)

    async def _on_region_created(self, msg: RegionCreatedRequested) -> None:
        await self._sm.add_region(msg.region)

    async def _on_region_deleted(self, msg: RegionDeletedRequested) -> None:
        await self._sm.delete_region(msg.region_id)

    async def _on_region_updated(self, msg: RegionUpdatedRequested) -> None:
        await self._sm.update_region(msg.region_id, msg.note)

    async def _on_region_selected(self, msg: RegionSelectedRequested) -> None:
        await self._sm.select_region(msg.region_id)

    # ----- Recording handlers (sub-plan 04) -----

    async def _on_recording_start(self, msg: RecordingStartRequested) -> None:
        """RecordingStartRequested → create new recording. Broadcasts snapshot via StateManager listener."""
        await self._sm.start_recording(msg.name, msg.description)

    async def _on_recording_stop(self, msg: RecordingStopRequested) -> None:
        """RecordingStopRequested → stop active recording. Broadcasts snapshot via StateManager listener."""
        await self._sm.stop_recording(msg.recording_id)

    async def _on_recording_rename(self, msg: RecordingRenameRequested) -> None:
        """RecordingRenameRequested → patch name/description. Broadcasts snapshot via StateManager listener."""
        await self._sm.rename_recording(msg.recording_id, msg.name, msg.description)

    async def _on_recording_selected(self, msg: RecordingSelectedRequested) -> None:
        """RecordingSelectedRequested → set active_detail_recording_id. Broadcasts snapshot."""
        await self._sm.select_recording(msg.recording_id)

    async def _on_recorded_event_captured(self, msg: RecordedEventCapturedRequested) -> None:
        """RecordedEventCapturedRequested → append timeline entry. NON-broadcasting path (COL-5 / PIT-105).

        seq is stamped Python-side in append_timeline_entry (reviewer Q1).
        No snapshot broadcast — ~10 Hz keydown events must not flood the wire.
        """
        await self._sm.append_timeline_entry(msg.recording_id, msg.entry)

    async def _heartbeat_sender(self, bridge: BridgeManager) -> None:
        """Periodic healthcheck — sends every 5s to overlay.

        On failure, logs warning only on the FIRST consecutive failure.
        Subsequent consecutive failures emit debug-level only (suppressed noise).
        On recovery after any failure streak, logs a debug recovery event and
        resets the failure counter.

        Backoff: after each failure the retry delay starts at 100 ms, doubles per
        attempt, and caps at 5 s. This ensures rapid detection of bridge recovery
        during page transitions (~200-500 ms) without log spam.
        """
        seq = 0
        consecutive_failures = 0
        _BACKOFF_BASE_S = 0.1
        _BACKOFF_CAP_S = 5.0
        _HEARTBEAT_INTERVAL_S = 5.0
        while True:
            await anyio.sleep(_HEARTBEAT_INTERVAL_S)
            seq += 1
            try:
                await bridge.send(Heartbeat(seq=seq, server_send_time_ns=time.monotonic_ns()))
                if consecutive_failures > 0:
                    self._log.debug("show.heartbeat.recovered", seq=seq, after_failures=consecutive_failures)
                    consecutive_failures = 0
            except Exception as exc:
                consecutive_failures += 1
                if consecutive_failures == 1:
                    self._log.warning("show.heartbeat.first_failure", seq=seq, error=str(exc))
                else:
                    self._log.debug(
                        "show.heartbeat.consecutive_failure_suppressed",
                        seq=seq,
                        consecutive=consecutive_failures,
                    )
                # Exponential backoff before next attempt: 100ms → 200ms → … → 5s cap
                backoff = min(_BACKOFF_BASE_S * (2 ** (consecutive_failures - 1)), _BACKOFF_CAP_S)
                await anyio.sleep(backoff)

    async def run(self) -> None:
        """Orchestrate full browser lifecycle. Equivalent to cli.py._show_async_main.

        Topology::

            anyio.create_task_group()
                ├── _signal_watcher()        (SIGINT/SIGTERM → cancel scope)
                └── _run_browser()
                      BrowserSessionManager (headful)
                        BridgeManager (expose_function before navigate)
                          bridge.set_task_group(self._tg)
                          StateManager (single-writer aggregate)
                          17 bridge.on(...) registrations
                          state_manager.add_snapshot_listener(broadcast)
                          OverlayInjector.install_init_script()
                          browser.navigate(url)
                          page.expose_function(__fp_internal_state_getter, ...)
                          tg.start_soon(_heartbeat_sender, bridge)
                          browser.wait_until_closed()
        """
        try:
            bundle = load_overlay_bundle()
            manifest = load_build_manifest()
        except FileNotFoundError as exc:
            click.echo(f"⚠ {exc}", err=True)
            raise SystemExit(1) from exc

        self._log.info(
            "show.start",
            url=self.url,
            bundle_length=len(bundle),
            build_session=manifest.build_session,
            schema_version=manifest.schema_version,
        )

        async with session_lifecycle(url=self.url) as session:
            # SSoT: the authoritative session_id is now in scope. Re-point the
            # log file sink to <session-dir>/show.log so the show-child's logs
            # land next to session.json + show.sock (was pid-fallback until now).
            from frontprompt.logging import configure_logging

            log_path = configure_logging(role="show", session_id=session.session_id)
            self._log.info("show.logging.configured", log_file=str(log_path))

            # SSoT: the authoritative session_id is now in scope. Build the
            # StateManager from it (consumer) unless a manager was injected (tests).
            if self.state_manager is None:
                self.state_manager = self._build_state_manager(session)
                self._log.info("show.state.manager_built", session_id=session.session_id)

            async with anyio.create_task_group() as tg:
                self._tg = tg

                async def _signal_watcher() -> None:
                    with anyio.open_signal_receiver(_signal.Signals.SIGINT, _signal.Signals.SIGTERM) as signals:
                        async for sig in signals:
                            self._log.info("show.shutdown.signal", signal=sig.name)
                            tg.cancel_scope.cancel()
                            return

                async def _run_browser() -> None:
                    # generate per-session integrity token. This 64-char hex
                    # string is never derivable from page JS — it is delivered to the
                    # overlay via the initial getState() seed (pre-mount hydration path)
                    # and validated by the TS dispatcher before accepting any
                    # state_snapshot envelope. See ARCHITECTURE.md and bridge.svelte.ts.
                    integrity_token = secrets.token_hex(32)

                    async with BrowserSessionManager(headless=False) as browser:
                        async with BridgeManager(browser, bundle_build_session=manifest.build_session) as bridge:
                            # inject task group so handlers are routed via
                            # tg.start_soon() instead of direct await in CDP callback.
                            bridge.set_task_group(tg)

                            # Re-hydration on OverlayReady (covers cross-origin nav).
                            # Also observes URL changes for NavigationEntry appending (sub-plan 04, COL-7).
                            # browser.page.url is a synchronous str property — no await needed.
                            async def _on_overlay_ready_with_bridge(_msg: OverlayReady) -> None:
                                current_url: str = browser.page.url
                                if current_url != self._last_url:
                                    active_recording_id = self._sm._recordings_state.active_recording_id
                                    if active_recording_id is not None and self._last_url is not None:
                                        await self._sm.append_timeline_entry(
                                            active_recording_id,
                                            NavigationEntry(
                                                seq=0,  # Python-stamped in append_timeline_entry
                                                timestamp_ms=0,  # Python-stamped in append_timeline_entry
                                                from_url=self._last_url,
                                                to_url=current_url,
                                            ),
                                        )
                                self._last_url = current_url
                                self._log.info("show.state.rehydrate_on_overlay_ready")
                                await self._send_snapshot(bridge, integrity_token=integrity_token)

                            bridge.on(OverlayReady, _on_overlay_ready_with_bridge)

                            # Register all 16 remaining handler methods
                            bridge.on(PanelToggleRequested, self._on_panel_toggle)
                            bridge.on(PanelResizeRequested, self._on_panel_resize)
                            bridge.on(HideAllPanelsRequested, self._on_hide_all)
                            bridge.on(InspectorActivateRequested, self._on_inspector_activate)
                            bridge.on(InspectorCanceledRequested, self._on_inspector_canceled)
                            bridge.on(InspectorPickMadeRequested, self._on_inspector_pick_made)
                            bridge.on(PickSelectedRequested, self._on_pick_selected)
                            bridge.on(PickCommentUpdatedRequested, self._on_pick_comment_updated)
                            bridge.on(PickDeletedRequested, self._on_pick_deleted)
                            bridge.on(RelationCreatedRequested, self._on_relation_created)
                            bridge.on(RelationDeletedRequested, self._on_relation_deleted)
                            bridge.on(RelationUpdatedRequested, self._on_relation_updated)
                            bridge.on(RegionCreatedRequested, self._on_region_created)
                            bridge.on(RegionDeletedRequested, self._on_region_deleted)
                            bridge.on(RegionUpdatedRequested, self._on_region_updated)
                            bridge.on(RegionSelectedRequested, self._on_region_selected)
                            # Recording handlers (sub-plan 04, COL-1 — inline in _run_browser, not _register_handlers)
                            bridge.on(RecordingStartRequested, self._on_recording_start)
                            bridge.on(RecordingStopRequested, self._on_recording_stop)
                            bridge.on(RecordingRenameRequested, self._on_recording_rename)
                            bridge.on(RecordingSelectedRequested, self._on_recording_selected)
                            bridge.on(RecordedEventCapturedRequested, self._on_recorded_event_captured)

                            # Broadcast after every authoritative mutation (include token)
                            self._sm.add_snapshot_listener(
                                lambda snap: tg.start_soon(self._send_snapshot, bridge, snap, integrity_token)
                            )

                            # Pre-mount-state-fetch (eliminates "flash of defaults"
                            # on cross-origin navigation): overlay's main.ts calls
                            # window.__fp.getState() SYNCHRONOUSLY BEFORE mount(App) —
                            # hydrates panelState before any render-tick.
                            #
                            # Window-namespace-discipline (see ARCHITECTURE.md): expose_function
                            # forces a top-level global. We use an internal marker name;
                            # setupBridge() in the overlay-bridge migrates it to
                            # window.__fp.getState and deletes the marker.
                            # End-state: ONLY window.__fp is in the namespace.
                            #
                            # TOCTOU decision:
                            # This is an architectural false-positive. Playwright's
                            # expose_function can only register top-level window globals
                            # (a CDP constraint, not a frontprompt bug). The TOCTOU
                            # window between expose_function registration and
                            # setupBridge() deleting __fp_internal_state_getter is
                            # synchronously closed at DOMContentLoaded. Third-party
                            # scripts running before DOMContentLoaded are uncommon and
                            # the exposed data (picks/regions/relations from the current
                            # session) is not credentials or cross-user data.
                            # Decision: accept as architectural false-positive.
                            # See ARCHITECTURE.md §Known TOCTOU Limitations for full rationale.
                            # Phase-2 escape hatch: replace fixed name
                            # '__fp_internal_state_getter' with a UUID generated at
                            # startup and propagated via page.evaluate initial seed,
                            # eliminating the expose_function entirely. Trigger: threat
                            # model expands to credentials or cross-user data.
                            #
                            # integrity_token is included in the initial state
                            # dict so main.ts can extract it and pass it to setupBridge.
                            async def _provide_initial_state() -> dict[str, object]:
                                result = self._sm.snapshot().model_dump(mode="json")
                                result["integrity_token"] = integrity_token
                                result["current_session_id"] = self._sm.session_id
                                return result

                            await browser.page.expose_function("__fp_internal_state_getter", _provide_initial_state)

                            # Page setup
                            injector = OverlayInjector(browser, scaffold_script=bundle)
                            await injector.install_init_script()
                            await browser.navigate(self.url)

                            try:
                                ready = await bridge.wait_until_ready(timeout_seconds=10.0)
                                self._log.info(
                                    "show.bridge.ready",
                                    overlay_build_session=ready.bundle_build_session,
                                    overlay_schema_version=ready.schema_version,
                                )
                            except Exception as exc:
                                self._log.warning("show.bridge.ready_timeout", error=str(exc))

                            try:
                                await injector.verify_mounted(timeout_seconds=5.0)
                            except OverlayNotMountedError as exc:
                                self._log.error("show.overlay.verify_failed", error=str(exc))
                                click.echo(f"⚠ Overlay verify failed ({exc}). Browser still open for debugging.")

                            click.echo(
                                f"Browser open at {self.url} with overlay + bridge + state-manager active. "
                                "Panel state survives cross-origin navigation."
                            )

                            resolver = ElementResolver(browser.page)
                            page_controller = PlaywrightPageController(browser.page, resolver)
                            tg.start_soon(
                                run_socket_server,
                                self._sm,
                                Path(session.socket_path),
                                page_controller,
                            )

                            from frontprompt.cli import _wait_for_socket_listening

                            await _wait_for_socket_listening(Path(session.socket_path))

                            click.echo(format_ready_line(session.session_id))
                            click.echo(
                                f"frontprompt session: {session.session_id}  (socket: {session.socket_path})",
                                err=True,
                            )

                            tg.start_soon(self._heartbeat_sender, bridge)

                            await browser.wait_until_closed()
                            self._log.info("show.page.closed_by_user")
                            tg.cancel_scope.cancel()

                tg.start_soon(_signal_watcher)
                tg.start_soon(_run_browser)


__all__ = ["ShowSession"]
