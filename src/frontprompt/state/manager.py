"""StateManager — single-writer aggregate für backend-authoritative state.

Single-writer: nur diese class mutiert state. Mutations via async
methods sind anyio-lock-guarded (belt-and-suspenders gegen accidental
concurrent calls aus mehreren task-group-children).

State classification: aggregat-root für alle backend-state-felder.

Panel + inspector state, persisted via the injected StatePersistence (SQLite on
disk, or InMemoryPersistence no-op). Phase 2+: annotations beyond comment,
adaptive scrapling-relocate on cross-origin nav.
"""

from __future__ import annotations

import time
import uuid
from collections.abc import Awaitable, Callable

import anyio
import structlog

from frontprompt.state.persistence import InMemoryPersistence, StatePersistence
from frontprompt.state.state import (
    PANEL_IDS,
    AssertionEntry,
    HostnameGroup,
    InspectorState,
    MicrophoneDevice,
    MicrophoneState,
    NavigationEntry,
    OriginSessionGroup,
    OwnedVsForeign,
    PageEventEntry,
    PanelId,
    PanelStateView,
    PanelView,
    ParameterDeclaration,
    Pick,
    PickRefEntry,
    Recording,
    RecordingMeta,
    RecordingsState,
    Region,
    RegionRefEntry,
    Relation,
    RelationKind,
    RelationRefEntry,
    ReplayProgress,
    ReplayReport,
    ReplayReportMeta,
    SettingsState,
    StateSnapshot,
    StateSummary,
    SummaryCounts,
    TimelineEntry,
    TranscriptSegmentEntry,
    TranscriptionBackendStatus,
    TranscriptionState,
    hostname_for_url,
)

_LOG = structlog.get_logger(__name__)

#: Default panel-sizes wenn keine persisted state da ist.
_DEFAULT_PANEL_SIZES: dict[PanelId, int] = {
    "top": 56,
    "bottom": 220,
    "left": 300,
    "right": 340,
}

#: Min/max constraints für resize-clamping.
_PANEL_SIZE_LIMITS: dict[PanelId, tuple[int, int]] = {
    "top": (40, 400),
    "bottom": (80, 500),
    "left": (200, 600),
    "right": (200, 600),
}


def _default_panel_state() -> PanelStateView:
    """Build default panel state.

    Top/Left/Right open. Bottom default closed — der DebugPanel ist
    diagnostics-content (state-snapshot dump etc), on-demand erwünscht,
    nicht standard-sichtbar (User-Mandate).
    """
    return PanelStateView(
        top=PanelView(open=True, size=_DEFAULT_PANEL_SIZES["top"]),
        bottom=PanelView(open=False, size=_DEFAULT_PANEL_SIZES["bottom"]),
        left=PanelView(open=True, size=_DEFAULT_PANEL_SIZES["left"]),
        right=PanelView(open=True, size=_DEFAULT_PANEL_SIZES["right"]),
    )


def _clamp_size(panel_id: PanelId, size: int) -> int:
    """Clamp size to [min, max] per panel."""
    lo, hi = _PANEL_SIZE_LIMITS[panel_id]
    return max(lo, min(hi, size))


SnapshotListener = Callable[[StateSnapshot], Awaitable[None] | None]


def _relation_involves_pick(relation: Relation, pick_id: str) -> bool:
    """True wenn die Relation den pick als source ODER target hat (kind=pick)."""
    if relation.source_kind == "pick" and relation.source_id == pick_id:
        return True
    if relation.target_kind == "pick" and relation.target_id == pick_id:
        return True
    return False


def _relation_involves_region(relation: Relation, region_id: str) -> bool:
    """True wenn die Relation die region als source ODER target hat (kind=region)."""
    if relation.source_kind == "region" and relation.source_id == region_id:
        return True
    if relation.target_kind == "region" and relation.target_id == region_id:
        return True
    return False


