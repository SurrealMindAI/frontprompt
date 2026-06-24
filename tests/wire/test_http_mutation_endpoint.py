"""Integration-Tests für den HTTP-Mutation-Endpoint.

Alle Tests laufen in-process via ``httpx.AsyncClient(transport=httpx.ASGITransport(app=app))``.
Kein uvicorn-Start, kein Port-Bind, kein Netzwerk-I/O. Fast und deterministisch.

Test-Setup:
    - ``FrozenClock`` für deterministisches TTL-Verhalten
    - ``anyio.create_memory_object_stream`` für IntentRequest-Queue (Spy-Pattern)
    - ``_build_app()`` direkt (kein run_http_server, kein uvicorn)
"""

from __future__ import annotations

import anyio
import httpx
import pytest
from anyio.streams.memory import MemoryObjectReceiveStream, MemoryObjectSendStream

from frontprompt.clock import FrozenClock, MonotonicSnapshot
from frontprompt.queue import IntentRequest
from frontprompt.wire.http_server import (
    IDEMPOTENCY_TTL_NS,
    CachedResponse,
    IdempotencyReplayCache,
    _build_app,
)
from frontprompt.wire.mutations import IdempotencyKey

# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------


@pytest.fixture
def frozen_clock() -> FrozenClock:
    """FrozenClock mit monotonic_ns=0 (Epoch-Start)."""
    return FrozenClock(monotonic_ns=0)


@pytest.fixture
def intent_queue() -> tuple[MemoryObjectSendStream[IntentRequest], MemoryObjectReceiveStream[IntentRequest]]:
    """Frisches anyio MemoryObjectStream-Paar für IntentRequest-Spy."""
    send, recv = anyio.create_memory_object_stream[IntentRequest](max_buffer_size=32)
    return send, recv


@pytest.fixture
def allowed_origins() -> frozenset[str]:
    return frozenset(["http://127.0.0.1:7178", "http://localhost:7178"])


# ---------------------------------------------------------------------------
# Hilfsfunktionen
# ---------------------------------------------------------------------------


# Test-Helpers korrigiert auf schema-konforme Payloads.
# PickRequested-Felder (per events.py): pointing_session_id, selector, score, idempotency_key.
# KEINE dehydrated cross-BC-IDs (page_session_id etc — die gehören zu AnnotationDraftSubmitted).
# Plus: type-discriminator ist snake_case (`pick_requested`/`annotation_draft_submitted`), nicht PascalCase.
# Envelope muss schema_version + received_at_monotonic_ns + payload-wrapper enthalten.
def _pick_requested_body(
    pointing_session_id: str = "01HYYYYYYYYYYYYYYYYYYYYYY",
    selector: str = "div.hero-button",
    score: str = "0.95",
    idempotency_key: str = "test-key-pick",
) -> dict[str, object]:
    return {
        "schema_version": 1,
        "received_at_monotonic_ns": 0,
        "payload": {
            "type": "pick_requested",
            "pointing_session_id": pointing_session_id,
            "selector": selector,
            "score": score,
            "idempotency_key": idempotency_key,
        },
    }


def _annotation_body(
    pointing_session_id: str = "01HYYYYYYYYYYYYYYYYYYYYYY",
    page_session_id: str | None = "01HXXXXXXXXXXXXXXXXXXXXXXX",
    content: str = "Click the login button",
    idempotency_key: str = "test-key-anno",
) -> dict[str, object]:
    return {
        "schema_version": 1,
        "received_at_monotonic_ns": 0,
        "payload": {
            "type": "annotation_draft_submitted",
            "pointing_session_id": pointing_session_id,
            "content": content,
            "idempotency_key": idempotency_key,
            "page_session_id": page_session_id,  # optional dehydrated ID
            "interaction_flow_step_id": None,
            "dom_snapshot_hash": None,
        },
    }


# ---------------------------------------------------------------------------
# Happy-Path: PickRequested
# ---------------------------------------------------------------------------


@pytest.mark.anyio
async def test_pick_requested_returns_202(
    frozen_clock: FrozenClock,
    intent_queue: tuple[MemoryObjectSendStream[IntentRequest], MemoryObjectReceiveStream[IntentRequest]],
    allowed_origins: frozenset[str],
) -> None:
    """POST PickRequested mit gültigem Origin + Idempotency-Key → HTTP 202."""
    send, _recv = intent_queue
    cache = IdempotencyReplayCache(clock=frozen_clock)
    app = _build_app(send, cache, allowed_origins)

    async with httpx.AsyncClient(transport=httpx.ASGITransport(app=app), base_url="http://test") as client:
        resp = await client.post(
            "/mutations/",
            json=_pick_requested_body(),
            headers={
                "Origin": "http://127.0.0.1:7178",
                "Idempotency-Key": "test-pick-001",
            },
        )

    assert resp.status_code == 202
    assert resp.json()["idempotency_key"] == "test-pick-001"
    assert resp.json()["accepted"] is True


