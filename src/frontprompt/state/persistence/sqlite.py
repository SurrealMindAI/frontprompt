"""SqlitePersistence — SQLite-backed persistence implementation.

Phase-2 disk-persistence provider. One long-lived ``sqlite3.Connection`` per
instance, WAL mode, idempotent DDL via ``CREATE TABLE IF NOT EXISTS``.

State classification: Python is authoritative; this module serialises/deserialises Pydantic
models via ``model_dump_json`` / ``model_validate_json`` — no hand-rolled SQL
column mapping.

Resilience contract (Task 5):
- Corrupt rows (bad JSON / failed Pydantic validation) are skipped with a warning.
- Write failures (``sqlite3.Error``) are swallowed with a warning — no raise.
- :func:`make_persistence` is the factory that callers should use; it falls back to
  :class:`~frontprompt.state.persistence.in_memory.InMemoryPersistence` on any init error.
"""

from __future__ import annotations

import json
import sqlite3
from pathlib import Path
from typing import TYPE_CHECKING

import pydantic
import structlog

if TYPE_CHECKING:
    from frontprompt.state.persistence.protocol import StatePersistence
    from frontprompt.state.state import (
        InspectorState,
        PanelStateView,
        Pick,
        Recording,
        Region,
        Relation,
        ReplayReport,
        ReplayReportMeta,
        SettingsState,
        TimelineEntry,
    )

_LOG = structlog.get_logger(__name__)

# ---------------------------------------------------------------------------
# DDL — must match spec exactly (idempotent via IF NOT EXISTS)
# ---------------------------------------------------------------------------

_DDL = """\
CREATE TABLE IF NOT EXISTS panel_state (
    id          INTEGER PRIMARY KEY CHECK (id = 0),
    payload_json TEXT NOT NULL,
    updated_at   TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS picks (
    pick_id        TEXT PRIMARY KEY,
    origin_session TEXT,
    url            TEXT,
    payload_json   TEXT NOT NULL,
    updated_at     TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS regions (
    region_id      TEXT PRIMARY KEY,
    origin_session TEXT,
    payload_json   TEXT NOT NULL,
    updated_at     TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS relations (
    relation_id    TEXT PRIMARY KEY,
    origin_session TEXT,
    payload_json   TEXT NOT NULL,
    updated_at     TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS schema_meta (
    key   TEXT PRIMARY KEY,
    value TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS recordings (
    recording_id   TEXT PRIMARY KEY,
    origin_session TEXT,
    payload_json   TEXT NOT NULL,
    status         TEXT NOT NULL,
    started_at_ms  INTEGER NOT NULL,
    ended_at_ms    INTEGER,
    updated_at     TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS timeline_entries (
    entry_id     INTEGER PRIMARY KEY AUTOINCREMENT,
    recording_id TEXT NOT NULL REFERENCES recordings(recording_id),
    seq          INTEGER NOT NULL,
    kind         TEXT NOT NULL,
    timestamp_ms INTEGER NOT NULL,
    payload_json TEXT NOT NULL,
    UNIQUE(recording_id, seq)
);

CREATE TABLE IF NOT EXISTS replay_reports (
    replay_id        TEXT PRIMARY KEY,
    recording_id     TEXT NOT NULL,
    status           TEXT NOT NULL,
    started_at_ms    INTEGER NOT NULL,
    ended_at_ms      INTEGER,
    parameters_json  TEXT NOT NULL,
    step_results_json TEXT NOT NULL,
    error            TEXT,
    origin_session   TEXT,
    updated_at       TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS settings (
    key   TEXT PRIMARY KEY,
    value TEXT NOT NULL
);
"""

# Voice-over columns added to recordings table (migration guard — ALTER TABLE
# silently fails if the column already exists, as SQLite does not support
# IF NOT EXISTS for ALTER TABLE before 3.37.0).
_RECORDINGS_VOICE_OVER_MIGRATIONS = [
    "ALTER TABLE recordings ADD COLUMN has_voice_over INTEGER NOT NULL DEFAULT 0",
    "ALTER TABLE recordings ADD COLUMN audio_path TEXT",
    "ALTER TABLE recordings ADD COLUMN transcription_status TEXT NOT NULL DEFAULT 'none'",
    "ALTER TABLE recordings ADD COLUMN transcription_error TEXT",
]

_SEED_SCHEMA_VERSION = "INSERT OR IGNORE INTO schema_meta (key, value) VALUES (?, ?)"


