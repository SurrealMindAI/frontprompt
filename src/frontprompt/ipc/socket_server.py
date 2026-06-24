"""Unix-socket-Server für state-queries + browser-actions.

anyio-basiert. Eine connection = ein request = eine response, dann close.
Caller-side dispatch über :class:`~frontprompt.ipc.protocol.IpcRequest`
discriminator.

Lock-discipline (read-side):
    Wir lesen via ``StateManager.snapshot()`` was lock-free ist (siehe
    state/manager.py docstring). Kein conflict mit dem single-writer-pfad
    von :class:`~frontprompt.state.StateManager`.

Write-side (Schema 0.2.0+, :class:`NavigateRequest`):
    Browser-actions gehen via :class:`PageController` an die live Playwright
    Page. Sie mutieren KEIN StateManager-Aggregate — single-writer-conform. Der
    cross-origin ``framenavigated``-handler im show-Prozess re-hydriert das
    Overlay nach jedem navigate vom existing snapshot (state-classification).

Pick-creator-side (Schema 0.3.0, :class:`PickBySelectorRequest`, :class:`PickByTextRequest`):
    Delegiert an :class:`~frontprompt.state.programmatic_picks.ProgrammaticPickService`
    (pre-constructed ONCE in run_socket_server).

PageAnalyzer-side (Schema 0.4.0, :class:`GetPageOutlineRequest` et al.):
    Delegiert an :class:`~frontprompt.analysis.analyzer.PageAnalyzer`
    (pre-constructed ONCE in run_socket_server, analog ProgrammaticPickService).
    Nur ``eval_js``, ``dom_patch``, ``pick_by_xpath`` gehen via page_controller (low-level escape).

Request-size-Cap: 1 MiB. Frame-Delimiter: erster ``\\n``-byte ODER EOF.
"""

from __future__ import annotations

from pathlib import Path
from typing import TYPE_CHECKING, Any

import anyio
import structlog
from anyio.abc import SocketStream
from pydantic import TypeAdapter, ValidationError

from frontprompt.ipc.page_controller import NullPageController, PageController
from frontprompt.ipc.playwright_controller.element_resolver import StalePickError
from frontprompt.ipc.playwright_controller.timeouts import PageOpTimeoutError
from frontprompt.ipc.protocol import (
    AnnotationEntry,
    DomPatchRequest,
    EvalJsRequest,
    FindByRegexRequest,
    FindFirstRequest,
    FindOneRequest,
    FindSimilarRequest,
    GetAttributesRequest,
    GetCommentsRequest,
    GetElementContextRequest,
    GetHtmlRequest,
    GetOutlineRequest,
    GetPageHtmlRequest,
    GetPageInfoRequest,
    GetPageOutlineRequest,
    GetPickRequest,
    GetPicksRequest,
    GetSnapshotRequest,
    GetStateRequest,
    GetStateSummaryRequest,
    GetTextRequest,
    InspectElementsRequest,
    IpcRequest,
    IpcResponse,
    NavigateRequest,
    PickBySelectorRequest,
    PickByTextRequest,
    PickByXpathRequest,
    PickFromRefRequest,
    PickPathRequest,
    PingRequest,
    RelocatePicksRequest,
    ScreenshotElementRequest,
    ScreenshotPageRequest,
    ScrollToRequest,
)
from frontprompt.state import StateManager
from frontprompt.state.state import Pick as _Pick

if TYPE_CHECKING:
    from frontprompt.analysis.analyzer import PageAnalyzer
    from frontprompt.state.programmatic_picks import ProgrammaticPickService

_LOG = structlog.get_logger(__name__)

_REQUEST_ADAPTER: TypeAdapter[IpcRequest] = TypeAdapter(IpcRequest)


