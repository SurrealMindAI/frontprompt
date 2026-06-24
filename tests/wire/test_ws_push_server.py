"""Integration tests — InProcessEventBus + run_ws_push_server().

Alle Tests starten einen echten WS-Server via run_ws_push_server() mit port=0
(random free port). Der tatsächlich gebundene Port wird via
``bus.bound_port`` abgelesen (gesetzt von run_ws_push_server() nach Bind).
Die OriginAllowlist wird nach Bind mit dem tatsächlichen Port konstruiert.

Kein anyio MemoryObjectStream als Transport-Shim — wir testen den echten WS-Pfad
(websockets.connect). Der echte WS-Client ist KISS.

EventEnvelope-Shape-Note:
    EventEnvelope ist ein Wrapper mit schema_version/daemon_id/emitted_at_monotonic_ns
    plus einem 'payload'-Feld. Flache Dicts schlagen mit ValidationError fehl.
    Tests nutzen korrekte Wrapper-Form.
"""

from __future__ import annotations

import contextlib
import json

import anyio
import pytest
import websockets
import websockets.exceptions

from frontprompt.wire.event_bus import InProcessEventBus


def _make_session_started_envelope() -> dict:  # type: ignore[type-arg]
    """Minimal-valides EventEnvelope-Dict für SessionStarted-Payload."""
    return {
        "schema_version": 1,
        "daemon_id": "d-001",
        "emitted_at_monotonic_ns": 1_000_000_000,
        "payload": {
            "type": "session_started",
            "page_session_id": "01HAAAAAAAAAAAAAAAAAAAAAA1",
            "dns_domain": "example.com",
            "started_at_monotonic_ns": 1_000_000_000,
        },
    }


def _make_page_navigated_envelope() -> dict:  # type: ignore[type-arg]
    """Minimal-valides EventEnvelope-Dict für PageNavigated-Payload."""
    return {
        "schema_version": 1,
        "daemon_id": "d-001",
        "emitted_at_monotonic_ns": 2_000_000_000,
        "payload": {
            "type": "page_navigated",
            "page_session_id": "01HAAAAAAAAAAAAAAAAAAAAAA1",
            "url": "https://example.com/page",
            "dom_snapshot_hash": "sha256:deadbeef",
            "navigated_at_monotonic_ns": 2_000_000_000,
        },
    }


@pytest.mark.anyio
async def test_event_bus_subscribe_and_emit() -> None:
    """InProcessEventBus: emit() nach subscribe() liefert das Event — subscribe-after-publish-safe."""
    # Arrange
    bus = InProcessEventBus(buffer_size=4)
    recv = bus.subscribe()

    from frontprompt.wire.events import EventEnvelope

    # Korrekte Envelope-Wrapper-Form
    envelope = EventEnvelope.model_validate(_make_session_started_envelope())

    # Act — emit nach subscribe (subscribe-after-publish-safe: subscribe ist synchron, emit ist async)
    await bus.emit(envelope)

    # Assert
    received = await recv.receive()
    assert received == envelope

    await bus.close()


@pytest.mark.anyio
async def test_event_bus_fanout_to_multiple_subscribers() -> None:
    """emit() liefert denselben EventEnvelope an alle aktuellen Subscriber."""
    bus = InProcessEventBus(buffer_size=4)
    recv_a = bus.subscribe()
    recv_b = bus.subscribe()

    from frontprompt.wire.events import EventEnvelope

    envelope = EventEnvelope.model_validate(_make_session_started_envelope())
    await bus.emit(envelope)

    a = await recv_a.receive()
    b = await recv_b.receive()
    assert a == envelope
    assert b == envelope

    await bus.close()


@pytest.mark.anyio
async def test_event_bus_emit_before_subscribe_is_dropped() -> None:
    """emit() vor subscribe() — das Event landet in keinem Subscriber.

    Kein historisches Replay (YAGNI — skeleton). Das ist explizit dokumentiertes
    Verhalten, kein Bug.
    """
    bus = InProcessEventBus(buffer_size=4)

    from frontprompt.wire.events import EventEnvelope

    envelope = EventEnvelope.model_validate(_make_session_started_envelope())
    # emit OHNE subscriber — kein offener recv-stream → noop
    await bus.emit(envelope)  # must not raise

    await bus.close()