class SqlitePersistence:
    """SQLite-backed persistence — Phase-2 disk provider.

    Implements :class:`~frontprompt.state.persistence.protocol.StatePersistence`.
    Panel-state serialised as single JSON row at ``id=0`` (singleton).
    Inspector-state methods are Task-4 stubs.

    Parameters
    ----------
    db_path:
        Filesystem path to the SQLite database file.  Parent directories are
        created automatically.  WAL journal mode is activated on every open so
        readers never block writers.
    """

    def __init__(self, db_path: Path) -> None:
        self._db_path = db_path
        self._log = _LOG.bind(impl="sqlite", db_path=str(db_path))

        db_path.parent.mkdir(parents=True, exist_ok=True)

        self._conn = sqlite3.connect(str(db_path))
        self._conn.execute("PRAGMA journal_mode = WAL")
        self._conn.executescript(_DDL)
        self._conn.execute(_SEED_SCHEMA_VERSION, ("db_schema_version", "1"))
        self._conn.commit()

        # Run voice-over column migrations (idempotent — guard against "duplicate column" error)
        for migration_sql in _RECORDINGS_VOICE_OVER_MIGRATIONS:
            try:
                self._conn.execute(migration_sql)
                self._conn.commit()
            except sqlite3.OperationalError:
                # Column already exists — normal for existing databases
                pass

        self._log.debug("state.persistence.sqlite.init_ok")

    # ------------------------------------------------------------------
    # Panel-state
    # ------------------------------------------------------------------

    def load_panel_state(self) -> PanelStateView | None:
        """Return persisted panel-state or ``None`` when no row exists."""
        from frontprompt.state.state import PanelStateView

        row = self._conn.execute("SELECT payload_json FROM panel_state WHERE id = 0").fetchone()

        if row is None:
            self._log.debug("state.persistence.sqlite.load_panel.empty")
            return None

        self._log.debug("state.persistence.sqlite.load_panel.hit")
        return PanelStateView.model_validate_json(row[0])

    def save_panel_state(self, panel_state: PanelStateView) -> None:
        """Upsert panel-state as singleton row (``id=0``).

        Write failures (``sqlite3.Error``) are swallowed and logged as warnings.
        """
        payload = panel_state.model_dump_json()
        try:
            self._conn.execute(
                """
                INSERT INTO panel_state (id, payload_json, updated_at)
                VALUES (0, ?, datetime('now'))
                ON CONFLICT (id) DO UPDATE SET
                    payload_json = excluded.payload_json,
                    updated_at   = excluded.updated_at
                """,
                (payload,),
            )
            self._conn.commit()
        except sqlite3.Error as exc:
            self._log.warning("state.persistence.save.failed", method="save_panel_state", error=str(exc))
            return
        self._log.debug("state.persistence.sqlite.save_panel.ok")

    # ------------------------------------------------------------------
    # Inspector-state
    # ------------------------------------------------------------------

    def load_inspector_state(self) -> InspectorState | None:
        """Read all inspector entities from disk and assemble a fresh InspectorState.

        Ephemeral selection fields (``active``, ``active_pick_id``, ``active_region_id``)
        are intentionally NOT restored — they default to their model defaults (False / None).

        Returns ``None`` when all three tables are empty.
        """
        from frontprompt.state.state import InspectorState, Pick, Region, Relation

        pick_rows = self._conn.execute("SELECT payload_json FROM picks").fetchall()
        region_rows = self._conn.execute("SELECT payload_json FROM regions").fetchall()
        relation_rows = self._conn.execute("SELECT payload_json FROM relations").fetchall()

        if not pick_rows and not region_rows and not relation_rows:
            self._log.debug("state.persistence.sqlite.load_inspector.empty")
            return None

        picks: list[Pick] = []
        for r in pick_rows:
            try:
                picks.append(Pick.model_validate_json(r[0]))
            except (json.JSONDecodeError, pydantic.ValidationError) as exc:
                self._log.warning("state.persistence.load.row_skipped", table="picks", error=str(exc))

        regions: list[Region] = []
        for r in region_rows:
            try:
                regions.append(Region.model_validate_json(r[0]))
            except (json.JSONDecodeError, pydantic.ValidationError) as exc:
                self._log.warning("state.persistence.load.row_skipped", table="regions", error=str(exc))

        relations: list[Relation] = []
        for r in relation_rows:
            try:
                relations.append(Relation.model_validate_json(r[0]))
            except (json.JSONDecodeError, pydantic.ValidationError) as exc:
                self._log.warning("state.persistence.load.row_skipped", table="relations", error=str(exc))

        self._log.debug(
            "state.persistence.sqlite.load_inspector.hit",
            picks=len(picks),
            regions=len(regions),
            relations=len(relations),
        )
        return InspectorState(picks=picks, regions=regions, relations=relations)

    # ----- Per-entity write-through (authoritative + idempotent on id) --------
    #
    # Runtime mutations write ONE entity at a time. The disk is the source of
    # truth for "what exists" — a session never rewrites the full set from its
    # (possibly stale) in-memory copy, so a delete in one session is never
    # resurrected by another session's flush. Fixes the cross-session
    # picks-accumulation bug (tests/state/persistence/test_sqlite_accumulation.py).

    _UPSERT_PICK = """
        INSERT INTO picks (pick_id, origin_session, url, payload_json, updated_at)
        VALUES (?, ?, ?, ?, datetime('now'))
        ON CONFLICT (pick_id) DO UPDATE SET
            origin_session = excluded.origin_session,
            url            = excluded.url,
            payload_json   = excluded.payload_json,
            updated_at     = excluded.updated_at
    """

    _UPSERT_REGION = """
        INSERT INTO regions (region_id, origin_session, payload_json, updated_at)
        VALUES (?, ?, ?, datetime('now'))
        ON CONFLICT (region_id) DO UPDATE SET
            origin_session = excluded.origin_session,
            payload_json   = excluded.payload_json,
            updated_at     = excluded.updated_at
    """

    _UPSERT_RELATION = """
        INSERT INTO relations (relation_id, origin_session, payload_json, updated_at)
        VALUES (?, ?, ?, datetime('now'))
        ON CONFLICT (relation_id) DO UPDATE SET
            origin_session = excluded.origin_session,
            payload_json   = excluded.payload_json,
            updated_at     = excluded.updated_at
    """

    def upsert_pick(self, pick: Pick) -> None:
        """Insert-or-replace one pick keyed on ``pick_id``. Idempotent."""
        try:
            with self._conn:
                self._conn.execute(
                    self._UPSERT_PICK,
                    (pick.pick_id, pick.origin_session, pick.url, pick.model_dump_json()),
                )
        except sqlite3.Error as exc:
            self._log.warning("state.persistence.save.failed", method="upsert_pick", error=str(exc))
            return
        self._log.debug("state.persistence.sqlite.upsert_pick.ok", pick_id=pick.pick_id)

    def delete_pick(self, pick_id: str) -> None:
        """Delete one pick by ``pick_id``. Idempotent (no-op if absent)."""
        try:
            with self._conn:
                self._conn.execute("DELETE FROM picks WHERE pick_id = ?", (pick_id,))
        except sqlite3.Error as exc:
            self._log.warning("state.persistence.save.failed", method="delete_pick", error=str(exc))
            return
        self._log.debug("state.persistence.sqlite.delete_pick.ok", pick_id=pick_id)

    def upsert_region(self, region: Region) -> None:
        """Insert-or-replace one region keyed on ``region_id``. Idempotent."""
        try:
            with self._conn:
                self._conn.execute(
                    self._UPSERT_REGION,
                    (region.region_id, region.origin_session, region.model_dump_json()),
                )
        except sqlite3.Error as exc:
            self._log.warning("state.persistence.save.failed", method="upsert_region", error=str(exc))
            return
        self._log.debug("state.persistence.sqlite.upsert_region.ok", region_id=region.region_id)

    def delete_region(self, region_id: str) -> None:
        """Delete one region by ``region_id``. Idempotent (no-op if absent)."""
        try:
            with self._conn:
                self._conn.execute("DELETE FROM regions WHERE region_id = ?", (region_id,))
        except sqlite3.Error as exc:
            self._log.warning("state.persistence.save.failed", method="delete_region", error=str(exc))
            return
        self._log.debug("state.persistence.sqlite.delete_region.ok", region_id=region_id)

    def upsert_relation(self, relation: Relation) -> None:
        """Insert-or-replace one relation keyed on ``relation_id``. Idempotent."""
        try:
            with self._conn:
                self._conn.execute(
                    self._UPSERT_RELATION,
                    (relation.relation_id, relation.origin_session, relation.model_dump_json()),
                )
        except sqlite3.Error as exc:
            self._log.warning("state.persistence.save.failed", method="upsert_relation", error=str(exc))
            return
        self._log.debug("state.persistence.sqlite.upsert_relation.ok", relation_id=relation.relation_id)

    def delete_relation(self, relation_id: str) -> None:
        """Delete one relation by ``relation_id``. Idempotent (no-op if absent)."""
        try:
            with self._conn:
                self._conn.execute("DELETE FROM relations WHERE relation_id = ?", (relation_id,))
        except sqlite3.Error as exc:
            self._log.warning("state.persistence.save.failed", method="delete_relation", error=str(exc))
            return
        self._log.debug("state.persistence.sqlite.delete_relation.ok", relation_id=relation_id)

    def save_inspector_state(self, inspector_state: InspectorState) -> None:
        """Bulk-seed the inspector entities (upsert-all + prune-missing).

        Seed/initialisation helper only — see protocol docstring. Runs in a
        single transaction: upsert-all + delete-missing for picks / regions /
        relations. **Runtime mutations use the per-entity methods instead**;
        this whole-set overwrite is reserved for one-shot seeding where a single
        writer owns the entire set.

        Write failures (``sqlite3.Error``) are swallowed and logged as warnings.
        """
        try:
            with self._conn:
                # --- picks ---
                for pick in inspector_state.picks:
                    self._conn.execute(
                        self._UPSERT_PICK,
                        (pick.pick_id, pick.origin_session, pick.url, pick.model_dump_json()),
                    )
                if inspector_state.picks:
                    placeholders = ",".join("?" * len(inspector_state.picks))
                    self._conn.execute(
                        f"DELETE FROM picks WHERE pick_id NOT IN ({placeholders})",
                        [p.pick_id for p in inspector_state.picks],
                    )
                else:
                    self._conn.execute("DELETE FROM picks")

                # --- regions ---
                for region in inspector_state.regions:
                    self._conn.execute(
                        self._UPSERT_REGION,
                        (region.region_id, region.origin_session, region.model_dump_json()),
                    )
                if inspector_state.regions:
                    placeholders = ",".join("?" * len(inspector_state.regions))
                    self._conn.execute(
                        f"DELETE FROM regions WHERE region_id NOT IN ({placeholders})",
                        [r.region_id for r in inspector_state.regions],
                    )
                else:
                    self._conn.execute("DELETE FROM regions")

                # --- relations ---
                for relation in inspector_state.relations:
                    self._conn.execute(
                        self._UPSERT_RELATION,
                        (relation.relation_id, relation.origin_session, relation.model_dump_json()),
                    )
                if inspector_state.relations:
                    placeholders = ",".join("?" * len(inspector_state.relations))
                    self._conn.execute(
                        f"DELETE FROM relations WHERE relation_id NOT IN ({placeholders})",
                        [r.relation_id for r in inspector_state.relations],
                    )
                else:
                    self._conn.execute("DELETE FROM relations")

        except sqlite3.Error as exc:
            self._log.warning("state.persistence.save.failed", method="save_inspector_state", error=str(exc))
            return

        self._log.debug(
            "state.persistence.sqlite.save_inspector.ok",
            picks=len(inspector_state.picks),
            regions=len(inspector_state.regions),
            relations=len(inspector_state.relations),
        )


    # ------------------------------------------------------------------
    # Recording-domain (sub-plan 01)
    # ------------------------------------------------------------------

    _UPSERT_RECORDING = """
        INSERT INTO recordings (
            recording_id, origin_session, payload_json, status,
            started_at_ms, ended_at_ms, updated_at,
            has_voice_over, audio_path, transcription_status, transcription_error
        )
        VALUES (?, ?, ?, ?, ?, ?, datetime('now'), ?, ?, ?, ?)
        ON CONFLICT (recording_id) DO UPDATE SET
            origin_session       = excluded.origin_session,
            payload_json         = excluded.payload_json,
            status               = excluded.status,
            started_at_ms        = excluded.started_at_ms,
            ended_at_ms          = excluded.ended_at_ms,
            updated_at           = excluded.updated_at,
            has_voice_over       = excluded.has_voice_over,
            audio_path           = excluded.audio_path,
            transcription_status = excluded.transcription_status,
            transcription_error  = excluded.transcription_error
    """

    def upsert_recording(self, recording: "Recording") -> None:
        """Insert-or-replace one recording keyed on ``recording_id``. Idempotent.

        Stores recording metadata + voice-over fields; timeline entries are NOT
        written by this method — use ``append_timeline_entry`` for runtime event appends.
        """
        # Store only the meta fields (no entries) so that a bulk re-seed does
        # not accidentally resurrect or duplicate timeline_entries.
        import json

        meta_payload = json.dumps(
            {
                "recording_id": recording.recording_id,
                "name": recording.name,
                "description": recording.description,
                "origin_session": recording.origin_session,
            }
        )
        try:
            with self._conn:
                self._conn.execute(
                    self._UPSERT_RECORDING,
                    (
                        recording.recording_id,
                        recording.origin_session,
                        meta_payload,
                        recording.status,
                        recording.started_at_ms,
                        recording.ended_at_ms,
                        1 if recording.has_voice_over else 0,
                        recording.audio_path,
                        recording.transcription_status,
                        recording.transcription_error,
                    ),
                )
        except sqlite3.Error as exc:
            self._log.warning("state.persistence.save.failed", method="upsert_recording", error=str(exc))
            return
        self._log.debug("state.persistence.sqlite.upsert_recording.ok", recording_id=recording.recording_id)

    def delete_recording(self, recording_id: str) -> None:
        """Delete recording + all timeline_entries (cascade). Idempotent."""
        try:
            with self._conn:
                # Delete entries first (no FK cascade in SQLite without PRAGMA foreign_keys)
                self._conn.execute("DELETE FROM timeline_entries WHERE recording_id = ?", (recording_id,))
                self._conn.execute("DELETE FROM recordings WHERE recording_id = ?", (recording_id,))
        except sqlite3.Error as exc:
            self._log.warning("state.persistence.save.failed", method="delete_recording", error=str(exc))
            return
        self._log.debug("state.persistence.sqlite.delete_recording.ok", recording_id=recording_id)

    def load_recordings(self) -> "list[Recording]":
        """Return all recordings with their timeline entries, ordered by started_at_ms.

        Reads voice-over columns (has_voice_over, audio_path, transcription_status,
        transcription_error) via COALESCE to remain forward-compatible with rows that
        predate the voice-over migration (columns default to 0 / NULL / 'none').
        """
        import json

        from pydantic import TypeAdapter

        from frontprompt.state.state import Recording, TimelineEntry

        ta: TypeAdapter[TimelineEntry] = TypeAdapter(TimelineEntry)

        rec_rows = self._conn.execute(
            "SELECT recording_id, origin_session, payload_json, status, started_at_ms, ended_at_ms, "
            "COALESCE(has_voice_over, 0), audio_path, COALESCE(transcription_status, 'none'), transcription_error "
            "FROM recordings ORDER BY started_at_ms ASC"
        ).fetchall()

        results: list[Recording] = []
        for row in rec_rows:
            (
                recording_id,
                origin_session,
                payload_json,
                status,
                started_at_ms,
                ended_at_ms,
                has_voice_over_int,
                audio_path,
                transcription_status,
                transcription_error,
            ) = row
            try:
                meta = json.loads(payload_json)
            except (json.JSONDecodeError, ValueError) as exc:
                self._log.warning("state.persistence.load.row_skipped", table="recordings", error=str(exc))
                continue

            # Load timeline entries for this recording, ordered by seq
            entry_rows = self._conn.execute(
                "SELECT payload_json FROM timeline_entries WHERE recording_id = ? ORDER BY seq ASC",
                (recording_id,),
            ).fetchall()

            entries = []
            for entry_row in entry_rows:
                try:
                    entries.append(ta.validate_json(entry_row[0]))
                except (json.JSONDecodeError, Exception) as exc:
                    self._log.warning(
                        "state.persistence.load.row_skipped",
                        table="timeline_entries",
                        recording_id=recording_id,
                        error=str(exc),
                    )
                    # corrupt rows skipped — resilience convention (mirrors picks/regions)

            results.append(
                Recording(
                    recording_id=recording_id,
                    name=meta.get("name", ""),
                    description=meta.get("description", ""),
                    status=status,
                    started_at_ms=started_at_ms,
                    ended_at_ms=ended_at_ms,
                    entries=entries,
                    origin_session=origin_session,
                    has_voice_over=bool(has_voice_over_int),
                    audio_path=audio_path,
                    transcription_status=transcription_status,
                    transcription_error=transcription_error,
                )
            )

        self._log.debug("state.persistence.sqlite.load_recordings.ok", count=len(results))
        return results

    _UPSERT_TIMELINE_ENTRY = """
        INSERT INTO timeline_entries (recording_id, seq, kind, timestamp_ms, payload_json)
        VALUES (?, ?, ?, ?, ?)
        ON CONFLICT (recording_id, seq) DO UPDATE SET
            kind         = excluded.kind,
            timestamp_ms = excluded.timestamp_ms,
            payload_json = excluded.payload_json
    """

    def append_timeline_entry(self, recording_id: str, entry: "TimelineEntry") -> None:
        """Append a single timeline entry to an existing recording. Append-only at runtime."""
        try:
            with self._conn:
                self._conn.execute(
                    self._UPSERT_TIMELINE_ENTRY,
                    (recording_id, entry.seq, entry.kind, entry.timestamp_ms, entry.model_dump_json()),
                )
        except sqlite3.Error as exc:
            self._log.warning("state.persistence.save.failed", method="append_timeline_entry", error=str(exc))
            return
        self._log.debug(
            "state.persistence.sqlite.append_timeline_entry.ok",
            recording_id=recording_id,
            seq=entry.seq,
        )

    def update_recording_meta(self, recording_id: str, name: str, description: str) -> None:
        """Update only name + description of an existing recording."""
        import json

        # Read current meta payload, update fields, write back
        row = self._conn.execute(
            "SELECT payload_json FROM recordings WHERE recording_id = ?", (recording_id,)
        ).fetchone()
        if row is None:
            self._log.warning("state.persistence.update_recording_meta.unknown", recording_id=recording_id)
            return
        try:
            meta = json.loads(row[0])
        except json.JSONDecodeError:
            meta = {}
        meta["name"] = name
        meta["description"] = description
        try:
            with self._conn:
                self._conn.execute(
                    "UPDATE recordings SET payload_json = ?, updated_at = datetime('now') WHERE recording_id = ?",
                    (json.dumps(meta), recording_id),
                )
        except sqlite3.Error as exc:
            self._log.warning("state.persistence.save.failed", method="update_recording_meta", error=str(exc))
            return
        self._log.debug("state.persistence.sqlite.update_recording_meta.ok", recording_id=recording_id)

    def mark_recording_stopped(self, recording_id: str, ended_at_ms: int) -> None:
        """Set status='stopped' and ended_at_ms. Idempotent."""
        try:
            with self._conn:
                self._conn.execute(
                    "UPDATE recordings SET status = 'stopped', ended_at_ms = ?, updated_at = datetime('now') "
                    "WHERE recording_id = ?",
                    (ended_at_ms, recording_id),
                )
        except sqlite3.Error as exc:
            self._log.warning("state.persistence.save.failed", method="mark_recording_stopped", error=str(exc))
            return
        self._log.debug("state.persistence.sqlite.mark_recording_stopped.ok", recording_id=recording_id)

    # ------------------------------------------------------------------
    # Voice-over settings (sub-plan 01)
    # ------------------------------------------------------------------

    _UPSERT_SETTING = """
        INSERT INTO settings (key, value) VALUES (?, ?)
        ON CONFLICT (key) DO UPDATE SET value = excluded.value
    """

    def save_settings(self, settings: "SettingsState") -> None:
        """Persist durable voice-over settings to the settings key-value table.

        Writes two rows: ``voice_over_enabled`` and ``selected_transcription_backend_id``.
        Idempotent (ON CONFLICT DO UPDATE). Write failures are swallowed with a warning.
        """
        try:
            with self._conn:
                self._conn.execute(
                    self._UPSERT_SETTING,
                    ("voice_over_enabled", "1" if settings.voice_over_enabled else "0"),
                )
                self._conn.execute(
                    self._UPSERT_SETTING,
                    (
                        "selected_transcription_backend_id",
                        settings.selected_transcription_backend_id or "",
                    ),
                )
        except sqlite3.Error as exc:
            self._log.warning("state.persistence.save.failed", method="save_settings", error=str(exc))
            return
        self._log.debug("state.persistence.sqlite.save_settings.ok")

    def load_settings(self) -> "SettingsState | None":
        """Load voice-over settings from the settings key-value table.

        Returns ``None`` when neither ``voice_over_enabled`` nor
        ``selected_transcription_backend_id`` rows exist yet.
        """
        from frontprompt.state.state import SettingsState

        rows = {
            row[0]: row[1]
            for row in self._conn.execute(
                "SELECT key, value FROM settings WHERE key IN (?, ?)",
                ("voice_over_enabled", "selected_transcription_backend_id"),
            ).fetchall()
        }
        if not rows:
            self._log.debug("state.persistence.sqlite.load_settings.empty")
            return None

        voice_over_enabled = rows.get("voice_over_enabled", "0") == "1"
        raw_backend = rows.get("selected_transcription_backend_id", "")
        selected_transcription_backend_id: str | None = raw_backend if raw_backend else None

        self._log.debug("state.persistence.sqlite.load_settings.hit")
        return SettingsState(
            voice_over_enabled=voice_over_enabled,
            selected_transcription_backend_id=selected_transcription_backend_id,
        )

    def save_mic_device_id(self, device_id: int | None) -> None:
        """Persist selected microphone device id to the settings key-value table.

        ``None`` clears the preference (reverts to system default).
        Idempotent. Write failures are swallowed with a warning.
        """
        value = str(device_id) if device_id is not None else ""
        try:
            with self._conn:
                self._conn.execute(self._UPSERT_SETTING, ("selected_mic_device_id", value))
        except sqlite3.Error as exc:
            self._log.warning("state.persistence.save.failed", method="save_mic_device_id", error=str(exc))
            return
        self._log.debug("state.persistence.sqlite.save_mic_device_id.ok", device_id=device_id)

    def load_mic_device_id(self) -> int | None:
        """Load persisted microphone device id. Returns None when not set."""
        row = self._conn.execute(
            "SELECT value FROM settings WHERE key = 'selected_mic_device_id'"
        ).fetchone()
        if row is None or not row[0]:
            return None
        try:
            return int(row[0])
        except (ValueError, TypeError):
            self._log.warning("state.persistence.sqlite.load_mic_device_id.invalid_value", raw=row[0])
            return None

    def save_mlx_whisper_model_id(self, model_id: str | None) -> None:
        """Persist selected mlx-whisper model id to the settings key-value table.

        ``None`` clears the preference (reverts to default model).
        Idempotent. Write failures are swallowed with a warning.
        Schema 0.11.0+.
        """
        value = model_id if model_id is not None else ""
        try:
            with self._conn:
                self._conn.execute(self._UPSERT_SETTING, ("mlx_whisper_model_id", value))
        except sqlite3.Error as exc:
            self._log.warning("state.persistence.save.failed", method="save_mlx_whisper_model_id", error=str(exc))
            return
        self._log.debug("state.persistence.sqlite.save_mlx_whisper_model_id.ok", model_id=model_id)

    def load_mlx_whisper_model_id(self) -> str | None:
        """Load persisted mlx-whisper model id. Returns None when not set.

        Schema 0.11.0+.
        """
        row = self._conn.execute(
            "SELECT value FROM settings WHERE key = 'mlx_whisper_model_id'"
        ).fetchone()
        if row is None or not row[0]:
            return None
        return row[0]

    # ------------------------------------------------------------------
    # Replay-report domain (sub-plan 01)
    # ------------------------------------------------------------------

    _UPSERT_REPLAY_REPORT = """
        INSERT INTO replay_reports (
            replay_id, recording_id, status, started_at_ms, ended_at_ms,
            parameters_json, step_results_json, error, origin_session, updated_at
        )
        VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, datetime('now'))
        ON CONFLICT (replay_id) DO UPDATE SET
            recording_id      = excluded.recording_id,
            status            = excluded.status,
            started_at_ms     = excluded.started_at_ms,
            ended_at_ms       = excluded.ended_at_ms,
            parameters_json   = excluded.parameters_json,
            step_results_json = excluded.step_results_json,
            error             = excluded.error,
            origin_session    = excluded.origin_session,
            updated_at        = excluded.updated_at
    """

    def save_replay_report(self, report: "ReplayReport") -> None:
        """Insert-or-replace one ReplayReport keyed on replay_id.

        JSON blobs for ``parameters`` and ``step_results`` (WAL pattern
        mirroring the recording domain's upsert_recording / append_timeline_entry).
        Write failures (``sqlite3.Error``) are swallowed and logged as warnings.
        """
        import json

        parameters_json = json.dumps(report.parameters)
        step_results_json = json.dumps([s.model_dump() for s in report.step_results])
        try:
            with self._conn:
                self._conn.execute(
                    self._UPSERT_REPLAY_REPORT,
                    (
                        report.replay_id,
                        report.recording_id,
                        report.status,
                        report.started_at_ms,
                        report.ended_at_ms,
                        parameters_json,
                        step_results_json,
                        report.error,
                        report.origin_session,
                    ),
                )
        except sqlite3.Error as exc:
            self._log.warning("state.persistence.save.failed", method="save_replay_report", error=str(exc))
            return
        self._log.debug("state.persistence.sqlite.save_replay_report.ok", replay_id=report.replay_id)

    def get_replay_report(self, replay_id: str) -> "ReplayReport | None":
        """Retrieve a ReplayReport by replay_id. Returns None when not found."""
        import json

        from frontprompt.state.state import ReplayReport, ReplayStepResult

        row = self._conn.execute(
            "SELECT replay_id, recording_id, status, started_at_ms, ended_at_ms, "
            "parameters_json, step_results_json, error, origin_session "
            "FROM replay_reports WHERE replay_id = ?",
            (replay_id,),
        ).fetchone()
        if row is None:
            return None

        r_id, recording_id, status, started_at_ms, ended_at_ms, parameters_json, step_results_json, error, origin_session = row

        try:
            parameters = json.loads(parameters_json)
        except (json.JSONDecodeError, ValueError):
            parameters = {}

        step_results: list[ReplayStepResult] = []
        try:
            raw_steps = json.loads(step_results_json)
            for raw in raw_steps:
                try:
                    step_results.append(ReplayStepResult.model_validate(raw))
                except Exception as exc:
                    self._log.warning(
                        "state.persistence.load.row_skipped",
                        table="replay_reports.step_results",
                        replay_id=replay_id,
                        error=str(exc),
                    )
        except (json.JSONDecodeError, ValueError) as exc:
            self._log.warning(
                "state.persistence.load.row_skipped",
                table="replay_reports",
                replay_id=replay_id,
                error=str(exc),
            )

        return ReplayReport(
            replay_id=r_id,
            recording_id=recording_id,
            parameters=parameters,
            status=status,
            started_at_ms=started_at_ms,
            ended_at_ms=ended_at_ms,
            step_results=step_results,
            error=error,
            origin_session=origin_session,
        )

    def list_replay_reports_meta(self, recording_id: str | None = None) -> "list[ReplayReportMeta]":
        """Return lightweight ReplayReportMeta list, optionally filtered by recording_id.

        ``step_count``, ``passed_assertions``, and ``failed_assertions`` are derived
        from the stored step_results JSON blob.
        """
        import json

        from frontprompt.state.state import ReplayReportMeta, ReplayStepResult

        if recording_id is not None:
            rows = self._conn.execute(
                "SELECT replay_id, recording_id, status, started_at_ms, ended_at_ms, step_results_json "
                "FROM replay_reports WHERE recording_id = ? ORDER BY started_at_ms ASC",
                (recording_id,),
            ).fetchall()
        else:
            rows = self._conn.execute(
                "SELECT replay_id, recording_id, status, started_at_ms, ended_at_ms, step_results_json "
                "FROM replay_reports ORDER BY started_at_ms ASC"
            ).fetchall()

        results: list[ReplayReportMeta] = []
        for row in rows:
            r_id, rec_id, status, started_at_ms, ended_at_ms, step_results_json = row
            step_count = 0
            passed = 0
            failed = 0
            try:
                raw_steps = json.loads(step_results_json)
                step_count = len(raw_steps)
                for raw in raw_steps:
                    try:
                        step = ReplayStepResult.model_validate(raw)
                        if step.assertion_passed is True:
                            passed += 1
                        elif step.assertion_passed is False:
                            failed += 1
                    except Exception:
                        pass
            except (json.JSONDecodeError, ValueError):
                pass

            results.append(
                ReplayReportMeta(
                    replay_id=r_id,
                    recording_id=rec_id,
                    status=status,
                    started_at_ms=started_at_ms,
                    ended_at_ms=ended_at_ms,
                    step_count=step_count,
                    passed_assertions=passed,
                    failed_assertions=failed,
                )
            )
        self._log.debug("state.persistence.sqlite.list_replay_reports_meta.ok", count=len(results))
        return results

