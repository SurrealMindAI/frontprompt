"""HTTP Mutation Endpoint — Channel 3: Tab → Daemon.

Wire-boundary: dieser Endpoint ist reines Ingestion-Artefakt.
Er nimmt ``MutationEnvelope``-Bodies an, validiert den ``Idempotency-Key``-Header,
und leitet Mutations als ``IntentRequest`` an den PE-BC-Nursery weiter.

Kein ``event_bus``-Argument — Events entstehen nachgelagert im PE-BC-Aggregat-
Verarbeitungspfad. ``event_bus`` im HTTP-Layer wäre ein Wire-Boundary- +
Single-Writer-Bruch.

Origin-Check: nur ``http://127.0.0.1:<port>`` und ``http://localhost:<port>``
(exact-match, kein Wildcard — analog einer Origin-Allowlist).

Idempotency-Key TTL: 300 s via ``DaemonClock.idempotency_ttl_expired()`` (daemon wall-clock).
Lazy eviction: bei jedem POST werden expired Entries aus dem Cache entfernt.

F-7 Detection Hook: Placeholder-Kommentar im Cache-Lookup-Pfad — wird in dem
Bundle aktiviert, das World-State-Hash-Berechnungen implementiert.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import TYPE_CHECKING, Any

import structlog
from pydantic import ValidationError
from starlette.applications import Starlette
from starlette.requests import Request
from starlette.responses import JSONResponse, Response
from starlette.routing import Route

from frontprompt.clock import MonotonicSnapshot
from frontprompt.queue import IntentRequest
from frontprompt.wire.mutations import (
    AnnotationDraftSubmitted,
    IdempotencyKey,
    MutationEnvelope,
    PickRequested,
)

if TYPE_CHECKING:
    from anyio.streams.memory import MemoryObjectSendStream

    from frontprompt.clock import DaemonClock

_LOG = structlog.get_logger(__name__)

#: Idempotency-Key TTL in Nanosekunden: 300 Sekunden.
IDEMPOTENCY_TTL_NS: int = 300 * 1_000_000_000


@dataclass
class CachedResponse:
    """Gecachte HTTP-Response für Idempotency-Replay.

    ``snapshot`` ist der monotonic-Clock-Snapshot zum Zeitpunkt des ersten
    erfolgreichen POST. TTL-Prüfung erfolgt via
    ``clock.idempotency_ttl_expired(snapshot, IDEMPOTENCY_TTL_NS)``.
    """

    snapshot: MonotonicSnapshot
    status_code: int
    body: dict[str, Any]


class IdempotencyReplayCache:
    """In-memory Idempotency-Key → CachedResponse Map.

    Lazy eviction: bei jedem ``lookup()`` und ``store()`` werden expired
    Entries aus dem Cache entfernt. Kein Background-Task, kein Timer —
    KISS, ausreichend für den Daemon-Use-Case (niedrige Mutation-Rate).

    F-7 Detection Hook: Placeholder in ``lookup()`` — sobald World-State-Hash
    verfügbar ist, wird hier geprüft ob der gecachte State noch der aktuelle ist.
    """

    def __init__(self, clock: DaemonClock) -> None:
        self._clock = clock
        self._store: dict[IdempotencyKey, CachedResponse] = {}

    def _evict_expired(self) -> None:
        """Entfernt alle Entries deren TTL abgelaufen ist (lazy eviction)."""
        expired_keys = [
            k for k, v in self._store.items() if self._clock.idempotency_ttl_expired(v.snapshot, IDEMPOTENCY_TTL_NS)
        ]
        for k in expired_keys:
            del self._store[k]
            _LOG.debug("idempotency_cache.evicted", idempotency_key=k)

    def lookup(self, key: IdempotencyKey) -> CachedResponse | None:
        """Gibt gecachte Response zurück wenn Key bekannt und nicht expired.

        TODO(F-7): Wenn World-State-Hash verfügbar: prüfen ob
        ``cached.world_state_hash != current_world_state_hash`` →
        log ``idempotency_f7_world_state_drift`` + return None (kein Replay).
        """
        self._evict_expired()
        cached = self._store.get(key)
        if cached is None:
            return None
        # TTL nochmal prüfen nach eviction (Race-free da single-threaded anyio)
        if self._clock.idempotency_ttl_expired(cached.snapshot, IDEMPOTENCY_TTL_NS):
            del self._store[key]
            return None
        return cached

    def store(self, key: IdempotencyKey, response: CachedResponse) -> None:
        """Speichert Response für key. Evictet expired Entries zuerst."""
        self._evict_expired()
        self._store[key] = response

    def size(self) -> int:
        """Aktuelle Cache-Größe (nach eviction). Nur für Tests."""
        self._evict_expired()
        return len(self._store)


def _mutation_to_intent_request(mutation: MutationEnvelope) -> IntentRequest:
    """Mapped MutationEnvelope auf IntentRequest (Prefix-Konvention).

    Raises:
        ValueError: bei unbekanntem Mutation-Typ (sollte durch discriminated union
            Pydantic-Validation bereits abgefangen sein — defensive Belt-and-Suspenders).
    """
    # MutationEnvelope ist BaseModel mit `payload`-Field, NICHT RootModel mit
    # `.root`. `mutation.root` würde AttributeError werfen.
    payload = mutation.payload
    if isinstance(payload, PickRequested):
        # PickRequested-Felder sind
        # `pointing_session_id`, `selector`, `score`, `idempotency_key`.
        # Die Felder `page_session_id`, `interaction_flow_step_id`, `dom_snapshot_hash`
        # gehören zu AnnotationDraftSubmitted (optional dehydrated IDs).
        return IntentRequest(
            intent_type="request.pick",
            # PickRequested trägt KEINE dehydrated cross-BC-IDs — diese werden vom
            # PointingSession-owner-task im BC nachgeschlagen wenn nötig.
            page_session_id=None,
            interaction_flow_step_id=None,
            dom_snapshot_hash=None,
        )
    if isinstance(payload, AnnotationDraftSubmitted):
        return IntentRequest(
            intent_type="notify.annotation_added",
            page_session_id=payload.page_session_id,
            interaction_flow_step_id=payload.interaction_flow_step_id,
            dom_snapshot_hash=payload.dom_snapshot_hash,
        )
    # Should be unreachable: Pydantic discriminated union rejects unknown types.
    raise ValueError(f"Unbekannter Mutation-Typ: {type(payload).__name__!r}")  # pragma: no cover


def _build_app(
    intent_queue_send: MemoryObjectSendStream[IntentRequest],
    cache: IdempotencyReplayCache,
    allowed_origins: frozenset[str],
) -> Starlette:
    """Baut die Starlette-ASGI-App. Intern; wird von ``run_http_server`` gerufen.

    Trennt App-Konstruktion von Startlogik damit Tests die App direkt instanziieren
    können (``httpx.ASGITransport``), ohne ``run_http_server`` aufrufen zu müssen.
    """

    async def mutations_endpoint(request: Request) -> Response:
        # --- Origin-Check ---
        origin = request.headers.get("origin", "")
        if origin not in allowed_origins:
            _LOG.warning(
                "http_mutation.origin_rejected",
                origin=origin,
                allowed=list(allowed_origins),
            )
            return JSONResponse({"error": "forbidden"}, status_code=403)

        # --- Idempotency-Key Header ---
        raw_key = request.headers.get("idempotency-key", "").strip()
        if not raw_key:
            return JSONResponse(
                {"error": "Idempotency-Key header required"},
                status_code=400,
            )
        idempotency_key = IdempotencyKey(raw_key)

        # --- Idempotency-Replay-Check ---
        cached = cache.lookup(idempotency_key)
        if cached is not None:
            _LOG.info(
                "idempotency_replay_short_circuit",
                idempotency_key=idempotency_key,
            )
            return JSONResponse(cached.body, status_code=cached.status_code)

        # --- Body-Parse ---
        try:
            raw_body = await request.json()
        except Exception:
            return JSONResponse({"error": "invalid JSON body"}, status_code=400)

        try:
            envelope = MutationEnvelope.model_validate(raw_body)
        except ValidationError as exc:
            return JSONResponse(
                {"error": "validation failed", "detail": exc.errors()},
                status_code=422,
            )

        # --- Mutation → IntentRequest forward ---
        intent = _mutation_to_intent_request(envelope)
        await intent_queue_send.send(intent)
        _LOG.info(
            "http_mutation.forwarded",
            idempotency_key=idempotency_key,
            intent_type=intent.intent_type,
        )

        # --- Response + Cache ---
        response_body: dict[str, Any] = {"idempotency_key": idempotency_key, "accepted": True}
        # Snapshot nach dem send() — garantiert dass der Cache-TTL frühestens
        # nach dem erfolgreichen send() startet.
        # clock ist via closure über cache._clock zugreifbar — akzeptiert weil _build_app
        # und IdempotencyReplayCache im selben Modul leben.
        snapshot = cache._clock.monotonic()
        cache.store(idempotency_key, CachedResponse(snapshot=snapshot, status_code=202, body=response_body))

        return JSONResponse(response_body, status_code=202)

    return Starlette(
        routes=[Route("/mutations/", mutations_endpoint, methods=["POST"])],
    )


async def run_http_server(
    intent_queue_send: MemoryObjectSendStream[IntentRequest],
    clock: DaemonClock,
    host: str = "127.0.0.1",
    port: int = 7178,
) -> None:
    """HTTP-Mutation-Endpoint starten und bis zur äußeren Cancellation blockieren.

    Bindet Starlette via uvicorn an ``host:port``. Läuft als anyio-Task im
    PE-BC-Nursery-TaskGroup-Block.

    Port 7178 — absichtlich nicht 7177 (WS-Server). Beide Server müssen
    gleichzeitig laufen; gleicher Port würde ``OSError: [Errno 98] Address already in use``
    produzieren.

    Args:
        intent_queue_send: Send-end der IntentRequestQueue (IS-BC-Nursery besitzt
            die receive-end; PE-BC sendet hier die HTTP-Mutations weiter).
        clock: DaemonClock für Idempotency-TTL-Berechnungen.
        host: TCP-Host. Default: ``"127.0.0.1"`` (localhost-only).
        port: TCP-Port. Default: ``7178``.
    """
    import uvicorn

    allowed_origins = frozenset(
        [
            f"http://{host}:{port}",
            f"http://localhost:{port}",
        ]
    )
    cache = IdempotencyReplayCache(clock=clock)
    app = _build_app(intent_queue_send, cache, allowed_origins)

    _LOG.info("http_mutation_server.startup", host=host, port=port)

    config = uvicorn.Config(app=app, host=host, port=port, log_config=None, timeout_graceful_shutdown=1)
    server = uvicorn.Server(config=config)
    await server.serve()
