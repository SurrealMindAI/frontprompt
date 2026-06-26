"""Recording wire types — SSoT for the frontprompt-recorder-replay and
frontprompt-voice-over bundles.

Diese Datei ist der SSoT für die Recording-feature Wire-Typen. Sie re-exportiert
die Pydantic-Modelle aus :mod:`frontprompt.state.state` und :mod:`frontprompt.bridge.messages`
die für die Replay- und Voice-Over-Bundles relevant sind.

Codegen
=======
``pydantic-zod-codegen generate frontprompt.wire --output <output>.gen.ts``

Das Goldenfile liegt unter ``tests/goldenfile/wire-events.gen.ts``. CI-Gate:

    uv run pytest -m drift

Lokaler Regen:

    uv run pydantic-zod-codegen generate frontprompt.wire \\
        --output tests/goldenfile/wire-events.gen.ts

Drift = Wire-Typen in state.py/messages.py verändert, Goldenfile nicht regeneriert.

Scope
=====
Wire = was über den bridge-Kanal (expose_function + page.evaluate) geht und
was die downstream-Bundles (recorder-replay, voice-over) konsumieren müssen.

Inbound Recording-Messages (Overlay → Python):
    :class:`RecordingStartRequested`        Neue Aufnahme beginnen.
    :class:`RecordingStopRequested`         Aktive Aufnahme beenden.
    :class:`RecordingRenameRequested`       Name/Beschreibung patchen.
    :class:`RecordingSelectedRequested`     Detail-Selektion (oder deselect).
    :class:`RecordedEventCapturedRequested` Page-Event während aktiver Aufnahme.

Timeline-Entry-Varianten:
    :class:`PageEventEntry`     Page-Interaktion (click/pointerdown/keydown).
    :class:`PickRefEntry`       Referenz auf einen erstellten Pick.
    :class:`RegionRefEntry`     Referenz auf eine gezeichnete Region.
    :class:`RelationRefEntry`   Referenz auf eine erstellte Relation.
    :class:`NavigationEntry`    Page-Navigation (Python-seitig erfasst).
    :data:`TimelineEntry`       Discriminated union aller Entry-Typen.

State-Typen:
    :class:`RecordingMeta`      Lightweight summary (für Listen-Ansicht).
    :class:`Recording`          Vollständiges Aggregat mit Timeline.
    :class:`RecordingsState`    Gesamter Recording-State (StateSnapshot-Feld).
"""

from __future__ import annotations

# Re-exports from state SSoT — intentional, no duplication
from frontprompt.state.state import (
    NavigationEntry,
    PageEventEntry,
    PickRefEntry,
    Recording,
    RecordingMeta,
    RecordingsState,
    RecordingStatus,
    RegionRefEntry,
    RelationRefEntry,
    TimelineEntry,
    TimelineEntryKind,
)

# Re-exports from bridge messages SSoT
from frontprompt.bridge.messages import (
    RecordedEventCapturedRequested,
    RecordingRenameRequested,
    RecordingSelectedRequested,
    RecordingStartRequested,
    RecordingStopRequested,
)

# ============================================================================
# Codegen roots — what gets emitted to TypeScript
# ============================================================================
#
# pydantic-zod-codegen reads this list and emits TS types for each entry.
# Order controls the output order in the generated file.

__codegen_roots__ = [
    # Recording status + entry kind discriminators
    "RecordingStatus",
    "TimelineEntryKind",
    # Timeline entry variants (individual concrete types)
    "PageEventEntry",
    "PickRefEntry",
    "RegionRefEntry",
    "RelationRefEntry",
    "NavigationEntry",
    # TimelineEntry discriminated union
    "TimelineEntry",
    # Recording domain aggregates
    "RecordingMeta",
    "Recording",
    "RecordingsState",
    # Outbound bridge messages (Overlay → Python) for recording feature
    "RecordingStartRequested",
    "RecordingStopRequested",
    "RecordingRenameRequested",
    "RecordingSelectedRequested",
    "RecordedEventCapturedRequested",
]

__all__ = [
    # State types
    "NavigationEntry",
    "PageEventEntry",
    "PickRefEntry",
    "Recording",
    "RecordingMeta",
    "RecordingsState",
    "RecordingStatus",
    "RegionRefEntry",
    "RelationRefEntry",
    "TimelineEntry",
    "TimelineEntryKind",
    # Bridge messages
    "RecordedEventCapturedRequested",
    "RecordingRenameRequested",
    "RecordingSelectedRequested",
    "RecordingStartRequested",
    "RecordingStopRequested",
]