@pytest.mark.anyio
async def test_pick_requested_enqueues_intent_request(
    frozen_clock: FrozenClock,
    intent_queue: tuple[MemoryObjectSendStream[IntentRequest], MemoryObjectReceiveStream[IntentRequest]],
    allowed_origins: frozenset[str],
) -> None:
    """PickRequested → IntentRequest mit intent_type=request.pick in Queue.

    PickRequested hat kein page_session_id —
    deshalb ist intent.page_session_id immer None für request.pick IntentRequests.
    """
    send, recv = intent_queue
    cache = IdempotencyReplayCache(clock=frozen_clock)
    app = _build_app(send, cache, allowed_origins)

    async with httpx.AsyncClient(transport=httpx.ASGITransport(app=app), base_url="http://test") as client:
        await client.post(
            "/mutations/",
            json=_pick_requested_body(),
            headers={"Origin": "http://127.0.0.1:7178", "Idempotency-Key": "enqueue-test-001"},
        )

    intent = recv.receive_nowait()
    assert intent.intent_type == "request.pick"
    # PickRequested trägt keine dehydrated cross-BC-IDs — page_session_id ist None
    assert intent.page_session_id is None


# ---------------------------------------------------------------------------
# Happy-Path: AnnotationDraftSubmitted
# ---------------------------------------------------------------------------


@pytest.mark.anyio
async def test_annotation_draft_submitted_returns_202(
    frozen_clock: FrozenClock,
    intent_queue: tuple[MemoryObjectSendStream[IntentRequest], MemoryObjectReceiveStream[IntentRequest]],
    allowed_origins: frozenset[str],
) -> None:
    """POST AnnotationDraftSubmitted mit gültigem Origin → HTTP 202."""
    send, _recv = intent_queue
    cache = IdempotencyReplayCache(clock=frozen_clock)
    app = _build_app(send, cache, allowed_origins)

    async with httpx.AsyncClient(transport=httpx.ASGITransport(app=app), base_url="http://test") as client:
        resp = await client.post(
            "/mutations/",
            json=_annotation_body(),
            headers={"Origin": "http://localhost:7178", "Idempotency-Key": "annotation-001"},
        )

    assert resp.status_code == 202


@pytest.mark.anyio
async def test_annotation_draft_enqueues_notify_annotation_added(
    frozen_clock: FrozenClock,
    intent_queue: tuple[MemoryObjectSendStream[IntentRequest], MemoryObjectReceiveStream[IntentRequest]],
    allowed_origins: frozenset[str],
) -> None:
    """AnnotationDraftSubmitted → intent_type=notify.annotation_added."""
    send, recv = intent_queue
    cache = IdempotencyReplayCache(clock=frozen_clock)
    app = _build_app(send, cache, allowed_origins)

    async with httpx.AsyncClient(transport=httpx.ASGITransport(app=app), base_url="http://test") as client:
        await client.post(
            "/mutations/",
            json=_annotation_body(page_session_id="01HPAGE111111111111111111"),
            headers={"Origin": "http://127.0.0.1:7178", "Idempotency-Key": "annotation-enqueue-001"},
        )

    intent = recv.receive_nowait()
    assert intent.intent_type == "notify.annotation_added"
    assert intent.page_session_id == "01HPAGE111111111111111111"


# ---------------------------------------------------------------------------
# Idempotency-Replay
# ---------------------------------------------------------------------------


@pytest.mark.anyio
async def test_idempotency_replay_returns_same_response(
    frozen_clock: FrozenClock,
    intent_queue: tuple[MemoryObjectSendStream[IntentRequest], MemoryObjectReceiveStream[IntentRequest]],
    allowed_origins: frozenset[str],
) -> None:
    """Gleicher Idempotency-Key zweimal → gleiche Response, Queue erhält nur 1 IntentRequest."""
    send, recv = intent_queue
    cache = IdempotencyReplayCache(clock=frozen_clock)
    app = _build_app(send, cache, allowed_origins)

    headers = {"Origin": "http://127.0.0.1:7178", "Idempotency-Key": "replay-key-001"}
    body = _pick_requested_body()

    async with httpx.AsyncClient(transport=httpx.ASGITransport(app=app), base_url="http://test") as client:
        resp1 = await client.post("/mutations/", json=body, headers=headers)
        resp2 = await client.post("/mutations/", json=body, headers=headers)

    assert resp1.status_code == 202
    assert resp2.status_code == 202
    assert resp1.json()["idempotency_key"] == resp2.json()["idempotency_key"]

    # Queue darf nur 1 IntentRequest enthalten (zweiter POST war Replay)
    intent = recv.receive_nowait()
    assert intent.intent_type == "request.pick"
    with pytest.raises(anyio.WouldBlock):
        recv.receive_nowait()  # zweiter POST hat NICHT enqueued


