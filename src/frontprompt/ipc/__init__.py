"""IPC layer — unix-socket-basierte Read-Only-API für `frontprompt show`.

Multi-instance via per-session-directories:

    ~/.cache/frontprompt/sessions/<ts>-<rand>/
        show.sock          ← unix socket
        session.json       ← {session_id, pid, url, started_at, socket_path}

Design notes:
    - Single-writer: IPC ist READ-ONLY (snapshot()-pfad ist lock-free)
    - Daemon-singleton: NICHT mehr enforced — wir lassen jetzt
      multiple ``frontprompt show``-instances parallel laufen, jede mit
      eigenem session-dir + socket. Phase-2 daemon-singleton (falls je nötig)
      wäre auf dieser Basis ein optionales lock-file.
    - IPC ist orthogonal zum Browser↔Python channel.

Phase-1 Operations (read-only):
    - ``ping``           — liveness check
    - ``get_snapshot``   — voller authoritative StateSnapshot
    - ``get_picks``      — nur picks-liste
    - ``get_pick(id)``   — einen Pick by id

Phase-2 erweitert ggf. um write-operations + subscribe — Pydantic-
discriminated-union macht das forward-compatible.

Spätere MCP-tools dünnen wrapper hier drüber — IPC ist die SSoT für die
"frontprompt-state-extern-lesen"-Domain.
"""

from frontprompt.ipc.paths import (
    cache_root,
    new_session_id,
    sessions_root,
    socket_path_for,
)
from frontprompt.ipc.protocol import (
    IPC_SCHEMA_VERSION,
    AddAssertionRequest,  # Schema 0.8.0
    AnnotationEntry,
    AttributesReaderResult,
    CondensedHtmlResult,  # Schema 0.4.0
    DomPatchRequest,
    DomPatchResult,
    ElementContextResult,
    EvalJsRequest,
    EvalJsResult,
    FindByRegexRequest,
    FindFirstRequest,
    FindFirstResult,
    FindMultiResult,
    FindOneRequest,
    FindOneResult,
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
    GetRecordingRequest,
    GetRecordingsRequest,
    GetReplayReportRequest,  # Schema 0.8.0
    GetSnapshotRequest,
    GetStateRequest,
    GetStateSummaryRequest,
    GetTextRequest,
    HtmlReaderResult,
    InspectElementsRequest,
    InspectElementsResult,
    IpcRequest,
    IpcResponse,
    ListReplayReportsRequest,  # Schema 0.8.0
    NavigateRequest,
    OutlineNode,
    OutlineReaderResult,
    PageInfoResult,
    PageOutlineResult,
    PickBySelectorRequest,
    PickByTextRequest,
    PickByXpathRequest,
    PickCreatorResult,
    PickFromRefRequest,
    PickFromRefResult,
    PickPathRequest,
    PickPathResult,
    PingRequest,
    RelocatePicksRequest,
    RelocatePicksResult,
    ReplayReportMeta,  # Schema 0.8.0
    RunReplayRequest,  # Schema 0.8.0
    ScreenshotElementRequest,
    ScreenshotPageRequest,
    ScreenshotResult,
    ScrollToRequest,
    ScrollToResult,
    StartRecordingRequest,  # Schema 0.8.0
    StateReaderResult,
    StopRecordingRequest,  # Schema 0.8.0
    TextReaderResult,
)
from frontprompt.ipc.session import (
    SessionMetadata,
    discover_sessions,
    pick_latest_session,
    prune_dead_sessions,
    session_lifecycle,
)
from frontprompt.ipc.replay_player import ReplayPlayer
from frontprompt.ipc.socket_client import IPC_ROUNDTRIP_TIMEOUT_S, IpcConnectError, query
from frontprompt.ipc.socket_server import run_socket_server

__all__ = [
    "IPC_ROUNDTRIP_TIMEOUT_S",
    "ReplayPlayer",
    "IPC_SCHEMA_VERSION",
    "AddAssertionRequest",
    "AnnotationEntry",
    "AttributesReaderResult",
    "CondensedHtmlResult",
    "DomPatchRequest",
    "DomPatchResult",
    "ElementContextResult",
    "EvalJsRequest",
    "EvalJsResult",
    "FindByRegexRequest",
    "FindFirstRequest",
    "FindFirstResult",
    "FindMultiResult",
    "FindOneRequest",
    "FindOneResult",
    "FindSimilarRequest",
    "GetAttributesRequest",
    "GetCommentsRequest",
    "GetElementContextRequest",
    "GetHtmlRequest",
    "GetOutlineRequest",
    "GetPageHtmlRequest",
    "GetPageInfoRequest",
    "GetPageOutlineRequest",
    "GetPickRequest",
    "GetPicksRequest",
    "GetRecordingRequest",
    "GetRecordingsRequest",
    "GetReplayReportRequest",
    "GetSnapshotRequest",
    "GetStateRequest",
    "GetStateSummaryRequest",
    "GetTextRequest",
    "HtmlReaderResult",
    "InspectElementsRequest",
    "InspectElementsResult",
    "IpcConnectError",
    "IpcRequest",
    "IpcResponse",
    "ListReplayReportsRequest",
    "NavigateRequest",
    "OutlineNode",
    "OutlineReaderResult",
    "PageInfoResult",
    "PageOutlineResult",
    "PickBySelectorRequest",
    "PickByTextRequest",
    "PickByXpathRequest",
    "PickCreatorResult",
    "PickFromRefRequest",
    "PickFromRefResult",
    "PickPathRequest",
    "PickPathResult",
    "PingRequest",
    "RelocatePicksRequest",
    "RelocatePicksResult",
    "ReplayReportMeta",
    "RunReplayRequest",
    "ScreenshotElementRequest",
    "ScreenshotPageRequest",
    "ScreenshotResult",
    "ScrollToRequest",
    "ScrollToResult",
    "SessionMetadata",
    "StartRecordingRequest",
    "StateReaderResult",
    "StopRecordingRequest",
    "TextReaderResult",
    "cache_root",
    "discover_sessions",
    "new_session_id",
    "pick_latest_session",
    "prune_dead_sessions",
    "query",
    "run_socket_server",
    "session_lifecycle",
    "sessions_root",
    "socket_path_for",
]