def _to_dict(result: object) -> dict[str, Any]:
    """Serialize a Pick (or subclass) to dict, or return as-is if already a dict.

    Supports both real Pick objects (from PageAnalyzer) and dict test-doubles
    (from FakePageAnalyzer), so dispatch code works unchanged under both.
    """
    if isinstance(result, dict):
        return result
    if hasattr(result, "model_dump"):
        return result.model_dump(mode="json")  # type: ignore[no-any-return]
    return dict(result)  # type: ignore[call-overload,no-any-return]


#: Max request-size — Protected gegen unbeschränkten read.
_MAX_REQUEST_BYTES: int = 1 * 1024 * 1024


async def _dispatch(
    state_manager: StateManager,
    page_controller: PageController,
    request: IpcRequest,
    pick_service: ProgrammaticPickService,
    page_analyzer: PageAnalyzer,
) -> IpcResponse:
    """Async dispatch — read-handler bleiben lock-free, navigate awaitet Playwright.

    pick_service and page_analyzer are pre-constructed in run_socket_server
    (not per-request).

    page_analyzer: pre-constructed PageAnalyzer. Handles all
    high-level analysis requests (outline, find_*, context, path, pick_from_ref,
    relocate, inspect). eval_js, dom_patch, pick_by_xpath remain low-level
    page_controller routes.
    """
    if isinstance(request, NavigateRequest):
        try:
            result = await page_controller.navigate(request.url)
        except NotImplementedError as exc:
            return IpcResponse(ok=False, error=f"navigate_unavailable: {exc}")
        except Exception as exc:
            _LOG.warning("ipc.server.navigate_failed", url=request.url, error=str(exc))
            return IpcResponse(ok=False, error=f"navigate_failed: {exc}")
        return IpcResponse(ok=True, data=result)

    if isinstance(request, GetStateSummaryRequest):
        # Read-only navigable overview — does not pay the full-snapshot deep-copy.
        return IpcResponse(ok=True, data=state_manager.state_summary().model_dump(mode="json"))

    if isinstance(request, GetCommentsRequest):
        # Compact annotation surface — picks with non-empty comments only.
        snap_for_comments = state_manager.snapshot()
        entries = [
            AnnotationEntry(
                pick_id=p.pick_id,
                comment=p.comment,
                selector=p.element.selector,
                url=p.url,
            ).model_dump(mode="json")
            for p in snap_for_comments.inspector_state.picks
            if p.comment
        ]
        return IpcResponse(ok=True, data=entries)

    snap = state_manager.snapshot()

    if isinstance(request, PingRequest):
        return IpcResponse(ok=True, data={"pong": True})

    if isinstance(request, GetSnapshotRequest):
        return IpcResponse(ok=True, data=snap.model_dump(mode="json"))

    if isinstance(request, GetPicksRequest):
        return IpcResponse(
            ok=True,
            data=[p.model_dump(mode="json") for p in snap.inspector_state.picks],
        )

    if isinstance(request, GetPickRequest):
        pick = next(
            (p for p in snap.inspector_state.picks if p.pick_id == request.pick_id),
            None,
        )
        if pick is None:
            return IpcResponse(ok=False, error=f"pick_not_found: {request.pick_id}")
        return IpcResponse(ok=True, data=pick.model_dump(mode="json"))

    # resolve pick_ids → Pick map ONCE at top of dispatch.
    # pick_service is pre-constructed in run_socket_server (no lazy per-request build).
    picks_by_id = {p.pick_id: p for p in snap.inspector_state.picks}

    def _resolve_parent_pick(parent_pick_id: str | None) -> _Pick | None:
        """Resolve parent_pick_id string → Pick (or hard-fail)."""
        if parent_pick_id is None:
            return None
        return picks_by_id.get(parent_pick_id)

    # --- Pick-creators ---
    if isinstance(request, PickBySelectorRequest):
        parent_pick = _resolve_parent_pick(request.parent_pick_id)
        if request.parent_pick_id is not None and parent_pick is None:
            return IpcResponse(ok=False, error=f"parent_not_found: {request.parent_pick_id}")
        try:
            result = await pick_service.pick_by_selector(
                request.selector,
                request.comment,
                parent_pick,
                request.limit,
            )
        except StalePickError as exc:
            return IpcResponse(ok=False, error=f"parent_stale: {exc}")
        except Exception as exc:
            return IpcResponse(ok=False, error=f"pick_by_selector_failed: {exc}")
        return IpcResponse(ok=True, data=result)

    if isinstance(request, PickByTextRequest):
        parent_pick = _resolve_parent_pick(request.parent_pick_id)
        if request.parent_pick_id is not None and parent_pick is None:
            return IpcResponse(ok=False, error=f"parent_not_found: {request.parent_pick_id}")
        try:
            result = await pick_service.pick_by_text(
                request.text,
                request.role,
                request.comment,
                parent_pick,
                request.limit,
            )
        except StalePickError as exc:
            return IpcResponse(ok=False, error=f"parent_stale: {exc}")
        except Exception as exc:
            return IpcResponse(ok=False, error=f"pick_by_text_failed: {exc}")
        return IpcResponse(ok=True, data=result)

    # --- Element-readers (resolve pick_ids → list[Pick]) ---

    def _resolve_picks(pick_ids: list[str]) -> tuple[list[_Pick], list[dict[str, str]]]:
        found: list[_Pick] = []
        errors: list[dict[str, str]] = []
        for pid in pick_ids:
            if pid in picks_by_id:
                found.append(picks_by_id[pid])
            else:
                errors.append({"error": "pick_not_found", "pick_id": pid})
        return found, errors

    if isinstance(request, GetTextRequest):
        picks, errs = _resolve_picks(request.pick_ids)
        results = await page_controller.get_text(picks)
        return IpcResponse(ok=True, data=errs + results)

    if isinstance(request, GetHtmlRequest):
        picks, errs = _resolve_picks(request.pick_ids)
        results = await page_controller.get_html(picks, request.max_chars)
        return IpcResponse(ok=True, data=errs + results)

    if isinstance(request, GetAttributesRequest):
        picks, errs = _resolve_picks(request.pick_ids)
        results = await page_controller.get_attributes(picks)
        return IpcResponse(ok=True, data=errs + results)

    if isinstance(request, GetStateRequest):
        picks, errs = _resolve_picks(request.pick_ids)
        results = await page_controller.get_state(picks)
        return IpcResponse(ok=True, data=errs + results)

    if isinstance(request, GetOutlineRequest):
        picks, errs = _resolve_picks(request.pick_ids)
        results = await page_controller.get_outline(picks, request.max_depth, request.max_nodes)
        return IpcResponse(ok=True, data=errs + results)

    if isinstance(request, ScreenshotElementRequest):
        picks, errs = _resolve_picks(request.pick_ids)
        results = await page_controller.screenshot_element(picks, request.padding)
        return IpcResponse(ok=True, data=errs + results)

    # --- Page-level ---
    if isinstance(request, GetPageInfoRequest):
        try:
            result = await page_controller.get_page_info()
        except PageOpTimeoutError as exc:
            return IpcResponse(ok=False, error=f"page_op_timeout: {exc.op}")
        except NotImplementedError as exc:
            return IpcResponse(ok=False, error=f"get_page_info_unavailable: {exc}")
        return IpcResponse(ok=True, data=result)

    if isinstance(request, ScreenshotPageRequest):
        try:
            result = await page_controller.screenshot_page(request.full_page)
        except PageOpTimeoutError as exc:
            return IpcResponse(ok=False, error=f"page_op_timeout: {exc.op}")
        except NotImplementedError as exc:
            return IpcResponse(ok=False, error=f"screenshot_page_unavailable: {exc}")
        return IpcResponse(ok=True, data=result)

    if isinstance(request, ScrollToRequest):
        pick = picks_by_id.get(request.pick_id)
        if pick is None:
            return IpcResponse(ok=False, error=f"pick_not_found: {request.pick_id}")
        try:
            result = await page_controller.scroll_to(pick)
        except PageOpTimeoutError as exc:
            return IpcResponse(ok=False, error=f"page_op_timeout: {exc.op}")
        except NotImplementedError as exc:
            return IpcResponse(ok=False, error=f"scroll_to_unavailable: {exc}")
        return IpcResponse(ok=True, data=result)

    # ── PageAnalyzer high-level (Schema 0.4.0) ─────────────────────────────
    if isinstance(request, GetPageOutlineRequest):
        try:
            result = await page_analyzer.outline(request)  # type: ignore[assignment,arg-type]  # type: ignore[arg-type]
        except Exception as exc:
            return IpcResponse(ok=False, error=f"outline_failed: {exc}")
        return IpcResponse(ok=True, data=result)

    if isinstance(request, GetPageHtmlRequest):
        try:
            result = await page_analyzer.condensed_html(request)  # type: ignore[assignment,arg-type]  # type: ignore[arg-type]
        except Exception as exc:
            return IpcResponse(ok=False, error=f"condensed_html_failed: {exc}")
        return IpcResponse(ok=True, data=result)

    if isinstance(request, PickFromRefRequest):
        try:
            result = await page_analyzer.pick_from_ref(request.ref_id, request.snapshot_id, request.comment)  # type: ignore[assignment]
        except Exception as exc:
            return IpcResponse(ok=False, error=f"pick_from_ref_failed: {exc}")
        if result is None:
            return IpcResponse(ok=True, data={"error": "ref_not_found"})
        data = _to_dict(result)
        # FakePageAnalyzer returns {error: "ref_expired"} dict for expired refs
        if isinstance(data, dict) and data.get("error"):
            return IpcResponse(ok=True, data=data)
        return IpcResponse(ok=True, data=data)

    if isinstance(request, FindOneRequest):
        parent_pick = _resolve_parent_pick(request.parent_pick_id)
        if request.parent_pick_id is not None and parent_pick is None:
            return IpcResponse(ok=False, error=f"parent_not_found: {request.parent_pick_id}")
        try:
            result = await page_analyzer.find_one(request.query, request.comment, parent_pick)  # type: ignore[assignment]
        except Exception as exc:
            # FindAmbiguousError → soft-error response (ok=True) with ambiguous details
            total = getattr(exc, "total_matches", None)
            if total is not None:
                return IpcResponse(ok=True, data={"error": "ambiguous", "total_matches": total})
            return IpcResponse(ok=False, error=f"find_one_failed: {exc}")
        if result is None:
            return IpcResponse(ok=True, data={"error": "not_found"})
        return IpcResponse(ok=True, data=_to_dict(result))

    if isinstance(request, FindFirstRequest):
        parent_pick = _resolve_parent_pick(request.parent_pick_id)
        if request.parent_pick_id is not None and parent_pick is None:
            return IpcResponse(ok=False, error=f"parent_not_found: {request.parent_pick_id}")
        try:
            result = await page_analyzer.find_first(request.query, request.comment, parent_pick)  # type: ignore[assignment]
        except Exception as exc:
            return IpcResponse(ok=False, error=f"find_first_failed: {exc}")
        if result is None:
            return IpcResponse(ok=True, data={"error": "not_found"})
        # Real PageAnalyzer returns (Pick, int) tuple; FakePageAnalyzer returns dict
        if isinstance(result, tuple):
            pick, total_matches = result
            return IpcResponse(ok=True, data={**_to_dict(pick), "total_matches": total_matches})
        return IpcResponse(ok=True, data=_to_dict(result))

    if isinstance(request, FindSimilarRequest):
        anchor_pick = picks_by_id.get(request.anchor_pick_id)
        if anchor_pick is None:
            return IpcResponse(ok=False, error=f"pick_not_found: {request.anchor_pick_id}")
        try:
            result = await page_analyzer.find_similar(
                anchor_pick, request.threshold, request.max_results, request.comment
            )  # type: ignore[assignment]
        except Exception as exc:
            return IpcResponse(ok=False, error=f"find_similar_failed: {exc}")
        return IpcResponse(ok=True, data=_to_dict(result))

    if isinstance(request, FindByRegexRequest):
        parent_pick = _resolve_parent_pick(request.parent_pick_id)
        if request.parent_pick_id is not None and parent_pick is None:
            return IpcResponse(ok=False, error=f"parent_not_found: {request.parent_pick_id}")
        try:
            result = await page_analyzer.find_by_regex(
                request.pattern, request.field, parent_pick, request.comment, request.limit
            )  # type: ignore[assignment]
        except Exception as exc:
            return IpcResponse(ok=False, error=f"find_by_regex_failed: {exc}")
        return IpcResponse(ok=True, data=_to_dict(result))

    if isinstance(request, GetElementContextRequest):
        pick = picks_by_id.get(request.pick_id)
        if pick is None:
            return IpcResponse(ok=False, error=f"pick_not_found: {request.pick_id}")
        try:
            result = await page_analyzer.context(pick, request.levels_up, request.sibling_radius)  # type: ignore[assignment]
        except Exception as exc:
            return IpcResponse(ok=False, error=f"context_failed: {exc}")
        return IpcResponse(ok=True, data=result)

    if isinstance(request, PickPathRequest):
        pick = picks_by_id.get(request.pick_id)
        if pick is None:
            return IpcResponse(ok=False, error=f"pick_not_found: {request.pick_id}")
        try:
            result = await page_analyzer.path(pick)  # type: ignore[assignment]
        except Exception as exc:
            return IpcResponse(ok=False, error=f"path_failed: {exc}")
        return IpcResponse(ok=True, data={"path": result})

    if isinstance(request, RelocatePicksRequest):
        if request.pick_ids is None:
            target_picks = list(picks_by_id.values())
        else:
            target_picks = [picks_by_id[pid] for pid in request.pick_ids if pid in picks_by_id]
        try:
            result = await page_analyzer.relocate(target_picks)  # type: ignore[assignment]
        except Exception as exc:
            return IpcResponse(ok=False, error=f"relocate_failed: {exc}")
        return IpcResponse(ok=True, data=result)

    if isinstance(request, InspectElementsRequest):
        picks, errs = _resolve_picks(request.pick_ids)
        try:
            raw_results = await page_analyzer.inspect(picks, request.fields)  # type: ignore[arg-type]
        except Exception as exc:
            return IpcResponse(ok=False, error=f"inspect_failed: {exc}")
        # Serialize InspectResult objects with exclude_unset so only requested fields appear.
        # exclude_unset=True keeps fields explicitly set to None (e.g. checked=None for h1)
        # while excluding fields that were never assigned (unrequested fields).
        inspect_results: list[dict[str, Any]] = [
            r.model_dump(mode="json", exclude_unset=True) if hasattr(r, "model_dump") else r  # type: ignore[misc]
            for r in raw_results
        ]
        return IpcResponse(ok=True, data=errs + inspect_results)

    # ── Low-level escape (Schema 0.4.0) — page_controller only ────────────
    if isinstance(request, EvalJsRequest):
        pick_arg = picks_by_id.get(request.pick_id_arg) if request.pick_id_arg else None
        try:
            result = await page_controller.eval_js(request.expression, pick_arg, request.mutating)
            if request.mutating:
                page_analyzer.invalidate_snapshot()
        except NotImplementedError as exc:
            return IpcResponse(ok=False, error=f"eval_js_unavailable: {exc}")
        except Exception as exc:
            return IpcResponse(ok=False, error=f"eval_js_failed: {exc}")
        return IpcResponse(ok=True, data=result)

    if isinstance(request, DomPatchRequest):
        pick = picks_by_id.get(request.pick_id)
        if pick is None:
            return IpcResponse(ok=False, error=f"pick_not_found: {request.pick_id}")
        try:
            result = await page_controller.dom_patch(pick, [op.model_dump() for op in request.operations])
            page_analyzer.invalidate_snapshot()  # always invalidate on dom_patch
        except NotImplementedError as exc:
            return IpcResponse(ok=False, error=f"dom_patch_unavailable: {exc}")
        except Exception as exc:
            return IpcResponse(ok=False, error=f"dom_patch_failed: {exc}")
        return IpcResponse(ok=True, data=result)

    if isinstance(request, PickByXpathRequest):
        parent_pick = _resolve_parent_pick(request.parent_pick_id)
        if request.parent_pick_id is not None and parent_pick is None:
            return IpcResponse(ok=False, error=f"parent_not_found: {request.parent_pick_id}")
        try:
            raw_result = await page_controller.pick_by_xpath_raw(request.xpath, parent_pick, request.limit)
        except NotImplementedError as exc:
            return IpcResponse(ok=False, error=f"pick_by_xpath_unavailable: {exc}")
        except Exception as exc:
            return IpcResponse(ok=False, error=f"pick_by_xpath_failed: {exc}")
        # Materialize into picks via pick_service
        try:
            created = await pick_service.pick_from_xpath_elements(raw_result, request.comment)
        except Exception as exc:
            return IpcResponse(ok=False, error=f"pick_by_xpath_pick_failed: {exc}")
        return IpcResponse(ok=True, data=created)

    # Sollte nie erreicht werden — discriminated union ist exhaustive
    return IpcResponse(ok=False, error=f"unknown_request_kind: {type(request).__name__}")


