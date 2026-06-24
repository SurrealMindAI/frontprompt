"""Unix-socket-Client für IPC-queries.

Single-shot: open connection → send NDJSON request → recv NDJSON response →
close. Kein keepalive/subscription in Phase 1.

Bounded round-trip: the daemon→show-child send/recv is wrapped in a finite
timeout (:data:`IPC_ROUNDTRIP_TIMEOUT_S`). If the show-child accepts the
connection but never replies — e.g. its page JS thread is pinned during a bulk
persistence-load + overlay re-render — the client returns a clean
``IpcResponse(ok=False, error="ipc_timeout: ...")`` instead of blocking forever.
This guarantees every MCP tool ALWAYS returns even when the show-child is wedged.
"""

from __future__ import annotations

from pathlib import Path

import anyio
import structlog
from pydantic import TypeAdapter

from frontprompt.ipc.protocol import IpcRequest, IpcResponse

_LOG = structlog.get_logger(__name__)

_REQUEST_ADAPTER: TypeAdapter[IpcRequest] = TypeAdapter(IpcRequest)

#: Finite wall-clock bound for the daemon→show-child IPC round-trip, in seconds.
#: Runtime-latency constant (not magic number): even heavy page ops are themselves
#: bounded by PAGE_OP_TIMEOUT_S (10s) on the show-side, so 30s here is a generous
#: outer envelope that only fires if the show-child is genuinely wedged.
IPC_ROUNDTRIP_TIMEOUT_S: float = 30.0


class IpcConnectError(RuntimeError):
    """Konnten uns nicht mit dem socket connecten — z.B. weil kein show läuft."""


async def query(
    socket_path: Path,
    request: IpcRequest,
    *,
    timeout: float = IPC_ROUNDTRIP_TIMEOUT_S,
) -> IpcResponse:
    """Send request, return response. Raises :class:`IpcConnectError` bei connect-fail.

    ``request`` muss eine concrete subclass von IpcRequest sein (not the union
    type) — wir validieren + dumpen via TypeAdapter um die diskriminator-
    serialisierung sauber zu kriegen.

    Der send/recv round-trip ist auf ``timeout`` Sekunden begrenzt. Bei timeout
    (wedged show-child) wird ein ``IpcResponse(ok=False, error="ipc_timeout: ...")``
    zurückgegeben — der Aufruf hängt NIE unendlich.
    """
    try:
        stream = await anyio.connect_unix(str(socket_path))
    except (FileNotFoundError, ConnectionRefusedError) as exc:
        raise IpcConnectError(f"Kein ``frontprompt show`` an {socket_path} erreichbar: {exc}") from exc

    try:
        with anyio.fail_after(timeout):
            async with stream:
                payload = _REQUEST_ADAPTER.dump_json(request) + b"\n"
                await stream.send(payload)
                # Empfange bis EOF (Server schließt nach response).
                # anyio.receive() raises EndOfStream beim peer-close — fangen + break.
                buf = bytearray()
                try:
                    while True:
                        chunk = await stream.receive(4096)
                        buf.extend(chunk)
                except anyio.EndOfStream:
                    pass
    except TimeoutError:
        _LOG.warning(
            "mcp.tool.ipc.timeout",
            socket=str(socket_path),
            timeout_s=timeout,
        )
        return IpcResponse(
            ok=False,
            error=f"ipc_timeout: show-child did not respond within {timeout}s (socket={socket_path})",
        )

    raw = bytes(buf).strip()
    if not raw:
        raise IpcConnectError(f"Server schloss connection ohne response (socket={socket_path})")
    return IpcResponse.model_validate_json(raw)


__all__ = ["IPC_ROUNDTRIP_TIMEOUT_S", "IpcConnectError", "query"]