@pytest.mark.anyio
async def test_idempotency_replay_after_ttl_expiry_re_enqueues(
    intent_queue: tuple[MemoryObjectSendStream[IntentRequest], MemoryObjectReceiveStream[IntentRequest]],
    allowed_origins: frozenset[str],
) -> None:
    """Nach TTL-Ablauf (FrozenClock vorwärtsbewegen) wird gleicher Key neu verarbeitet."""
    send, recv = intent_queue

    # Clock auf 0 starten
    clock = FrozenClock(monotonic_ns=0)
    cache = IdempotencyReplayCache(clock=clock)
    app = _build_app(send, cache, allowed_origins)

    headers = {"Origin": "http://127.0.0.1:7178", "Idempotency-Key": "ttl-expiry-key"}
    body = _pick_requested_body()

    async with httpx.AsyncClient(transport=httpx.ASGITransport(app=app), base_url="http://test") as client:
        # Erster POST — wird gecacht
        resp1 = await client.post("/mutations/", json=body, headers=headers)
        assert resp1.status_code == 202

        # Clock vorwärtsbewegen: TTL + 1 ns → expired
        clock.monotonic_ns = IDEMPOTENCY_TTL_NS + 1

        # Zweiter POST mit gleichem Key — Cache expired → neu verarbeitet
        resp2 = await client.post("/mutations/", json=body, headers=headers)
        assert resp2.status_code == 202

    # Queue enthält jetzt 2 IntentRequests (beide Posts haben enqueued)
    intent1 = recv.receive_nowait()
    intent2 = recv.receive_nowait()
    assert intent1.intent_type == "request.pick"
    assert intent2.intent_type == "request.pick"


# ---------------------------------------------------------------------------
# Origin-Check
# ---------------------------------------------------------------------------


@pytest.mark.anyio
async def test_unknown_origin_returns_403(
    frozen_clock: FrozenClock,
    intent_queue: tuple[MemoryObjectSendStream[IntentRequest], MemoryObjectReceiveStream[IntentRequest]],
    allowed_origins: frozenset[str],
) -> None:
    """Origin nicht in der Allowlist → HTTP 403."""
    send, recv = intent_queue
    cache = IdempotencyReplayCache(clock=frozen_clock)
    app = _build_app(send, cache, allowed_origins)

    async with httpx.AsyncClient(transport=httpx.ASGITransport(app=app), base_url="http://test") as client:
        resp = await client.post(
            "/mutations/",
            json=_pick_requested_body(),
            headers={"Origin": "http://evil.example.com", "Idempotency-Key": "evil-key"},
        )

    assert resp.status_code == 403
    assert resp.json()["error"] == "forbidden"

    # Queue darf leer sein
    with pytest.raises(anyio.WouldBlock):
        recv.receive_nowait()


@pytest.mark.anyio
async def test_missing_origin_returns_403(
    frozen_clock: FrozenClock,
    intent_queue: tuple[MemoryObjectSendStream[IntentRequest], MemoryObjectReceiveStream[IntentRequest]],
    allowed_origins: frozenset[str],
) -> None:
    """Kein Origin-Header → HTTP 403 (leerer String nicht in Allowlist)."""
    send, _recv = intent_queue
    cache = IdempotencyReplayCache(clock=frozen_clock)
    app = _build_app(send, cache, allowed_origins)

    async with httpx.AsyncClient(transport=httpx.ASGITransport(app=app), base_url="http://test") as client:
        resp = await client.post(
            "/mutations/",
            json=_pick_requested_body(),
            headers={"Idempotency-Key": "no-origin-key"},
        )

    assert resp.status_code == 403


# ---------------------------------------------------------------------------
# Fehler-Fälle
# ---------------------------------------------------------------------------