async def _read_frame(stream: SocketStream) -> bytes:
    """Read bytes bis zum ersten ``\\n`` ODER EOF. Cap auf _MAX_REQUEST_BYTES.

    anyio.receive() raises ``EndOfStream`` beim peer-close (NICHT empty-bytes).
    """
    buf = bytearray()
    try:
        while True:
            chunk = await stream.receive(4096)
            buf.extend(chunk)
            nl_idx = buf.find(b"\n")
            if nl_idx != -1:
                return bytes(buf[:nl_idx])
            if len(buf) >= _MAX_REQUEST_BYTES:
                raise ValueError(f"request exceeded {_MAX_REQUEST_BYTES} bytes")
    except anyio.EndOfStream:
        _LOG.debug("ipc.server.read_frame.end_of_stream", msg="connection closed gracefully by peer")
    return bytes(buf)


async def _handle_connection(
    state_manager: StateManager,
    page_controller: PageController,
    stream: SocketStream,
    pick_service: ProgrammaticPickService,  # required, pre-constructed in run_socket_server
    page_analyzer: PageAnalyzer,
) -> None:
    """Eine connection: read request → dispatch → send response → close."""
    async with stream:
        try:
            raw = await _read_frame(stream)
            if not raw:
                response = IpcResponse(ok=False, error="empty_request")
            else:
                try:
                    request = _REQUEST_ADAPTER.validate_json(raw)
                except ValidationError as exc:
                    response = IpcResponse(
                        ok=False,
                        error=f"validation_error: {exc.errors()[:3]}",
                    )
                else:
                    kind = type(request).__name__
                    # Entry/exit tracing: a hang in a page-op leaves the matching
                    # ``ipc.dispatch.start`` as the last line with no ``.done``.
                    _LOG.info("ipc.dispatch.start", request_kind=kind)
                    try:
                        response = await _dispatch(state_manager, page_controller, request, pick_service, page_analyzer)
                    except PageOpTimeoutError as exc:
                        # Safety net: any page-op timeout not caught at its route
                        # still produces a clean response so the daemon never hangs.
                        _LOG.warning("ipc.dispatch.page_op_timeout", request_kind=kind, op=exc.op)
                        response = IpcResponse(ok=False, error=f"page_op_timeout: {exc.op}")
                    _LOG.info("ipc.dispatch.done", request_kind=kind, ok=response.ok)
            await stream.send(response.model_dump_json().encode("utf-8") + b"\n")
        except Exception as exc:
            _LOG.exception("ipc.server.handler_failed", error=str(exc))


