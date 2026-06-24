"""run_ws_push_server() — Channel-2 WebSocket Push Server.

Nimmt EventEnvelope-Objekte aus dem InProcessEventBus und sendet sie als
JSON-RPC-2.0-Notifications (method=``wire.event``, kein ``id``-Feld) an alle
verbundenen WS-Clients.

Design-Constraints:

* websockets.asyncio.server.serve() direkt (NICHT ein generic JSON-RPC serve()-Loop), weil:
  1. Channel 2 ist reiner Server-Push — kein RPC-Call vom Client.
     Ein generic serve()-Loop ist für JSON-RPC Request/Response designed.
  2. Der port=0-Case braucht Late-Binding der OriginAllowlist nach Bind.
  3. Kein MethodRegistry-Dispatcher benötigt (Push ist unidirektional).
  Der einzige Verlust: OTel-Metering aus dem generic Server-Loop —
  für das Observability-Bundle (YAGNI für den Skeleton).

* OriginAllowlist ist exact-match-only: ``[f'http://{host}:{port}', f'http://localhost:{port}']``.
  KEIN Wildcard. Wird NACH dem Bind mit dem tatsächlichen Port konstruiert (port=0-Case).

* Subscriber-Registration: Jeder WS-Client-Handler subscribed via event_bus.subscribe()
  beim Connect — synchron, vor dem ersten emit(). Garantiert durch die Reihenfolge:
  WS-Client connected → Handler subscribed → wartet auf Events.
  Neue Events die zwischen Client-Connect und erstem recv() emittiert werden landen im Buffer.

* Cancellation: run_ws_push_server() blockiert mit anyio.sleep_forever() im
  ``async with serve(...) as ws_server:`` Block.
  Outer-cancel bricht sleep_forever() → context-manager-exit → Server shutdown.

* TODO: anyio.Event als Readiness-Signal statt anyio.sleep(0.05) in Tests.
  Robustere Alternative für CI auf langsamen Maschinen — YAGNI bis CI-failure.

Anyio-only concurrency: kein asyncio.create_task().
Naming-Konvention: Parameter domain-qualified (``event_bus``, ``host``, ``port``).
"""

from __future__ import annotations

import http
import json
import logging
from typing import TYPE_CHECKING

import anyio

from frontprompt.wire.event_bus import InProcessEventBus

if TYPE_CHECKING:
    from websockets.asyncio.server import ServerConnection
    from websockets.http11 import Request, Response

_LOG = logging.getLogger(__name__)

#: JSON-RPC-2.0 Notification method-name für Daemon→Tab Events.
#: Clients subscriben auf diese method, kein ``id``-Feld.
WIRE_EVENT_METHOD = "wire.event"


async def run_ws_push_server(
    event_bus: InProcessEventBus,
    host: str = "127.0.0.1",
    port: int = 7177,
) -> None:
    """Start den WebSocket-Push-Server und blockiert bis cancelled.

    Jeder WS-Client der sich verbindet bekommt eine Goroutine (anyio task_group)
    die aus dem event_bus subscribed und Events als Notifications pusht.

    Args:
        event_bus: Der InProcessEventBus — subscribe() wird pro Client-Connect aufgerufen.
        host: Bind-Adresse. Default: ``"127.0.0.1"`` (localhost-only).
        port: Bind-Port. ``0`` = random free port (CI-safe).
            Setzt ``event_bus.bound_port`` nach erfolgreichem Bind.
    """
    import websockets.asyncio.server as _ws_server_mod

    # actual_port_holder: list als mutable closure-Träger (Python-Closures können
    # auf äußere immutable-Variablen nicht schreiben — list[int] ist KISS-Idiom).
    actual_port_holder: list[int] = []

    async def _process_request_with_late_allowlist(
        connection: ServerConnection,
        request: Request,
    ) -> Response | None:
        """OriginAllowlist mit tatsächlichem Port prüfen.

        Wird von websockets pro Handshake aufgerufen — zu diesem Zeitpunkt ist
        actual_port_holder bereits befüllt (Bind geschieht vor erstem Connect).
        """
        if not actual_port_holder:
            # Defensiv: sollte nie passieren, da Bind vor Connect
            return connection.respond(http.HTTPStatus.SERVICE_UNAVAILABLE, "not ready\n")

        actual_port = actual_port_holder[0]
        allowed_origins = frozenset(
            [
                f"http://{host}:{actual_port}",
                f"http://localhost:{actual_port}",
            ]
        )
        origin: str | None = request.headers.get("Origin")
        if origin not in allowed_origins:
            return connection.respond(http.HTTPStatus.FORBIDDEN, "forbidden\n")
        return None  # allow upgrade

    async def _client_handler(ws: ServerConnection) -> None:
        """Pro-Client-Handler: subscribed am event_bus und pusht Events.

        subscribe() ist synchron — garantiert keine subscribe-after-emit-Race.
        """
        recv_stream = event_bus.subscribe()
        try:
            async with recv_stream:
                async for envelope in recv_stream:
                    notification = json.dumps(
                        {
                            "jsonrpc": "2.0",
                            "method": WIRE_EVENT_METHOD,
                            "params": envelope.model_dump(mode="json"),
                        }
                    )
                    await ws.send(notification)
        except (anyio.ClosedResourceError, anyio.EndOfStream):
            pass  # Bus geschlossen oder Client getrennt — sauber beenden
        except Exception:
            _LOG.exception("wire.event push error — client handler terminated")

    async with _ws_server_mod.serve(
        _client_handler,
        host,
        port,
        process_request=_process_request_with_late_allowlist,
        reuse_address=True,  # allow quick rebind after cancel (test isolation)
    ) as ws_server:
        # Tatsächlichen Port nach Bind lesen
        sockets = ws_server.sockets
        if sockets:
            actual_port = sockets[0].getsockname()[1]
        else:
            actual_port = port  # fallback für bekannten Port

        actual_port_holder.append(actual_port)
        event_bus.bound_port = actual_port

        _LOG.info(
            "ws_push_server.started host=%s port=%d",
            host,
            actual_port,
        )

        await anyio.sleep_forever()