class StateManager:
    """Single-writer aggregate für backend-authoritative state.

    Lifecycle ist process-scoped: lebt mit dem Python-process. Panel- UND
    inspector-state werden via der injizierten :class:`StatePersistence`
    geladen (init) und gespeichert (post-mutate). Mit
    :class:`InMemoryPersistence` ist das ein no-op; mit
    :class:`SqlitePersistence` landet alles auf disk.

    ``session_id`` ist die provenance-identity dieser session: jede add/update-
    mutation stempelt ``entity.origin_session = session_id`` (steal-on-mutate).

    Mutations (Panel):
        - :meth:`toggle_panel(panel_id)` — flip open
        - :meth:`resize_panel(panel_id, new_size)` — set size (clamped)
        - :meth:`set_all_panels_open(open_state)` — bulk

    Mutations (Inspector):
        - :meth:`set_inspector_active(active)` — activate/cancel inspector mode
        - :meth:`add_pick(pick)` — atomic: append + set active_pick_id + clear active
        - :meth:`select_pick(pick_id)` — re-select existing pick
        - :meth:`update_pick_comment(pick_id, comment)` — patch comment
        - :meth:`delete_pick(pick_id)` — remove + cascade-drop relations + region-member-cleanup

    Mutations (Regions, Schema 0.4.0):
        - :meth:`add_region(region)` — last-write-wins by region_id, filters unknown members
        - :meth:`delete_region(region_id)` — cascade-drops relations involving region
        - :meth:`update_region(region_id, note)` — patch note
        - :meth:`select_region(region_id)` — set active_region_id, clears active_pick_id

    Mutations (Relations):
        - :meth:`add_relation(relation)` — last-write-wins by relation_id, validates heterogeneous endpoints
        - :meth:`delete_relation(relation_id)` — idempotent
        - :meth:`update_relation(relation_id, kind, note)` — replaces both fields atomically

    Read:
        - :meth:`snapshot()` — returns immutable copy für wire-send (incl. inspector)

    Subscribers (z.B. CLI für broadcast-on-mutation):
        - :meth:`add_snapshot_listener(fn)` → unsubscribe-callable
    """

    def __init__(
        self,
        *,
        session_id: str,
        persistence: StatePersistence | None = None,
        transcription_state: TranscriptionState | None = None,
    ) -> None:
        self._session_id = session_id
        self._persistence = persistence or InMemoryPersistence()
        self._log = _LOG.bind(component="StateManager", session_id=session_id)
        self._lock = anyio.Lock()
        self._panel_state: PanelStateView = self._load_panel_or_default()
        self._inspector_state: InspectorState = self._load_inspector_or_default()
        self._listeners: list[SnapshotListener] = []
        # Recording domain (sub-plan 01)
        # _full_recordings: in-memory store for full Recording objects (with entries).
        # _recordings_state: snapshot-ready lightweight state (RecordingMeta list, no entries).
        # COL-2: snapshot() MUST include _recordings_state; see snapshot() implementation.
        self._full_recordings: dict[str, Recording] = {}
        self._recordings_state: RecordingsState = self._load_recordings_or_default()
        # Voice-over domain (voice-over sub-plan 01)
        # _microphone_state: in-process device list + selection, populated by MicWatcher.
        # _settings_state: durable user prefs (voice_over_enabled, backend selection).
        # _transcription_state: backend availability + download progress; injected by caller
        #   (StateManager is infrastructure-agnostic — it never probes hardware directly).
        # _microphone_topology_hash: snapshot of device IDs to skip no-op broadcasts.
        self._microphone_state: MicrophoneState = self._load_microphone_or_default()
        self._settings_state: SettingsState = self._load_settings_or_default()
        self._transcription_state: TranscriptionState = transcription_state or TranscriptionState()
        self._microphone_topology_hash: frozenset[int] = frozenset()

    def _load_panel_or_default(self) -> PanelStateView:
        loaded = self._persistence.load_panel_state()
        if loaded is not None:
            self._log.info("state.manager.init.panel.loaded_from_persistence")
            return loaded
        self._log.info("state.manager.init.panel.default")
        return _default_panel_state()

    def _load_inspector_or_default(self) -> InspectorState:
        """Load persisted inspector state. Ephemeral selection fields (active /
        active_pick_id / active_region_id) are NOT restored — the persistence layer
        resets them to model-defaults on load (Task 4)."""
        loaded = self._persistence.load_inspector_state()
        if loaded is not None:
            self._log.info("state.manager.init.inspector.loaded_from_persistence")
            return loaded
        self._log.info("state.manager.init.inspector.default")
        return InspectorState()

    def _load_recordings_or_default(self) -> RecordingsState:
        """Load persisted recordings and build in-memory state.

        Populates ``self._full_recordings`` (full Recording objects for mutations)
        and returns a ``RecordingsState`` with the lightweight meta list.
        Ephemeral selection fields (active_recording_id, active_detail_recording_id,
        detail_recording) are NOT restored — they default to None.
        """
        recordings = self._persistence.load_recordings()
        for rec in recordings:
            self._full_recordings[rec.recording_id] = rec
        if recordings:
            self._log.info("state.manager.init.recordings.loaded_from_persistence", count=len(recordings))
        else:
            self._log.info("state.manager.init.recordings.empty")
        metas = [self._recording_to_meta(r) for r in recordings]
        return RecordingsState(recordings=metas)

    def _load_microphone_or_default(self) -> MicrophoneState:
        """Load persisted microphone device selection. Device list is always empty on init —
        it is populated by the MicWatcher background task after startup.

        selected_device_id is restored from the settings key-value store so the user's
        preferred mic is remembered across restarts.
        """
        selected_device_id = self._persistence.load_mic_device_id()
        if selected_device_id is not None:
            self._log.info("state.manager.init.microphone.loaded_device_id", device_id=selected_device_id)
        return MicrophoneState(selected_device_id=selected_device_id)

    def _load_settings_or_default(self) -> SettingsState:
        """Load persisted durable voice-over settings from persistence.

        Returns defaults when no settings have been saved yet.
        """
        loaded = self._persistence.load_settings()
        if loaded is not None:
            self._log.info("state.manager.init.settings.loaded_from_persistence")
            return loaded
        self._log.info("state.manager.init.settings.default")
        return SettingsState()

    @staticmethod
    def _recording_to_meta(recording: Recording) -> RecordingMeta:
        """Build a lightweight RecordingMeta from a full Recording."""
        return RecordingMeta(
            recording_id=recording.recording_id,
            name=recording.name,
            description=recording.description,
            status=recording.status,
            started_at_ms=recording.started_at_ms,
            ended_at_ms=recording.ended_at_ms,
            entry_count=len(recording.entries),
            has_voice_over=recording.has_voice_over,
            audio_path=recording.audio_path,
            transcription_status=recording.transcription_status,
        )

    # ----- Read API ----------------------------------------------------------

    @property
    def session_id(self) -> str:
        """The provenance session-id this manager was constructed with (SSoT consumer).

        Sourced from ``session_lifecycle`` / ``SessionMetadata.session_id`` — never
        fabricated here. Read-only; the manager is a pure consumer of session identity.
        """
        return self._session_id

    @property
    def persistence(self) -> StatePersistence:
        """The injected persistence backend (InMemory stub or disk-backed SQLite)."""
        return self._persistence

    def snapshot(self) -> StateSnapshot:
        """Build a fresh immutable snapshot for wire-send. Does not acquire the lock itself —
        safe to call both inside and outside the lock. Called inside the lock from
        _post_mutate_locked (snapshot taken while holding), and outside the lock from external
        read paths (socket_server dispatch, initial state expose_function).

        Tiefe Kopien via ``model_copy(deep=True)`` — kein JSON-serialisierungs-roundtrip.
        """
        # model_copy(deep=True) replaces model_dump + model_validate.
        # In-memory deep copy is faster than a JSON serialisation round-trip and
        # semantically equivalent — all nested Pydantic models are reconstructed.
        # StateSnapshot wrapper is constructed fresh (not model_copy'd) so that
        # schema_version always comes from the class default.
        # COL-2: recordings_state MUST be passed explicitly here.
        # Without this, StateSnapshot uses default_factory=RecordingsState() and
        # silently emits an empty RecordingsState on every broadcast, making
        # the overlay completely blind to all recording state changes.
        # Voice-over sub-plan 01: three new state subtrees added.
        return StateSnapshot(
            panel_state=self._panel_state.model_copy(deep=True),
            inspector_state=self._inspector_state.model_copy(deep=True),
            recordings_state=self._recordings_state.model_copy(deep=True),
            microphone_state=self._microphone_state.model_copy(deep=True),
            settings_state=self._settings_state.model_copy(deep=True),
            transcription_state=self._transcription_state.model_copy(deep=True),
        )

    def state_summary(self) -> StateSummary:
        """Build a small navigable overview: counts + grouping, no entity payloads.

        Lock-discipline matches :meth:`snapshot` — read-only over the live state
        lists, no deep copy and no mutation, safe to call inside or outside the
        lock. The whole point is to NOT pay the full-snapshot cost: an AI agent
        gets counts + per-session + per-hostname grouping + owned-vs-foreign
        split, then drills down on demand via snapshot/get_picks/get_pick.

        Grouping keys:
            - ``origin_session``: the entity's provenance id; ``None`` (never
              persisted) collapses to ``"(none)"``.
            - hostname: derived from each Pick's url via
              :func:`~frontprompt.state.state.hostname_for_url` (``data:`` URLs
              collapse to a stable short label, never the blob).
            - owned-vs-foreign: a pick is *owned* iff its ``origin_session``
              equals this manager's ``session_id``.

        Groups are returned sorted by descending pick-count then name for stable,
        deterministic output.
        """
        inspector = self._inspector_state
        picks = inspector.picks
        regions = inspector.regions
        relations = inspector.relations

        # Per-origin-session tallies (picks + regions + relations).
        session_picks: dict[str, int] = {}
        session_regions: dict[str, int] = {}
        session_relations: dict[str, int] = {}

        def _origin(entity: Pick | Region | Relation) -> str:
            return entity.origin_session or "(none)"

        owned = 0
        foreign = 0
        host_picks: dict[str, int] = {}
        for pick in picks:
            origin = _origin(pick)
            session_picks[origin] = session_picks.get(origin, 0) + 1
            if pick.origin_session == self._session_id:
                owned += 1
            else:
                foreign += 1
            host = hostname_for_url(pick.url)
            host_picks[host] = host_picks.get(host, 0) + 1

        for region in regions:
            origin = _origin(region)
            session_regions[origin] = session_regions.get(origin, 0) + 1

        for relation in relations:
            origin = _origin(relation)
            session_relations[origin] = session_relations.get(origin, 0) + 1

        all_sessions = set(session_picks) | set(session_regions) | set(session_relations)
        by_origin_session = sorted(
            (
                OriginSessionGroup(
                    session=session,
                    picks=session_picks.get(session, 0),
                    regions=session_regions.get(session, 0),
                    relations=session_relations.get(session, 0),
                )
                for session in all_sessions
            ),
            key=lambda g: (-g.picks, g.session),
        )
        by_hostname = sorted(
            (HostnameGroup(hostname=host, picks=count) for host, count in host_picks.items()),
            key=lambda g: (-g.picks, g.hostname),
        )

        return StateSummary(
            schema_version=StateSnapshot.model_fields["schema_version"].default,
            current_session_id=self._session_id,
            active_pick_id=inspector.active_pick_id,
            active_region_id=inspector.active_region_id,
            counts=SummaryCounts(
                picks=len(picks),
                regions=len(regions),
                relations=len(relations),
            ),
            by_origin_session=by_origin_session,
            by_hostname=by_hostname,
            owned_vs_foreign=OwnedVsForeign(owned=owned, foreign=foreign),
        )

    def get_recording(self, recording_id: str) -> Recording | None:
        """Return the full Recording object by id, or None if unknown.

        Lock-free read — same discipline as snapshot(). Safe to call inside or
        outside the lock (read-only over _full_recordings).
        """
        return self._full_recordings.get(recording_id)

    def list_recordings_meta(self) -> list[RecordingMeta]:
        """Return the lightweight RecordingMeta list from the current recordings_state.

        Lock-free read. Returns a shallow copy to prevent callers from
        accidentally mutating the live state list.
        """
        return list(self._recordings_state.recordings)

    # ----- Mutation API: Panel (single-writer) -----------------------

    async def toggle_panel(self, panel_id: PanelId) -> StateSnapshot:
        """Flip panel open/closed. Returns new snapshot."""
        async with self._lock:
            panel = getattr(self._panel_state, panel_id)
            panel.open = not panel.open
            self._log.info("state.manager.toggle_panel", panel_id=panel_id, new_open=panel.open)
            snap = self._post_mutate_locked(self._persist_panel)
        return await self._notify_and_return(snap)

    async def resize_panel(self, panel_id: PanelId, new_size: int) -> StateSnapshot:
        """Set panel size (clamped to [min, max]). Returns new snapshot."""
        clamped = _clamp_size(panel_id, new_size)
        async with self._lock:
            panel = getattr(self._panel_state, panel_id)
            panel.size = clamped
            self._log.info(
                "state.manager.resize_panel",
                panel_id=panel_id,
                requested_size=new_size,
                applied_size=clamped,
            )
            snap = self._post_mutate_locked(self._persist_panel)
        return await self._notify_and_return(snap)

    async def set_all_panels_open(self, open_state: bool) -> StateSnapshot:
        """Bulk-set open/closed für alle panels (hide-all / show-all)."""
        async with self._lock:
            for pid in PANEL_IDS:
                getattr(self._panel_state, pid).open = open_state
            self._log.info("state.manager.set_all_panels_open", open_state=open_state)
            snap = self._post_mutate_locked(self._persist_panel)
        return await self._notify_and_return(snap)

    # ----- Mutation API: Inspector (single-writer) -------------------

    async def set_inspector_active(self, active: bool) -> StateSnapshot:
        """Flip inspector pick-mode on/off. Returns new snapshot.

        UI-Wirkung: panels retract via derived state (panel_state bleibt
        unverändert, frontend leitet effectiveOpen aus inspector.active ab).
        """
        async with self._lock:
            self._inspector_state.active = active
            self._log.info("state.manager.set_inspector_active", active=active)
            # active is an ephemeral selection field — never persisted (reset on load).
            snap = self._post_mutate_locked()
        return await self._notify_and_return(snap)

    async def add_pick(self, pick: Pick) -> StateSnapshot:
        """Atomic: append pick + set active_pick_id + clear inspector.active.

        Eine Snapshot-Broadcast nach allen drei mutations — der overlay sieht
        konsistenten state mit Pick in liste + active_pick_id = pick.pick_id +
        inspector.active = False (panels kommen automatisch via derived zurück).

        Idempotent gegen duplicate pick_id: wenn pick_id schon existiert,
        wird der existierende Pick durch den neuen ersetzt (last-write-wins).
        """
        async with self._lock:
            # Stamp provenance: this session now owns the pick (steal-on-mutate).
            pick.origin_session = self._session_id
            existing_idx = next(
                (i for i, p in enumerate(self._inspector_state.picks) if p.pick_id == pick.pick_id),
                None,
            )
            if existing_idx is not None:
                self._inspector_state.picks[existing_idx] = pick
                self._log.info("state.manager.add_pick.replace", pick_id=pick.pick_id)
            else:
                self._inspector_state.picks.append(pick)
                self._log.info(
                    "state.manager.add_pick",
                    pick_id=pick.pick_id,
                    selector=pick.element.selector,
                    url=pick.url,
                )
            self._inspector_state.active_pick_id = pick.pick_id
            self._inspector_state.active = False
            # COL-6: auto-link PickRefEntry into the active recording's timeline.
            # Same lock scope — one atomic operation.
            if self._recordings_state.active_recording_id is not None:
                self._append_timeline_entry_locked(
                    self._recordings_state.active_recording_id,
                    PickRefEntry(kind="pick_ref", seq=0, timestamp_ms=0, pick_id=pick.pick_id),
                )
            snap = self._post_mutate_locked(lambda: self._persistence.upsert_pick(pick))
        return await self._notify_and_return(snap)

    async def add_pick_from_programmatic_source(self, pick: Pick) -> None:
        """Persist an agent-created Pick without activating it in the UI.

        Unlike add_pick (which sets active_pick_id + clears inspector.active),
        this method is a silent background write — the pick appears in the list
        but no UI selection changes. Used by ProgrammaticPickService (single-writer).

        Idempotent by pick_id: last-write-wins (mirrors add_pick behavior).
        """
        async with self._lock:
            # Stamp provenance: this session now owns the pick (steal-on-mutate),
            # same as add_pick — the pick enters the persisted collection here.
            pick.origin_session = self._session_id
            existing_idx = next(
                (i for i, p in enumerate(self._inspector_state.picks) if p.pick_id == pick.pick_id),
                None,
            )
            if existing_idx is not None:
                self._inspector_state.picks[existing_idx] = pick
                self._log.info("state.manager.add_pick_programmatic.replace", pick_id=pick.pick_id)
            else:
                self._inspector_state.picks.append(pick)
                self._log.info(
                    "state.manager.add_pick_programmatic",
                    pick_id=pick.pick_id,
                    selector=pick.element.selector,
                    url=pick.url,
                )
            # COL-6: auto-link PickRefEntry from the programmatic path too.
            # Agent-created picks get equal timeline treatment.
            if self._recordings_state.active_recording_id is not None:
                self._append_timeline_entry_locked(
                    self._recordings_state.active_recording_id,
                    PickRefEntry(kind="pick_ref", seq=0, timestamp_ms=0, pick_id=pick.pick_id),
                )
            snap = self._post_mutate_locked(lambda: self._persistence.upsert_pick(pick))
        await self._notify_and_return(snap)

    async def select_pick(self, pick_id: str) -> StateSnapshot:
        """Set active_pick_id to the given pick. No-op if pick_id unknown.

        Snapshot wird trotzdem broadcast (idempotent re-hydrate) — keine
        Spezial-fall-Logik im aufrufer nötig.
        """
        async with self._lock:
            known = any(p.pick_id == pick_id for p in self._inspector_state.picks)
            if known:
                self._inspector_state.active_pick_id = pick_id
                self._log.info("state.manager.select_pick", pick_id=pick_id)
            else:
                self._log.warning("state.manager.select_pick.unknown", pick_id=pick_id)
            # active_pick_id is ephemeral selection — never persisted.
            snap = self._post_mutate_locked()
        return await self._notify_and_return(snap)

    async def update_pick_comment(self, pick_id: str, comment: str) -> StateSnapshot:
        """Patch the comment of an existing pick. No-op if pick_id unknown."""
        async with self._lock:
            mutated: Pick | None = None
            for pick in self._inspector_state.picks:
                if pick.pick_id == pick_id:
                    pick.comment = comment
                    pick.origin_session = self._session_id  # steal-on-mutate
                    mutated = pick
                    self._log.info(
                        "state.manager.update_pick_comment",
                        pick_id=pick_id,
                        comment_length=len(comment),
                    )
                    break
            else:
                self._log.warning("state.manager.update_pick_comment.unknown", pick_id=pick_id)
            persist = (lambda p=mutated: self._persistence.upsert_pick(p)) if mutated is not None else None
            snap = self._post_mutate_locked(persist)
        return await self._notify_and_return(snap)

    async def delete_pick(self, pick_id: str) -> StateSnapshot:
        """Remove pick from list. Cascade-drop relations + region-membership.

        Cascade:
            - alle Relations mit dem pick als source ODER target werden
              entfernt (auch wenn endpoint kind=pick).
            - alle Regions die diesen pick in member_pick_ids haben: pick aus
              members entfernen (Region selbst bleibt — sie ist ein
              eigenständiges Objekt mit eigener identity).
            - wenn active_pick_id == pick_id: clear.

        Eine atomare Mutation, ein Snapshot.

        No-op if pick_id unknown — snapshot wird trotzdem broadcast.
        """
        async with self._lock:
            before_picks = len(self._inspector_state.picks)
            self._inspector_state.picks = [p for p in self._inspector_state.picks if p.pick_id != pick_id]
            removed_picks = before_picks - len(self._inspector_state.picks)
            if self._inspector_state.active_pick_id == pick_id:
                self._inspector_state.active_pick_id = None
            # Cascade: relations involving this pick
            cascaded_relation_ids = [
                r.relation_id for r in self._inspector_state.relations if _relation_involves_pick(r, pick_id)
            ]
            self._inspector_state.relations = [
                r for r in self._inspector_state.relations if not _relation_involves_pick(r, pick_id)
            ]
            cascaded_relations = len(cascaded_relation_ids)
            # Cascade: pick aus region-memberships entfernen (regions selbst bleiben)
            touched_regions: list[Region] = []
            for region in self._inspector_state.regions:
                if pick_id in region.member_pick_ids:
                    region.member_pick_ids = [p for p in region.member_pick_ids if p != pick_id]
                    touched_regions.append(region)
            cascaded_memberships = len(touched_regions)
            self._log.info(
                "state.manager.delete_pick",
                pick_id=pick_id,
                removed_picks=removed_picks,
                cascaded_relations=cascaded_relations,
                cascaded_memberships=cascaded_memberships,
            )

            def _persist_delete_pick() -> None:
                self._persistence.delete_pick(pick_id)
                for rid in cascaded_relation_ids:
                    self._persistence.delete_relation(rid)
                for region in touched_regions:
                    self._persistence.upsert_region(region)

            snap = self._post_mutate_locked(_persist_delete_pick)
        return await self._notify_and_return(snap)

    # ----- Mutation API: Regions (single-writer) --------------------

    async def add_region(self, region: Region) -> StateSnapshot:
        """Append (or replace by region_id) eine Region.

        Validation: alle ``member_pick_ids`` müssen existing picks sein —
        unbekannte werden silent gefiltert (warning log). Member-set wird
        atomar gesetzt; späterer add_region mit selber id ersetzt komplett
        (last-write-wins, analog :meth:`add_pick` und :meth:`add_relation`).

        Setzt zudem ``active_region_id = region.region_id`` (right-panel zeigt
        die neue Region als details). Clears ``active_pick_id`` — mutually
        exclusive (Region und Pick teilen das right-panel).
        """
        async with self._lock:
            # Stamp provenance: this session now owns the region (steal-on-mutate).
            region.origin_session = self._session_id
            known_pick_ids = {p.pick_id for p in self._inspector_state.picks}
            invalid_members = [pid for pid in region.member_pick_ids if pid not in known_pick_ids]
            if invalid_members:
                self._log.warning(
                    "state.manager.add_region.unknown_members",
                    region_id=region.region_id,
                    invalid=invalid_members,
                )
                region.member_pick_ids = [pid for pid in region.member_pick_ids if pid in known_pick_ids]
            existing_idx = next(
                (i for i, r in enumerate(self._inspector_state.regions) if r.region_id == region.region_id),
                None,
            )
            if existing_idx is not None:
                self._inspector_state.regions[existing_idx] = region
                self._log.info("state.manager.add_region.replace", region_id=region.region_id)
            else:
                self._inspector_state.regions.append(region)
                self._log.info(
                    "state.manager.add_region",
                    region_id=region.region_id,
                    member_count=len(region.member_pick_ids),
                )
            self._inspector_state.active_region_id = region.region_id
            self._inspector_state.active_pick_id = None
            # COL-6: auto-link RegionRefEntry into the active recording's timeline.
            if self._recordings_state.active_recording_id is not None:
                self._append_timeline_entry_locked(
                    self._recordings_state.active_recording_id,
                    RegionRefEntry(kind="region_ref", seq=0, timestamp_ms=0, region_id=region.region_id),
                )
            snap = self._post_mutate_locked(lambda: self._persistence.upsert_region(region))
        return await self._notify_and_return(snap)

    async def delete_region(self, region_id: str) -> StateSnapshot:
        """Remove region. Cascade-drop relations involving this region.

        Picks die in region.member_pick_ids waren bleiben unverändert —
        Region ist ein **Container**, kein owner der members. Wenn der user
        die picks weghaben will, muss er sie separat löschen.

        Wenn active_region_id == region_id: clear.
        """
        async with self._lock:
            before_regions = len(self._inspector_state.regions)
            self._inspector_state.regions = [r for r in self._inspector_state.regions if r.region_id != region_id]
            removed = before_regions - len(self._inspector_state.regions)
            if self._inspector_state.active_region_id == region_id:
                self._inspector_state.active_region_id = None
            # Cascade: relations involving this region
            cascaded_relation_ids = [
                r.relation_id for r in self._inspector_state.relations if _relation_involves_region(r, region_id)
            ]
            self._inspector_state.relations = [
                r for r in self._inspector_state.relations if not _relation_involves_region(r, region_id)
            ]
            cascaded_relations = len(cascaded_relation_ids)
            self._log.info(
                "state.manager.delete_region",
                region_id=region_id,
                removed=removed,
                cascaded_relations=cascaded_relations,
            )

            def _persist_delete_region() -> None:
                self._persistence.delete_region(region_id)
                for rid in cascaded_relation_ids:
                    self._persistence.delete_relation(rid)

            snap = self._post_mutate_locked(_persist_delete_region)
        return await self._notify_and_return(snap)

    async def update_region(
        self,
        region_id: str,
        note: str | None,
    ) -> StateSnapshot:
        """Patch the note of an existing region. No-op if region_id unknown.

        Aktuell nur note — rect ist immutable (würde Member-collection neu-rechnen
        erfordern, Phase-2-feature wenn nötig). Members werden via separate
        add_region (last-write-wins) ersetzt.
        """
        async with self._lock:
            mutated: Region | None = None
            for region in self._inspector_state.regions:
                if region.region_id == region_id:
                    region.note = note
                    region.origin_session = self._session_id  # steal-on-mutate
                    mutated = region
                    self._log.info(
                        "state.manager.update_region",
                        region_id=region_id,
                        note_length=len(note) if note else 0,
                    )
                    break
            else:
                self._log.warning("state.manager.update_region.unknown", region_id=region_id)
            persist = (lambda r=mutated: self._persistence.upsert_region(r)) if mutated is not None else None
            snap = self._post_mutate_locked(persist)
        return await self._notify_and_return(snap)

    async def select_region(self, region_id: str) -> StateSnapshot:
        """Set active_region_id. Clears active_pick_id (mutually exclusive)."""
        async with self._lock:
            known = any(r.region_id == region_id for r in self._inspector_state.regions)
            if known:
                self._inspector_state.active_region_id = region_id
                self._inspector_state.active_pick_id = None
                self._log.info("state.manager.select_region", region_id=region_id)
            else:
                self._log.warning("state.manager.select_region.unknown", region_id=region_id)
            # active_region_id is ephemeral selection — never persisted.
            snap = self._post_mutate_locked()
        return await self._notify_and_return(snap)

    # ----- Mutation API: Relations (single-writer) -------------------

    async def add_relation(self, relation: Relation) -> StateSnapshot:
        """Append (or replace by relation_id) eine Relation (heterogeneous endpoints).

        Validation:
            - source und target dürfen nicht identisch sein (Pydantic
              model_validator + zusätzlicher manager-check).
            - source_id muss existieren in picks (wenn source_kind=pick) ODER
              regions (wenn source_kind=region); analog für target. Sonst
              silent reject (warning log), verhindert dangling-edges.

        Idempotenz: last-write-wins by relation_id.
        """
        async with self._lock:
            # Stamp provenance: this session now owns the relation (steal-on-mutate).
            # Rejected relations (self-loop / unknown endpoint) never enter the
            # collection, so stamping them is a harmless no-op.
            relation.origin_session = self._session_id
            if relation.source_id == relation.target_id and relation.source_kind == relation.target_kind:
                self._log.warning(
                    "state.manager.add_relation.self_loop_rejected",
                    relation_id=relation.relation_id,
                    node_kind=relation.source_kind,
                    node_id=relation.source_id,
                )
                snap = self._post_mutate_locked()
            elif not self._endpoint_exists(relation.source_id, relation.source_kind):
                self._log.warning(
                    "state.manager.add_relation.unknown_source",
                    relation_id=relation.relation_id,
                    source_kind=relation.source_kind,
                    source_id=relation.source_id,
                )
                snap = self._post_mutate_locked()
            elif not self._endpoint_exists(relation.target_id, relation.target_kind):
                self._log.warning(
                    "state.manager.add_relation.unknown_target",
                    relation_id=relation.relation_id,
                    target_kind=relation.target_kind,
                    target_id=relation.target_id,
                )
                snap = self._post_mutate_locked()
            else:
                existing_idx = next(
                    (i for i, r in enumerate(self._inspector_state.relations) if r.relation_id == relation.relation_id),
                    None,
                )
                if existing_idx is not None:
                    self._inspector_state.relations[existing_idx] = relation
                    self._log.info(
                        "state.manager.add_relation.replace",
                        relation_id=relation.relation_id,
                        kind=relation.kind,
                    )
                else:
                    self._inspector_state.relations.append(relation)
                    self._log.info(
                        "state.manager.add_relation",
                        relation_id=relation.relation_id,
                        kind=relation.kind,
                        source=f"{relation.source_kind}:{relation.source_id}",
                        target=f"{relation.target_kind}:{relation.target_id}",
                    )
                # COL-6: auto-link RelationRefEntry into the active recording's timeline.
                if self._recordings_state.active_recording_id is not None:
                    self._append_timeline_entry_locked(
                        self._recordings_state.active_recording_id,
                        RelationRefEntry(kind="relation_ref", seq=0, timestamp_ms=0, relation_id=relation.relation_id),
                    )
                snap = self._post_mutate_locked(lambda: self._persistence.upsert_relation(relation))
        return await self._notify_and_return(snap)

    def _endpoint_exists(self, node_id: str, node_kind: str) -> bool:
        """Check ob ein relation-endpoint (pick_id oder region_id) im state ist."""
        if node_kind == "pick":
            return any(p.pick_id == node_id for p in self._inspector_state.picks)
        if node_kind == "region":
            return any(r.region_id == node_id for r in self._inspector_state.regions)
        return False

    async def delete_relation(self, relation_id: str) -> StateSnapshot:
        """Remove relation by id. Idempotent — no-op if unknown."""
        async with self._lock:
            before = len(self._inspector_state.relations)
            self._inspector_state.relations = [
                r for r in self._inspector_state.relations if r.relation_id != relation_id
            ]
            removed = before - len(self._inspector_state.relations)
            self._log.info(
                "state.manager.delete_relation",
                relation_id=relation_id,
                removed=removed,
            )
            snap = self._post_mutate_locked(lambda: self._persistence.delete_relation(relation_id))
        return await self._notify_and_return(snap)

    async def update_relation(
        self,
        relation_id: str,
        kind: RelationKind,
        note: str | None,
    ) -> StateSnapshot:
        """Replace ``kind`` and ``note`` of an existing relation atomically.

        No-op if relation_id unknown — snapshot wird trotzdem broadcast.
        Beide Felder werden zusammen gesetzt: das Frontend-edit-modal sendet
        eine update-envelope für beide; partial updates sind nicht nötig.
        """
        async with self._lock:
            mutated: Relation | None = None
            for relation in self._inspector_state.relations:
                if relation.relation_id == relation_id:
                    relation.kind = kind
                    relation.note = note
                    relation.origin_session = self._session_id  # steal-on-mutate
                    mutated = relation
                    self._log.info(
                        "state.manager.update_relation",
                        relation_id=relation_id,
                        kind=kind,
                        note_length=len(note) if note else 0,
                    )
                    break
            else:
                self._log.warning(
                    "state.manager.update_relation.unknown",
                    relation_id=relation_id,
                )
            persist = (lambda r=mutated: self._persistence.upsert_relation(r)) if mutated is not None else None
            snap = self._post_mutate_locked(persist)
        return await self._notify_and_return(snap)

    # ----- Mutation API: Recordings (single-writer) ------------------

    async def start_recording(self, name: str = "New Recording", description: str = "") -> StateSnapshot:
        """Create a new Recording, set active_recording_id, broadcast snapshot.

        If a recording is already active, it is stopped first (idempotent guard).
        Clears active_detail_recording_id (reviewer Q2: avoids broadcasting a stale
        large detail_recording on every keydown during capture).
        """
        async with self._lock:
            # Stop any active recording first (idempotent guard)
            if self._recordings_state.active_recording_id is not None:
                self._stop_recording_locked(self._recordings_state.active_recording_id)

            recording_id = str(uuid.uuid4())
            now_ms = int(time.time() * 1000)
            recording = Recording(
                recording_id=recording_id,
                name=name,
                description=description,
                status="active",
                started_at_ms=now_ms,
                origin_session=self._session_id,
            )
            self._full_recordings[recording_id] = recording
            meta = self._recording_to_meta(recording)
            self._recordings_state.recordings.append(meta)
            self._recordings_state.active_recording_id = recording_id

            # Q2: clear detail selection — prevents large stale detail from riding
            # every broadcast during capture (~10 Hz)
            self._recordings_state.active_detail_recording_id = None
            self._recordings_state.detail_recording = None

            self._log.info("state.manager.start_recording", recording_id=recording_id, name=name)
            snap = self._post_mutate_locked(lambda: self._persistence.upsert_recording(recording))
        return await self._notify_and_return(snap)

    async def stop_recording(self, recording_id: str) -> StateSnapshot:
        """Mark recording as stopped, clear active_recording_id, broadcast snapshot.

        No-op (with warning log) if recording_id is unknown.
        """
        async with self._lock:
            if recording_id not in self._full_recordings:
                self._log.warning("state.manager.stop_recording.unknown", recording_id=recording_id)
                snap = self._post_mutate_locked()
            else:
                ended_at_ms = self._stop_recording_locked(recording_id)
                snap = self._post_mutate_locked(
                    lambda r_id=recording_id, ts=ended_at_ms: self._persistence.mark_recording_stopped(r_id, ts)
                )
        return await self._notify_and_return(snap)

    def _stop_recording_locked(self, recording_id: str) -> int:
        """Stop a recording in-memory. Must be called inside the lock. Returns ended_at_ms."""
        recording = self._full_recordings.get(recording_id)
        if recording is None:
            return 0
        ended_at_ms = int(time.time() * 1000)
        recording.status = "stopped"
        recording.ended_at_ms = ended_at_ms
        # Update the corresponding RecordingMeta in _recordings_state
        for meta in self._recordings_state.recordings:
            if meta.recording_id == recording_id:
                meta.status = "stopped"
                meta.ended_at_ms = ended_at_ms
                break
        if self._recordings_state.active_recording_id == recording_id:
            self._recordings_state.active_recording_id = None
        self._log.info("state.manager.stop_recording_locked", recording_id=recording_id, ended_at_ms=ended_at_ms)
        return ended_at_ms

    async def rename_recording(self, recording_id: str, name: str, description: str) -> StateSnapshot:
        """Update name + description of a recording. No-op if unknown."""
        async with self._lock:
            recording = self._full_recordings.get(recording_id)
            if recording is None:
                self._log.warning("state.manager.rename_recording.unknown", recording_id=recording_id)
                snap = self._post_mutate_locked()
            else:
                recording.name = name
                recording.description = description
                for meta in self._recordings_state.recordings:
                    if meta.recording_id == recording_id:
                        meta.name = name
                        meta.description = description
                        break
                self._log.info("state.manager.rename_recording", recording_id=recording_id, name=name)
                snap = self._post_mutate_locked(
                    lambda r_id=recording_id, n=name, d=description: self._persistence.update_recording_meta(r_id, n, d)
                )
        return await self._notify_and_return(snap)

    async def select_recording(self, recording_id: str | None) -> StateSnapshot:
        """Set active_detail_recording_id + populate detail_recording. None = deselect."""
        async with self._lock:
            if recording_id is None:
                self._recordings_state.active_detail_recording_id = None
                self._recordings_state.detail_recording = None
                self._log.info("state.manager.select_recording.deselect")
            else:
                recording = self._full_recordings.get(recording_id)
                if recording is None:
                    self._log.warning("state.manager.select_recording.unknown", recording_id=recording_id)
                else:
                    self._recordings_state.active_detail_recording_id = recording_id
                    self._recordings_state.detail_recording = recording.model_copy(deep=True)
                    self._log.info("state.manager.select_recording", recording_id=recording_id)
            snap = self._post_mutate_locked()
        return await self._notify_and_return(snap)

    async def append_timeline_entry(self, recording_id: str, entry: TimelineEntry) -> None:
        """Append a timeline entry to a recording.

        NON-BROADCASTING PATH (COL-5): This method deliberately does NOT call
        _post_mutate_locked / _notify_listeners. Every keydown event during capture
        would trigger a full-state snapshot broadcast at ~10 Hz without this isolation.
        The snapshot's RecordingMeta.entry_count stays stale until the next natural
        snapshot trigger (nav, stop, rename) — acceptable since the frontend does not
        need live entry_count during capture.

        seq ownership (Q1): seq is stamped here as len(recording.entries) atomically
        inside the lock — never by the frontend. One monotonic counter across ALL entry
        kinds (page_event, pick_ref, region_ref, relation_ref, navigation) eliminates
        UNIQUE(recording_id, seq) collision hazard regardless of message-arrival ordering.
        """
        async with self._lock:
            self._append_timeline_entry_locked(recording_id, entry)
            # Deliberate: NO _post_mutate_locked / _notify_listeners call here.
            # See COL-5 note above.

    def _append_timeline_entry_locked(self, recording_id: str, entry: TimelineEntry) -> None:
        """Append entry to in-memory recording + persist. Must be called inside the lock.

        Stamps seq + timestamp_ms server-side (Q1 Python-owned seq). Used by both
        the public append_timeline_entry and the auto-link paths in add_pick / add_region
        / add_relation / add_pick_from_programmatic_source.
        """
        recording = self._full_recordings.get(recording_id)
        if recording is None:
            self._log.warning("state.manager.append_timeline_entry.unknown_recording", recording_id=recording_id)
            return
        # Q1: Python stamps seq as len(entries) — atomically inside the lock.
        # Any frontend-supplied seq value is overwritten here.
        entry.seq = len(recording.entries)
        entry.timestamp_ms = int(time.time() * 1000)
        recording.entries.append(entry)
        self._persistence.append_timeline_entry(recording_id, entry)
        self._log.debug(
            "state.manager.append_timeline_entry_locked",
            recording_id=recording_id,
            seq=entry.seq,
            kind=entry.kind,
        )

    # ----- Mutation API: Assertions (single-writer) ------------------

    async def add_assertion_to_timeline(
        self,
        recording_id: str,
        entry_payload: dict,
        insert_after_seq: int | None = None,
    ) -> StateSnapshot:
        """Append or insert an AssertionEntry into a recording's timeline.

        When ``insert_after_seq=None``, appended at end (seq = len(entries)).
        When ``insert_after_seq`` is set, the assertion is inserted after the
        entry with that seq and all subsequent entries are renumbered.

        No-op with warning if recording_id is unknown. Broadcasts snapshot.
        """
        async with self._lock:
            recording = self._full_recordings.get(recording_id)
            if recording is None:
                self._log.warning(
                    "state.manager.add_assertion.unknown_recording", recording_id=recording_id
                )
                snap = self._post_mutate_locked()
            else:
                now_ms = int(time.time() * 1000)
                entry = AssertionEntry(
                    kind="assertion",
                    seq=0,  # stamped below
                    timestamp_ms=now_ms,
                    **entry_payload,
                )
                if insert_after_seq is None:
                    # Append at end
                    entry.seq = len(recording.entries)
                    recording.entries.append(entry)
                else:
                    # Insert after the given seq — find insertion index
                    insert_idx = next(
                        (i + 1 for i, e in enumerate(recording.entries) if e.seq == insert_after_seq),
                        len(recording.entries),
                    )
                    entry.seq = insert_idx
                    recording.entries.insert(insert_idx, entry)
                    # Renumber all entries after the insertion point
                    for i, e in enumerate(recording.entries):
                        e.seq = i

                self._log.info(
                    "state.manager.add_assertion",
                    recording_id=recording_id,
                    assertion_id=entry.assertion_id,
                    seq=entry.seq,
                    insert_after_seq=insert_after_seq,
                )
                snap = self._post_mutate_locked()
        return await self._notify_and_return(snap)

    async def delete_assertion(self, recording_id: str, assertion_id: str) -> StateSnapshot:
        """Remove an AssertionEntry from a recording's timeline. Renumbers seqs.

        No-op if recording or assertion is unknown. Broadcasts snapshot.
        """
        async with self._lock:
            recording = self._full_recordings.get(recording_id)
            if recording is None:
                self._log.warning(
                    "state.manager.delete_assertion.unknown_recording", recording_id=recording_id
                )
                snap = self._post_mutate_locked()
            else:
                before = len(recording.entries)
                recording.entries = [
                    e for e in recording.entries
                    if not (e.kind == "assertion" and e.assertion_id == assertion_id)  # type: ignore[attr-defined]
                ]
                removed = before - len(recording.entries)
                if removed == 0:
                    self._log.warning(
                        "state.manager.delete_assertion.not_found",
                        recording_id=recording_id,
                        assertion_id=assertion_id,
                    )
                else:
                    # Renumber seqs monotonically after deletion
                    for i, e in enumerate(recording.entries):
                        e.seq = i
                    self._log.info(
                        "state.manager.delete_assertion",
                        recording_id=recording_id,
                        assertion_id=assertion_id,
                    )
                snap = self._post_mutate_locked()
        return await self._notify_and_return(snap)

    async def update_assertion(
        self,
        recording_id: str,
        assertion_id: str,
        patch: dict,
    ) -> StateSnapshot:
        """Partial update of an AssertionEntry in a recording's timeline.

        Only the fields present in ``patch`` are updated; omitted fields stay unchanged.
        No-op if recording or assertion is unknown. Broadcasts snapshot.
        """
        async with self._lock:
            recording = self._full_recordings.get(recording_id)
            if recording is None:
                self._log.warning(
                    "state.manager.update_assertion.unknown_recording", recording_id=recording_id
                )
                snap = self._post_mutate_locked()
            else:
                mutated = False
                for entry in recording.entries:
                    if entry.kind == "assertion" and entry.assertion_id == assertion_id:  # type: ignore[attr-defined]
                        for field, value in patch.items():
                            if hasattr(entry, field):
                                setattr(entry, field, value)
                        mutated = True
                        self._log.info(
                            "state.manager.update_assertion",
                            recording_id=recording_id,
                            assertion_id=assertion_id,
                            patch_keys=list(patch.keys()),
                        )
                        break
                if not mutated:
                    self._log.warning(
                        "state.manager.update_assertion.not_found",
                        recording_id=recording_id,
                        assertion_id=assertion_id,
                    )
                snap = self._post_mutate_locked()
        return await self._notify_and_return(snap)

    # ----- Mutation API: Parameters (single-writer) ------------------

    async def add_parameter_to_recording(
        self,
        recording_id: str,
        param: ParameterDeclaration,
    ) -> StateSnapshot:
        """Append a ParameterDeclaration to a recording.

        Enforces name uniqueness — raises ``ValueError`` if ``param.name`` is
        already declared on the recording. No-op (with warning) if recording
        is unknown. Broadcasts snapshot.
        """
        async with self._lock:
            recording = self._full_recordings.get(recording_id)
            if recording is None:
                self._log.warning(
                    "state.manager.add_parameter.unknown_recording", recording_id=recording_id
                )
                snap = self._post_mutate_locked()
            else:
                existing_names = {p.name for p in recording.parameters}
                if param.name in existing_names:
                    raise ValueError(
                        f"Parameter name '{param.name}' already declared on recording {recording_id!r}."
                    )
                recording.parameters.append(param)
                self._log.info(
                    "state.manager.add_parameter",
                    recording_id=recording_id,
                    param_name=param.name,
                    param_type=param.param_type,
                )
                snap = self._post_mutate_locked()
        return await self._notify_and_return(snap)

    # ----- Replay report API (read + write, no broadcast) ------------

    async def save_replay_report(self, report: ReplayReport) -> None:
        """Persist a ReplayReport. Delegates to persistence; no snapshot broadcast.

        Replay reports are large; agents poll via GetReplayReportRequest IPC call.
        Non-broadcasting path (mirrors append_timeline_entry discipline, PIT-105).
        Acquires lock for safe write-through to the persistence layer.
        """
        async with self._lock:
            self._persistence.save_replay_report(report)
        self._log.debug("state.manager.save_replay_report", replay_id=report.replay_id)

    async def get_replay_report(self, replay_id: str) -> ReplayReport | None:
        """Retrieve a ReplayReport by replay_id from persistence.

        Lock-free read (mirrors snapshot() / get_recording() discipline).
        """
        return self._persistence.get_replay_report(replay_id)

    async def list_replay_reports_meta(
        self, recording_id: str | None = None
    ) -> list[ReplayReportMeta]:
        """Return lightweight ReplayReportMeta list from persistence.

        Lock-free read. Optionally filtered by recording_id.
        """
        return self._persistence.list_replay_reports_meta(recording_id)

    # ----- Replay progress (backendState, broadcasts) ----------------

    async def set_active_replay_progress(
        self, progress: ReplayProgress | None
    ) -> StateSnapshot:
        """Update RecordingsState.active_replay_progress + broadcast snapshot.

        ``None`` = no active replay (cleared after replay finishes or is aborted).
        Single-field, last-writer-wins (one active replay at a time, MVP).
        Acquires lock (ADR-011: anyio.Lock, single-writer).
        """
        async with self._lock:
            self._recordings_state.active_replay_progress = progress
            self._log.info(
                "state.manager.set_active_replay_progress",
                replay_id=progress.replay_id if progress is not None else None,
            )
            snap = self._post_mutate_locked()
        return await self._notify_and_return(snap)

    # ----- Mutation API: Voice-over recording meta (single-writer) ----------

    async def set_audio_path(self, recording_id: str, audio_path: str) -> StateSnapshot:
        """Set the audio file path on a recording after capture completes.

        No-op (with warning) if recording_id is unknown. Broadcasts snapshot.
        Persists via upsert_recording (full row overwrite for voice-over meta changes).
        """
        async with self._lock:
            recording = self._full_recordings.get(recording_id)
            if recording is None:
                self._log.warning("state.manager.set_audio_path.unknown", recording_id=recording_id)
                snap = self._post_mutate_locked()
            else:
                recording.audio_path = audio_path
                recording.has_voice_over = True
                # Sync RecordingMeta in _recordings_state
                for meta in self._recordings_state.recordings:
                    if meta.recording_id == recording_id:
                        meta.audio_path = audio_path
                        meta.has_voice_over = True
                        break
                self._log.info("state.manager.set_audio_path", recording_id=recording_id, audio_path=audio_path)
                snap = self._post_mutate_locked(lambda: self._persistence.upsert_recording(recording))
        return await self._notify_and_return(snap)

    async def set_transcription_status(
        self,
        recording_id: str,
        status: str,
        error: str | None,
    ) -> StateSnapshot:
        """Set transcription_status (and optional error) on a recording atomically.

        No-op (with warning) if recording_id is unknown. Broadcasts snapshot.
        Persists via upsert_recording.
        """
        async with self._lock:
            recording = self._full_recordings.get(recording_id)
            if recording is None:
                self._log.warning("state.manager.set_transcription_status.unknown", recording_id=recording_id)
                snap = self._post_mutate_locked()
            else:
                recording.transcription_status = status  # type: ignore[assignment]
                recording.transcription_error = error
                # Sync RecordingMeta in _recordings_state
                for meta in self._recordings_state.recordings:
                    if meta.recording_id == recording_id:
                        meta.transcription_status = status  # type: ignore[assignment]
                        break
                self._log.info(
                    "state.manager.set_transcription_status",
                    recording_id=recording_id,
                    status=status,
                    has_error=error is not None,
                )
                snap = self._post_mutate_locked(lambda: self._persistence.upsert_recording(recording))
        return await self._notify_and_return(snap)

    async def append_transcript_segments(
        self,
        recording_id: str,
        segments: list[TranscriptSegmentEntry],
        backend_id: str,
    ) -> StateSnapshot:
        """Append all TranscriptSegmentEntry items and set transcription_status='done'.

        PIT-105 pattern: hold lock once for all appends, single broadcast at the end.
        ``timestamp_ms`` is stamped as ``recording.started_at_ms + segment.start_ms``
        (voice-over semantics differ from real-time event timestamps).
        ``seq`` is assigned by Python (len(entries) at the time of each append).
        """
        async with self._lock:
            recording = self._full_recordings.get(recording_id)
            if recording is None:
                self._log.warning("state.manager.append_transcript_segments.unknown", recording_id=recording_id)
                snap = self._post_mutate_locked()
            else:
                for segment in segments:
                    segment.seq = len(recording.entries)
                    segment.timestamp_ms = recording.started_at_ms + segment.start_ms
                    segment.backend_id = backend_id
                    recording.entries.append(segment)
                    self._persistence.append_timeline_entry(recording_id, segment)

                # Set status=done atomically in the same lock hold
                recording.transcription_status = "done"
                recording.transcription_error = None
                for meta in self._recordings_state.recordings:
                    if meta.recording_id == recording_id:
                        meta.transcription_status = "done"
                        break

                self._log.info(
                    "state.manager.append_transcript_segments",
                    recording_id=recording_id,
                    count=len(segments),
                )
                # Single broadcast for all appends (PIT-105 pattern)
                snap = self._post_mutate_locked(lambda: self._persistence.upsert_recording(recording))
        return await self._notify_and_return(snap)

    # ----- Mutation API: MicrophoneState (single-writer) --------------------

    async def update_microphone_state(
        self,
        devices: list[MicrophoneDevice],
        system_default_device_id: int | None = None,
    ) -> StateSnapshot:
        """Replace the microphone device list when topology changed.

        Topology hash is computed outside the lock (pure compute over device_ids).
        The lock is acquired ONLY if the hash changed — devices list change is
        the guard. Preserves ``selected_device_id`` across topology changes.

        ``system_default_device_id`` is updated whenever watcher re-scans.
        """
        new_hash = frozenset(d.device_id for d in devices)
        # Check topology hash outside lock (read-only access to current hash)
        if new_hash == self._microphone_topology_hash and system_default_device_id == self._microphone_state.system_default_device_id:
            # No change — skip broadcast
            self._log.debug("state.manager.update_microphone_state.no_change")
            return self.snapshot()

        async with self._lock:
            # Re-check inside lock (double-checked locking — benign if same watcher)
            if new_hash == self._microphone_topology_hash and system_default_device_id == self._microphone_state.system_default_device_id:
                snap = self._post_mutate_locked()
            else:
                # Preserve selected_device_id
                selected = self._microphone_state.selected_device_id
                self._microphone_state.devices = list(devices)
                self._microphone_state.system_default_device_id = system_default_device_id
                self._microphone_state.selected_device_id = selected
                self._microphone_topology_hash = new_hash
                self._log.info(
                    "state.manager.update_microphone_state",
                    device_count=len(devices),
                    system_default=system_default_device_id,
                )
                snap = self._post_mutate_locked()
        return await self._notify_and_return(snap)

    async def set_mic_device(self, device_id: int | None) -> StateSnapshot:
        """Set the selected microphone device. Persists to settings key-value table.

        ``None`` = revert to system default. Broadcasts snapshot.
        """
        async with self._lock:
            self._microphone_state.selected_device_id = device_id
            self._log.info("state.manager.set_mic_device", device_id=device_id)
            snap = self._post_mutate_locked(lambda: self._persistence.save_mic_device_id(device_id))
        return await self._notify_and_return(snap)

    # ----- Mutation API: SettingsState (single-writer) ----------------------

    async def set_settings(self, settings: SettingsState) -> StateSnapshot:
        """Replace durable voice-over settings. Persists to settings key-value table.

        Broadcasts snapshot. Uses full replacement (no partial patch) — the UI
        always sends the complete settings object.
        """
        async with self._lock:
            self._settings_state = settings
            self._log.info(
                "state.manager.set_settings",
                voice_over_enabled=settings.voice_over_enabled,
                backend=settings.selected_transcription_backend_id,
            )
            snap = self._post_mutate_locked(lambda: self._persistence.save_settings(settings))
        return await self._notify_and_return(snap)

    # ----- Mutation API: TranscriptionState (single-writer) -----------------

    async def update_transcription_backend_status(
        self,
        backend_id: str,
        status: TranscriptionBackendStatus,
        download_progress: float | None,
    ) -> StateSnapshot:
        """Update status + download_progress for a backend in TranscriptionState.

        No-op (with warning) if backend_id is not found. Broadcasts snapshot.
        TranscriptionState is in-process only (ADR-018: ephemeral backend probing
        state is NOT persisted to SQLite).
        """
        async with self._lock:
            backend = next(
                (b for b in self._transcription_state.backends if b.backend_id == backend_id),
                None,
            )
            if backend is None:
                self._log.warning(
                    "state.manager.update_transcription_backend_status.unknown",
                    backend_id=backend_id,
                )
                snap = self._post_mutate_locked()
            else:
                backend.status = status
                backend.download_progress = download_progress
                self._log.info(
                    "state.manager.update_transcription_backend_status",
                    backend_id=backend_id,
                    status=status,
                    download_progress=download_progress,
                )
                snap = self._post_mutate_locked()
        return await self._notify_and_return(snap)

    # ----- Post-mutation hook ------------------------------------------------

    def _persist_panel(self) -> None:
        """Persist the panel-state singleton (full overwrite — no accumulation hazard)."""
        self._persistence.save_panel_state(self._panel_state)

    def _post_mutate_locked(self, persist: Callable[[], None] | None = None) -> StateSnapshot:
        """Called inside the lock: run the targeted persist write + build snapshot.

        ``persist`` is the entity-scoped write for THIS mutation (e.g.
        ``lambda: self._persistence.upsert_pick(pick)`` or a panel-state save).
        It is a per-entity write-through, NOT a whole-set overwrite: the disk is
        the source of truth for "what exists", so a delete in one session is
        never resurrected by another session flushing its stale in-memory set.
        This is the fix for the cross-session picks-accumulation bug
        (tests/state/persistence/test_sqlite_accumulation.py +
        tests/state/test_manager_persistence.py::test_concurrent_managers_deletes_stick).

        Mutations that change nothing on disk (e.g. selection-only) pass
        ``persist=None``.

        Single-writer: lock-free listener contract — callers must release
        the lock before calling _notify_and_return(snap).
        """
        if persist is not None:
            persist()
        return self.snapshot()

    async def _notify_and_return(self, snap: StateSnapshot) -> StateSnapshot:
        """Called OUTSIDE the lock: notify listeners, return snapshot.

        Must be called after async with self._lock: block ends.
        Ensures listeners can schedule nested mutations without deadlock.
        """
        await self._notify_listeners(snap)
        return snap

    async def _post_mutate(self) -> StateSnapshot:
        """Compat shim — must only be called from within an async with self._lock: block.

        Builds snapshot inside lock, then returns it. Callers that hold the lock
        and call this directly cannot benefit from the lock-free listener fix.
        Use _post_mutate_locked() + _notify_and_return() instead.

        This shim is kept for compatibility with any call-sites that cannot easily
        be restructured. The listener call happens outside the lock via
        _notify_and_return after the lock is implicitly released on return.

        NOTE: This method intentionally does NOT call _notify_listeners —
        that is the responsibility of each mutation method which uses the
        _post_mutate_locked() / _notify_and_return() split pattern.
        """
        return self._post_mutate_locked()

    async def _notify_listeners(self, snap: StateSnapshot) -> None:
        for fn in self._listeners:
            try:
                result = fn(snap)
                if hasattr(result, "__await__"):
                    await result  # type: ignore[misc]
            except Exception as exc:
                self._log.exception("state.manager.listener_failed", error=str(exc))

    # ----- Subscription API --------------------------------------------------

    def add_snapshot_listener(self, listener: SnapshotListener) -> Callable[[], None]:
        """Register a callback that fires after every mutation with new snapshot.

        Returns unsubscribe-function.

        Unsubscribe invariant (verified false-positive): the unsubscribe lambda accesses
        ``self._listeners`` via attribute lookup, not by closing over the list object —
        safe if ``_listeners`` is reassigned on the instance. Invariant: ``_listeners``
        is only mutated in-place (``.append``, ``.remove``); it is never reassigned.
        """
        self._listeners.append(listener)
        return lambda: self._listeners.remove(listener) if listener in self._listeners else None


__all__ = ["StateManager"]
