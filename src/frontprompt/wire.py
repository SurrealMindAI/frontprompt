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

Replay-Assertion-Authoring (Overlay → Python, Schema 0.9.0):
    :class:`AssertionAddedToRecordingRequested` Assertion zur Aufnahme hinzufügen.
    :class:`AssertionDeletedRequested`          Assertion aus Aufnahme entfernen.
    :class:`AssertionUpdatedRequested`          Assertion-Felder patchen.

Voice-Over-Mutations (Overlay → Python, Schema 0.10.0):
    :class:`SetMicDeviceRequested`              User-gewähltes Mikrofon setzen.
    :class:`SetTranscriptionBackendRequested`   User-gewähltes Backend setzen.
    :class:`TriggerModelDownloadRequested`      Modell-Download starten.

Transcription-Model-Selection (Overlay → Python, Schema 0.11.0):
    :class:`SetTranscriptionModelRequested`     User-gewähltes Modell für ein Backend setzen.

Timeline-Entry-Varianten:
    :class:`PageEventEntry`         Page-Interaktion (click/pointerdown/keydown).
    :class:`PickRefEntry`           Referenz auf einen erstellten Pick.
    :class:`RegionRefEntry`         Referenz auf eine gezeichnete Region.
    :class:`RelationRefEntry`       Referenz auf eine erstellte Relation.
    :class:`NavigationEntry`        Page-Navigation (Python-seitig erfasst).
    :class:`AssertionEntry`         Assertion-Checkpoint (replay sub-plan 01).
    :class:`TranscriptSegmentEntry` Transkribiertes Sprachsegment (voice-over sub-plan 01).
    :data:`TimelineEntry`           Discriminated union aller Entry-Typen.

State-Typen:
    :class:`RecordingMeta`      Lightweight summary (für Listen-Ansicht).
    :class:`Recording`          Vollständiges Aggregat mit Timeline.
    :class:`RecordingsState`    Gesamter Recording-State (StateSnapshot-Feld).

Replay-State-Typen (sub-plan 01/02):
    :class:`ParameterDeclaration`   Parameter-Deklaration auf Recording.
    :data:`AssertionType`           Assertion-Art-Discriminator.
    :data:`AssertionComparator`     Vergleichsoperator.
    :data:`ReplayStatus`            Replay-Abschluss-Status.
    :class:`ReplayStepResult`       Per-Step-Ergebnis im ReplayReport.
    :class:`ReplayReport`           Vollständiges Replay-Ergebnis.
    :class:`ReplayProgress`         Lightweight Progress-Snapshot (live im State).

Voice-Over-State-Typen (sub-plan 01):
    :class:`MicrophoneDevice`           Ein einzelnes Eingabegerät.
    :class:`MicrophoneState`            Mikrofon-Enumeration + User-Präferenz.
    :class:`SettingsState`              Dauerhafte Voice-Over-Einstellungen.
    :data:`TranscriptionBackendStatus`  Verfügbarkeitsstatus eines Backends.
    :class:`TranscriptionBackendInfo`   Status-Info pro Backend (inkl. Download-Progress).
    :class:`TranscriptionState`         Aggregierter Status aller Backends.
    :data:`TranscriptionStatus`         Transkriptions-Status einer Recording.

Transcription-Model-Catalog-Typen (voiceover-models sub-plan 01):
    :class:`TranscriptionModelSpec`     Statischer Katalog-Eintrag (model_id, display_name, hf_repo_id, default).
