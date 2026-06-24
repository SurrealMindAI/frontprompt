"""InProcessEventBus — anyio MemoryObjectStream-backed pub/sub für EventEnvelope.

Design-Constraints (alle Hard-Constraints aus dem Sub-Plan-Briefing):

* subscribe() ist **synchron** — verhindert subscribe-after-emit-Race.
  subscribe() vor dem ersten await-Checkpoint aufgerufen = Garantie dass kein
  Event verpasst wird das zwischen subscribe() und dem ersten recv() emittiert wird.
  (MemoryObjectReceiveStream puffert bis buffer_size.)

* emit() ist **async** — fan-out über alle aktuell offenen MemoryObjectReceiveStreams.
  Streams die zwischen emit()-Calls geschlossen werden (Client disconnect) werden
  aus der internen Liste entfernt.

* Kein historisches Replay (YAGNI — skeleton). Events die vor dem ersten subscribe()
  emittiert werden sind verloren. Aggregate-Bundles müssen selbst sicherstellen dass
  sie subscribe() vor dem ersten emit() aufrufen (via PE-BC-Nursery-Reihenfolge).

* anyio.create_memory_object_stream Generic-Subscript-Syntax (anyio 4.0+):
  ``anyio.create_memory_object_stream[EventEnvelope](max_buffer_size=N)``

* Keine asyncio.Lock / threading.Lock (single-writer). State (subscriber-Liste) ist
  exklusiv im PE-BC-Nursery-Task-Group-Kontext — kein shared mutable state über
  Task-Group-Grenzen hinweg.

Naming-Konvention: Alle Felder sind domain-qualified (``event_bus``, ``buffer_size``).
"""

from __future__ import annotations

import anyio
from anyio.streams.memory import MemoryObjectReceiveStream, MemoryObjectSendStream

from frontprompt.wire.events import EventEnvelope


class InProcessEventBus:
    """Fan-out pub/sub für EventEnvelope-Objekte innerhalb des Daemon-Prozesses.

    Jeder Aufruf von subscribe() gibt einen frischen MemoryObjectReceiveStream zurück.
    emit() sendet das Envelope in alle offenen Streams gleichzeitig (sequenziell,
    kein echter Parallelismus nötig — anyio-Backpressure per Stream).

    ``bound_port`` wird von run_ws_push_server() nach erfolgreichem Bind gesetzt.
    Test-Fixtures lesen diesen Wert um die tatsächliche WS-URL zu konstruieren.
    """

    def __init__(self, buffer_size: int = 256) -> None:
        if buffer_size <= 0:
            raise ValueError(f"buffer_size must be > 0, got {buffer_size!r}")
        self._buffer_size = buffer_size
        self._send_streams: list[MemoryObjectSendStream[EventEnvelope]] = []
        # Gesetzt von run_ws_push_server() nach erfolgreichem Bind.
        # None = Server noch nicht gestartet oder port=bekannter Port.
        self.bound_port: int | None = None

    def subscribe(self) -> MemoryObjectReceiveStream[EventEnvelope]:
        """Registriert einen neuen Subscriber und gibt seinen Receive-Stream zurück.

        **Muss synchron, vor dem ersten emit()-Call aufgerufen werden** (subscribe-after-publish race).
        Der zurückgegebene Stream ist exklusiver Besitz des Callers — dieser ist
        dafür verantwortlich ihn zu schließen (via ``async with recv_stream:``).
        """
        send, recv = anyio.create_memory_object_stream[EventEnvelope](
            max_buffer_size=self._buffer_size,
        )
        self._send_streams.append(send)
        return recv

    async def emit(self, envelope: EventEnvelope) -> None:
        """Sendet envelope an alle aktuell registrierten Subscriber.

        Subscriber die ihren Receive-Stream geschlossen haben werden aus der
        internen Liste entfernt (ClosedResourceError beim Send = Stream ist tot).

        Kein await-Checkpoint zwischen den einzelnen sends — KISS. Wenn ein
        Subscriber seinen Buffer gefüllt hat, blockiert emit() für diesen Stream
        bis Platz frei wird (anyio backpressure). Das ist akzeptiertes Verhalten:
        ein langsamer Client bremst den Daemon. Zukünftige Bundles können hier
        ein ``move_on_after`` einbauen wenn das ein Problem wird (YAGNI).

        Args:
            envelope: Das zu sendende EventEnvelope (discriminated union).
        """
        dead: list[int] = []
        for idx, send in enumerate(self._send_streams):
            try:
                await send.send(envelope)
            except (anyio.ClosedResourceError, anyio.BrokenResourceError):
                dead.append(idx)
        # Tote Streams rückwärts entfernen (Index-Stabilität)
        for idx in reversed(dead):
            self._send_streams.pop(idx)

    async def close(self) -> None:
        """Schließt alle Send-Streams — Subscriber erhalten EndOfStream."""
        for send in self._send_streams:
            await send.aclose()
        self._send_streams.clear()