@pytest.mark.anyio
async def test_missing_idempotency_key_returns_400(
    frozen_clock: FrozenClock,
    intent_queue: tuple[MemoryObjectSendStream[IntentRequest], MemoryObjectReceiveStream[IntentRequest]],
    allowed_origins: frozenset[str],
) -> None:
    """Kein Idempotency-Key Header → HTTP 400."""
    send, _recv = intent_queue
    cache = IdempotencyReplayCache(clock=frozen_clock)
    app = _build_app(send, cache, allowed_origins)

    async with httpx.AsyncClient(transport=httpx.ASGITransport(app=app), base_url="http://test") as client:
        resp = await client.post(
            "/mutations/",
            json=_pick_requested_body(),
            headers={"Origin": "http://127.0.0.1:7178"},
        )

    assert resp.status_code == 400
    assert "Idempotency-Key" in resp.json()["error"]


@pytest.mark.anyio
async def test_invalid_json_body_returns_400(
    frozen_clock: FrozenClock,
    intent_queue: tuple[MemoryObjectSendStream[IntentRequest], MemoryObjectReceiveStream[IntentRequest]],
    allowed_origins: frozenset[str],
) -> None:
    """Kein valides JSON → HTTP 400."""
    send, _recv = intent_queue
    cache = IdempotencyReplayCache(clock=frozen_clock)
    app = _build_app(send, cache, allowed_origins)

    async with httpx.AsyncClient(transport=httpx.ASGITransport(app=app), base_url="http://test") as client:
        resp = await client.post(
            "/mutations/",
            content=b"not-json",
            headers={
                "Origin": "http://127.0.0.1:7178",
                "Idempotency-Key": "bad-json-key",
                "Content-Type": "application/json",
            },
        )

    assert resp.status_code == 400


@pytest.mark.anyio
async def test_invalid_mutation_type_returns_422(
    frozen_clock: FrozenClock,
    intent_queue: tuple[MemoryObjectSendStream[IntentRequest], MemoryObjectReceiveStream[IntentRequest]],
    allowed_origins: frozenset[str],
) -> None:
    """Unbekannter type-Discriminator → HTTP 422 (Pydantic ValidationError)."""
    send, _recv = intent_queue
    cache = IdempotencyReplayCache(clock=frozen_clock)
    app = _build_app(send, cache, allowed_origins)

    async with httpx.AsyncClient(transport=httpx.ASGITransport(app=app), base_url="http://test") as client:
        resp = await client.post(
            "/mutations/",
            json={"type": "UnknownMutation", "payload": {}},
            headers={"Origin": "http://127.0.0.1:7178", "Idempotency-Key": "unknown-type-key"},
        )

    assert resp.status_code == 422
    assert resp.json()["error"] == "validation failed"


# ---------------------------------------------------------------------------
# IdempotencyReplayCache — Unit-Tests (synchron)
# ---------------------------------------------------------------------------


def test_cache_lookup_returns_none_for_unknown_key() -> None:
    clock = FrozenClock(monotonic_ns=0)
    cache = IdempotencyReplayCache(clock=clock)
    assert cache.lookup(IdempotencyKey("nonexistent")) is None


def test_cache_store_and_lookup_roundtrip() -> None:
    clock = FrozenClock(monotonic_ns=0)
    cache = IdempotencyReplayCache(clock=clock)
    key = IdempotencyKey("roundtrip-key")
    response = CachedResponse(
        snapshot=MonotonicSnapshot(value=0),
        status_code=202,
        body={"idempotency_key": "roundtrip-key", "accepted": True},
    )
    cache.store(key, response)
    result = cache.lookup(key)
    assert result is not None
    assert result.status_code == 202


def test_cache_evicts_on_ttl_expiry() -> None:
    clock = FrozenClock(monotonic_ns=0)
    cache = IdempotencyReplayCache(clock=clock)
    key = IdempotencyKey("evict-key")
    cache.store(
        key,
        CachedResponse(
            snapshot=MonotonicSnapshot(value=0),
            status_code=202,
            body={},
        ),
    )
    assert cache.size() == 1

    # TTL überschreiten
    clock.monotonic_ns = IDEMPOTENCY_TTL_NS + 1
    assert cache.lookup(key) is None
    assert cache.size() == 0


def test_cache_does_not_evict_before_ttl() -> None:
    clock = FrozenClock(monotonic_ns=0)
    cache = IdempotencyReplayCache(clock=clock)
    key = IdempotencyKey("no-evict-key")
    cache.store(
        key,
        CachedResponse(
            snapshot=MonotonicSnapshot(value=0),
            status_code=202,
            body={},
        ),
    )
    # Genau an der TTL-Grenze (strict >): noch nicht expired
    clock.monotonic_ns = IDEMPOTENCY_TTL_NS
    assert cache.lookup(key) is not None