# ---------------------------------------------------------------------------
# Factory
# ---------------------------------------------------------------------------


def make_persistence(db_path: Path | None = None) -> StatePersistence:
    """Factory for the disk-backed persistence provider.

    Tries to construct :class:`SqlitePersistence` at ``db_path`` (resolved via
    :func:`~frontprompt.state.persistence.paths.state_db_path` when ``None``).
    On any :class:`sqlite3.Error` or :class:`OSError` (e.g. unwritable parent
    directory) it falls back to
    :class:`~frontprompt.state.persistence.in_memory.InMemoryPersistence`,
    logs a warning, and never raises.

    Returns:
        A concrete :class:`~frontprompt.state.persistence.protocol.StatePersistence`
        implementation — either :class:`SqlitePersistence` or
        :class:`~frontprompt.state.persistence.in_memory.InMemoryPersistence`.
    """
    from frontprompt.state.persistence.in_memory import InMemoryPersistence
    from frontprompt.state.persistence.paths import state_db_path

    resolved = db_path if db_path is not None else state_db_path()
    try:
        return SqlitePersistence(resolved)
    except (sqlite3.Error, OSError) as exc:
        _LOG.warning(
            "state.persistence.init.degraded_to_in_memory",
            db_path=str(resolved),
            error=str(exc),
        )
        return InMemoryPersistence()


__all__ = ["SqlitePersistence", "make_persistence"]