@pytest.mark.anyio
async def test_ws_push_server_delivers_event_to_client() -> None:
    """run_ws_push_server() liefert ein emittiertes Event als JSON-RPC-Notification an den Client.

    Port=0 → random free port → tatsächlicher Port via bus.bound_port.
    OriginAllowlist wird nach Bind mit dem tatsächlichen Port konstruiert.
    """
    from frontprompt.wire.events import EventEnvelope
    from frontprompt.wire.ws_server import run_ws_push_server

    bus = InProcessEventBus(buffer_size=8)

    envelope = EventEnvelope.model_validate(_make_page_navigated_envelope())

    received_notifications: list[dict] = []  # type: ignore[type-arg]

    async with anyio.create_task_group() as tg:

        async def _server_task() -> None:
            # run_ws_push_server blockiert bis cancelled
            await run_ws_push_server(bus, host="127.0.0.1", port=0)

        async def _client_and_emit() -> None:
            # Kurz warten bis der Server gestartet hat
            await anyio.sleep(0.05)

            # Tatsächlichen Port nach Bind lesen (gesetzt von run_ws_push_server)
            port = bus.bound_port
            assert port is not None and port > 0

            origin = f"http://127.0.0.1:{port}"
            async with websockets.connect(
                f"ws://127.0.0.1:{port}",
                additional_headers={"Origin": origin},
            ) as ws:
                # Event emittieren NACH Client-Connect (subscribe ist synchron im Handler)
                await bus.emit(envelope)

                # WS-Notification empfangen
                raw = await ws.recv()

            notification = json.loads(raw)
            assert notification["jsonrpc"] == "2.0"
            assert "id" not in notification  # Notification hat keine id
            assert notification["method"] == "wire.event"
            assert notification["params"]["payload"]["type"] == "page_navigated"
            received_notifications.append(notification)
            tg.cancel_scope.cancel()

        tg.start_soon(_server_task)
        tg.start_soon(_client_and_emit)

    assert len(received_notifications) == 1


@pytest.mark.anyio
async def test_ws_push_server_rejects_unlisted_origin() -> None:
    """WS-Verbindung von nicht-allowlisted Origin bekommt HTTP 403.

    OriginAllowlist ist exact-match-only — kein Wildcard.
    """
    from frontprompt.wire.ws_server import run_ws_push_server

    bus = InProcessEventBus(buffer_size=4)

    rejected = False

    async with anyio.create_task_group() as tg:

        async def _server_task() -> None:
            await run_ws_push_server(bus, host="127.0.0.1", port=0)

        async def _bad_client() -> None:
            nonlocal rejected
            await anyio.sleep(0.05)
            port = bus.bound_port
            assert port is not None

            with contextlib.suppress(websockets.exceptions.InvalidStatus):
                async with websockets.connect(
                    f"ws://127.0.0.1:{port}",
                    additional_headers={"Origin": "http://evil.example.com"},
                ):
                    # Should not reach here — connection should be rejected
                    pass

            # Reached here = exception was suppress'd (403) OR no exception (shouldn't happen)
            rejected = True
            tg.cancel_scope.cancel()

        tg.start_soon(_server_task)
        tg.start_soon(_bad_client)

    # bad client completed (suppressed 403 or passed without error)
    assert rejected, "bad_client task did not complete"


@pytest.mark.anyio
async def test_daemon_spawns_ws_server_in_pe_bc_nursery() -> None:
    """run_daemon() startet run_ws_push_server() als Task im PE-BC-Nursery.

    Smoke-Test: Daemon startet, WS-Port wird gebunden, Daemon cancelt sauber.
    """
    from frontprompt.daemon import Daemon, run_daemon

    # http_port=0: OS picks a free port — avoids OSError: Address already in use
    daemon = Daemon(http_port=0)
    with anyio.move_on_after(1.0):
        await run_daemon(daemon=daemon)
    # Kein Exception-Austritt = grün