async def run_socket_server(
    state_manager: StateManager,
    socket_path: Path,
    page_controller: PageController | None = None,
    pick_service: ProgrammaticPickService | None = None,
    page_analyzer: PageAnalyzer | None = None,
) -> None:
    """Run unix-socket-server bis das outer cancel-scope feuert.

    Wird als TaskGroup-child gespawnt in :func:`frontprompt.cli._show_async_main`::

        tg.start_soon(run_socket_server, state_manager, Path(session.socket_path), page_controller)

    ``page_controller`` ist optional rückwärts-kompatibel — Aufrufer ohne live
    Browser (Tests, read-only legacy paths) lassen den Default
    :class:`NullPageController` greifen, der :class:`NavigateRequest` mit
    ``navigate_unavailable`` ablehnt. Die show-CLI gibt einen echten
    :class:`PlaywrightPageController` mit der live Page rein.

    ``pick_service`` ist optional rückwärts-kompatibel. Wenn None,
    wird eine :class:`~frontprompt.state.programmatic_picks.ProgrammaticPickService`
    ONCE bei Server-Boot konstruiert (nicht per-request) aus state_manager +
    controller. Die show-CLI kann einen pre-built Service reingeben.

    ``page_analyzer`` ist optional rückwärts-kompatibel (analog
    pick_service). Wenn None, wird ein :class:`PageAnalyzer` ONCE bei Server-Boot
    konstruiert wenn controller eine live Page hat; sonst :class:`NullPageAnalyzer`.
    Tests können einen :class:`FakePageAnalyzer` reingeben.

    Auto-removes existing socket (anyio convention). Beim cancel-scope-exit
    schließt anyio den listener; die session-cleanup-logic löscht dann den
    socket-path (siehe :func:`frontprompt.ipc.session.session_lifecycle`).
    """
    log = _LOG.bind(socket_path=str(socket_path))
    log.info("ipc.server.start")

    from frontprompt.analysis.analyzer import PageAnalyzer as _PA
    from frontprompt.state.programmatic_picks import ProgrammaticPickService as _PPS

    controller = page_controller if page_controller is not None else NullPageController()

    # construct PageAnalyzer ONCE at server-boot, not per-request.
    # NullPageController has no live page — provide NullPageAnalyzer stub.
    if page_analyzer is not None:
        analyzer: PageAnalyzer = page_analyzer
    elif hasattr(controller, "page") and controller.page is not None:
        analyzer = _PA(
            page=controller.page,
            resolver=controller.resolver,  # type: ignore[attr-defined]
            state_manager=state_manager,
            page_controller=controller,
        )
    else:
        from frontprompt.analysis.analyzer import NullPageAnalyzer as _NPA

        analyzer = _NPA()  # type: ignore[assignment]

    # construct ProgrammaticPickService ONCE at server-boot, not per-request.
    # Pass analyzer so pick_by_text uses PageAnalyzer.find_by_text (v0.4.0 rewire).
    from frontprompt.analysis.analyzer import NullPageAnalyzer as _NPA2

    _analyzer_for_svc = analyzer if not isinstance(analyzer, _NPA2) else None
    svc = pick_service if pick_service is not None else _PPS(state_manager, controller, _analyzer_for_svc)

    socket_path.parent.mkdir(parents=True, exist_ok=True)
    # anyio.create_unix_listener entfernt nur stale SOCKETS, nicht regular files.
    # Defensiv vorab unlinken (handles beides + leere lifecycle-state).
    if socket_path.exists():
        try:
            socket_path.unlink()
        except OSError as exc:
            log.warning("ipc.server.unlink_failed", error=str(exc))

    listener = await anyio.create_unix_listener(str(socket_path), mode=0o600)
    log.info("ipc.server.listening")

    try:
        await listener.serve(lambda stream: _handle_connection(state_manager, controller, stream, svc, analyzer))
    finally:
        await listener.aclose()
        log.info("ipc.server.stopped")


__all__ = ["run_socket_server"]