"""

from __future__ import annotations

# Re-exports from state SSoT — intentional, no duplication
from frontprompt.state.state import (
    AssertionComparator,
    AssertionEntry,
    AssertionType,
    MicrophoneDevice,
    MicrophoneState,
    NavigationEntry,
    PageEventEntry,
    ParameterDeclaration,
    PickRefEntry,
    Recording,
    RecordingMeta,
    RecordingsState,
    RecordingStatus,
    RegionRefEntry,
    RelationRefEntry,
    ReplayProgress,
    ReplayReport,
    ReplayStatus,
    ReplayStepResult,
    SettingsState,
    TimelineEntry,
    TimelineEntryKind,
    TranscriptionBackendInfo,
    TranscriptionBackendStatus,
    TranscriptionModelSpec,
    TranscriptionState,
    TranscriptSegmentEntry,
    TranscriptionStatus,
)

# Re-exports from bridge messages SSoT
from frontprompt.bridge.messages import (
    AssertionAddedToRecordingRequested,
    AssertionDeletedRequested,
    AssertionUpdatedRequested,
    RecordedEventCapturedRequested,
    RecordingRenameRequested,
    RecordingSelectedRequested,
    RecordingStartRequested,
    RecordingStopRequested,
    SetMicDeviceRequested,
    SetTranscriptionBackendRequested,
    SetTranscriptionModelRequested,
    TriggerModelDownloadRequested,
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
    # Assertion entry variant (replay sub-plan 01)
    "AssertionType",
    "AssertionComparator",
    "AssertionEntry",
    # Voice-over timeline entry variant (voice-over sub-plan 01)
    "TranscriptSegmentEntry",
    # TimelineEntry discriminated union
    "TimelineEntry",
    # Recording domain aggregates
    "RecordingMeta",
    "ParameterDeclaration",
    "Recording",
    # Replay state types (sub-plan 01)
    "ReplayStatus",
    "ReplayStepResult",
    "ReplayProgress",
    "RecordingsState",
    # Voice-over state types (voice-over sub-plan 01)
    "TranscriptionStatus",
    "MicrophoneDevice",
    "MicrophoneState",
    "SettingsState",
    "TranscriptionBackendStatus",
    "TranscriptionBackendInfo",
    "TranscriptionState",
    # Transcription-Model-Catalog (voiceover-models sub-plan 01)
    "TranscriptionModelSpec",
    # Outbound bridge messages (Overlay → Python) for recording feature
    "RecordingStartRequested",
    "RecordingStopRequested",
    "RecordingRenameRequested",
    "RecordingSelectedRequested",
    "RecordedEventCapturedRequested",
    # Outbound bridge messages — Replay-Assertion-Authoring (Schema 0.9.0)
    "AssertionAddedToRecordingRequested",
    "AssertionDeletedRequested",
    "AssertionUpdatedRequested",
    # Outbound bridge messages — Voice-Over-Mutations (Schema 0.10.0)
    "SetMicDeviceRequested",
    "SetTranscriptionBackendRequested",
    "TriggerModelDownloadRequested",
    # Outbound bridge messages — Transcription-Model-Selection (Schema 0.11.0)
    "SetTranscriptionModelRequested",
]

__all__ = [
    # State types — core
    "AssertionComparator",
    "AssertionEntry",
    "AssertionType",
    "NavigationEntry",
    "PageEventEntry",
    "ParameterDeclaration",
    "PickRefEntry",
    "Recording",
    "RecordingMeta",
    "RecordingsState",
    "RecordingStatus",
    "RegionRefEntry",
    "RelationRefEntry",
    "ReplayProgress",
    "ReplayReport",
    "ReplayStatus",
    "ReplayStepResult",
    "TimelineEntry",
    "TimelineEntryKind",
    # State types — voice-over (Schema 0.10.0)
    "MicrophoneDevice",
    "MicrophoneState",
    "SettingsState",
    "TranscriptionBackendInfo",
    "TranscriptionBackendStatus",
    "TranscriptionModelSpec",
    "TranscriptionState",
    "TranscriptSegmentEntry",
    "TranscriptionStatus",
    # Bridge messages — Recording
    "RecordedEventCapturedRequested",
    "RecordingRenameRequested",
    "RecordingSelectedRequested",
    "RecordingStartRequested",
    "RecordingStopRequested",
    # Bridge messages — Replay-Assertion-Authoring (Schema 0.9.0)
    "AssertionAddedToRecordingRequested",
    "AssertionDeletedRequested",
    "AssertionUpdatedRequested",
    # Bridge messages — Voice-Over-Mutations (Schema 0.10.0)
    "SetMicDeviceRequested",
    "SetTranscriptionBackendRequested",
    "TriggerModelDownloadRequested",
    # Bridge messages — Transcription-Model-Selection (Schema 0.11.0)
    "SetTranscriptionModelRequested",
]
