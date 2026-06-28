"""SqlitePersistence error-path tests.

Tests the sqlite3.Error exception handlers in upsert/delete methods.
These paths log a warning and return without raising — they are the
resilience contract for corrupted/locked databases.

Strategy: replace p._conn with a MagicMock whose execute() raises OperationalError.
The mock's __exit__ returns False so the exception propagates out of the `with conn:`
block and into the outer `except sqlite3.Error` handler — which swallows it.

sqlite3.Connection.execute is a read-only C-extension attribute, so patch.object
cannot be used directly; replacing the whole connection is the clean alternative.
"""

from __future__ import annotations

import json
import sqlite3
from pathlib import Path
from unittest.mock import MagicMock

import pytest


def _broken_conn() -> MagicMock:
    """MagicMock for sqlite3.Connection that raises OperationalError on execute.

    __exit__.return_value = False ensures the exception is NOT suppressed by the
    `with self._conn:` context manager — it propagates to the outer try/except.
    """
    mock = MagicMock()
    mock.__exit__.return_value = False  # don't suppress — let sqlite3.Error propagate
    mock.execute.side_effect = sqlite3.OperationalError("simulated failure")
    return mock


def _make_fresh_persistence(tmp_path: Path):  # type: ignore[no-untyped-def]
    from frontprompt.state.persistence.sqlite import SqlitePersistence

    return SqlitePersistence(tmp_path / "test.db")


def _make_pick(pick_id: str):  # type: ignore[no-untyped-def]
    from frontprompt.state.state import ElementFingerprint, ElementRect, Pick, PickElement

    return Pick(
        pick_id=pick_id,
        url="https://example.com",
        timestamp_ms=1000,
        element=PickElement(
            selector=f"#{pick_id}",
            fingerprint=ElementFingerprint(tag="div"),
            text_snippet="",
            rect=ElementRect(x=0, y=0, width=10, height=10),
        ),
    )


def _make_region(region_id: str):  # type: ignore[no-untyped-def]
    from frontprompt.state.state import ElementRect, Region

    return Region(
        region_id=region_id,
        rect=ElementRect(x=0, y=0, width=100, height=100),
        timestamp_ms=1000,
    )


def _make_relation(relation_id: str):  # type: ignore[no-untyped-def]
    from frontprompt.state.state import Relation

    return Relation(
        relation_id=relation_id,
        source_id="pick-a",
        source_kind="pick",
        target_id="pick-b",
        target_kind="pick",
        kind="relates_to",
        timestamp_ms=1000,
    )


def _make_recording(recording_id: str):  # type: ignore[no-untyped-def]
    from frontprompt.state.state import Recording

    return Recording(
        recording_id=recording_id,
        name="Test Recording",
        status="active",
        started_at_ms=1000,
    )


def _make_panel_state():  # type: ignore[no-untyped-def]
    from frontprompt.state.state import PanelStateView, PanelView

    return PanelStateView(
        top=PanelView(open=False, size=100),
        bottom=PanelView(open=False, size=100),
        left=PanelView(open=True, size=250),
        right=PanelView(open=True, size=300),
    )


# ── upsert_pick / delete_pick error paths ─────────────────────────────────────


def test_upsert_pick_swallows_sqlite_error(tmp_path: Path) -> None:
    """upsert_pick logs warning and returns on sqlite3.Error."""
    p = _make_fresh_persistence(tmp_path)
    pick = _make_pick("p1")
    p._conn = _broken_conn()
    p.upsert_pick(pick)  # must not raise


def test_delete_pick_swallows_sqlite_error(tmp_path: Path) -> None:
    """delete_pick logs warning and returns on sqlite3.Error."""
    p = _make_fresh_persistence(tmp_path)
    p._conn = _broken_conn()
    p.delete_pick("p1")  # must not raise


# ── upsert_region / delete_region error paths ─────────────────────────────────


def test_upsert_region_swallows_sqlite_error(tmp_path: Path) -> None:
    """upsert_region logs warning and returns on sqlite3.Error."""
    p = _make_fresh_persistence(tmp_path)
    region = _make_region("r1")
    p._conn = _broken_conn()
    p.upsert_region(region)  # must not raise


def test_delete_region_swallows_sqlite_error(tmp_path: Path) -> None:
    """delete_region logs warning and returns on sqlite3.Error."""
    p = _make_fresh_persistence(tmp_path)
    p._conn = _broken_conn()
    p.delete_region("r1")  # must not raise


# ── upsert_relation / delete_relation error paths ────────────────────────────


def test_upsert_relation_swallows_sqlite_error(tmp_path: Path) -> None:
    """upsert_relation logs warning and returns on sqlite3.Error."""
    p = _make_fresh_persistence(tmp_path)
    relation = _make_relation("rel1")
    p._conn = _broken_conn()
    p.upsert_relation(relation)  # must not raise


def test_delete_relation_swallows_sqlite_error(tmp_path: Path) -> None:
    """delete_relation logs warning and returns on sqlite3.Error."""
    p = _make_fresh_persistence(tmp_path)
    p._conn = _broken_conn()
    p.delete_relation("rel1")  # must not raise


# ── save_inspector_state error path ──────────────────────────────────────────


def test_save_inspector_state_swallows_sqlite_error(tmp_path: Path) -> None:
    """save_inspector_state logs warning and returns on sqlite3.Error."""
    from frontprompt.state.state import InspectorState

    p = _make_fresh_persistence(tmp_path)
    state = InspectorState(picks=[_make_pick("p1")])
    p._conn = _broken_conn()
    p.save_inspector_state(state)  # must not raise


# ── save_panel_state error path ───────────────────────────────────────────────


def test_save_panel_state_swallows_sqlite_error(tmp_path: Path) -> None:
    """save_panel_state logs warning and returns on sqlite3.Error."""
    p = _make_fresh_persistence(tmp_path)
    panel = _make_panel_state()
    p._conn = _broken_conn()
    p.save_panel_state(panel)  # must not raise


# ── upsert_recording / delete_recording error paths ──────────────────────────


def test_upsert_recording_swallows_sqlite_error(tmp_path: Path) -> None:
    """upsert_recording logs warning and returns on sqlite3.Error."""
    p = _make_fresh_persistence(tmp_path)
    recording = _make_recording("rec1")
    p._conn = _broken_conn()
    p.upsert_recording(recording)  # must not raise


def test_delete_recording_swallows_sqlite_error(tmp_path: Path) -> None:
    """delete_recording logs warning and returns on sqlite3.Error."""
    p = _make_fresh_persistence(tmp_path)
    p._conn = _broken_conn()
    p.delete_recording("rec1")  # must not raise


# ── append_timeline_entry error path ─────────────────────────────────────────


def test_append_timeline_entry_swallows_sqlite_error(tmp_path: Path) -> None:
    """append_timeline_entry logs warning and returns on sqlite3.Error."""
    from frontprompt.state.state import NavigationEntry

    p = _make_fresh_persistence(tmp_path)
    entry = NavigationEntry(seq=1, timestamp_ms=1000, from_url="https://a.com", to_url="https://b.com")
    p._conn = _broken_conn()
    p.append_timeline_entry("rec1", entry)  # must not raise


# ── mark_recording_stopped error path ────────────────────────────────────────


def test_mark_recording_stopped_swallows_sqlite_error(tmp_path: Path) -> None:
    """mark_recording_stopped logs warning and returns on sqlite3.Error."""
    p = _make_fresh_persistence(tmp_path)
    p._conn = _broken_conn()
    p.mark_recording_stopped("rec1", 2000)  # must not raise


# ── update_recording_meta paths ───────────────────────────────────────────────


def test_update_recording_meta_unknown_recording_returns_without_error(tmp_path: Path) -> None:
    """update_recording_meta warns and returns when recording_id not found."""
    p = _make_fresh_persistence(tmp_path)
    p.update_recording_meta("nonexistent-rec", "New Name", "New Desc")  # must not raise


def test_update_recording_meta_with_corrupt_json(tmp_path: Path) -> None:
    """update_recording_meta recovers from corrupt payload_json in existing row."""
    from frontprompt.state.persistence.sqlite import SqlitePersistence

    db_path = tmp_path / "test.db"
    p = SqlitePersistence(db_path)
    # Insert a recording with corrupt JSON payload
    with p._conn:
        p._conn.execute(
            "INSERT INTO recordings (recording_id, origin_session, payload_json, status, started_at_ms, updated_at) "
            "VALUES (?, ?, ?, ?, ?, datetime('now'))",
            ("rec-bad-json", None, "CORRUPT JSON", "active", 1000),
        )
    # Should not raise — falls back to empty dict
    p.update_recording_meta("rec-bad-json", "New Name", "New Desc")


# ── save_replay_report error path ─────────────────────────────────────────────


def test_save_replay_report_swallows_sqlite_error(tmp_path: Path) -> None:
    """save_replay_report logs warning and returns on sqlite3.Error."""
    from frontprompt.state.state import ReplayReport

    p = _make_fresh_persistence(tmp_path)
    report = ReplayReport(
        replay_id="rp1",
        recording_id="rec1",
        status="completed",
        started_at_ms=1000,
        ended_at_ms=2000,
    )
    p._conn = _broken_conn()
    p.save_replay_report(report)  # must not raise


# ── load_inspector_state resilience: corrupt rows ────────────────────────────


def test_load_inspector_state_skips_corrupt_pick_rows(tmp_path: Path) -> None:
    """load_inspector_state skips picks rows with invalid JSON — no exception raised."""
    from frontprompt.state.persistence.sqlite import SqlitePersistence

    db_path = tmp_path / "test.db"
    p = SqlitePersistence(db_path)
    with p._conn:
        p._conn.execute(
            "INSERT INTO picks (pick_id, origin_session, url, payload_json, updated_at) "
            "VALUES (?, ?, ?, ?, datetime('now'))",
            ("bad-pick", None, "https://x.com", "NOT VALID JSON {{{{"),
        )
    # Insert one valid pick to ensure the table is non-empty so load_inspector_state returns non-None
    p.upsert_pick(_make_pick("good-pick"))
    state = p.load_inspector_state()
    assert state is not None
    assert all(pick.pick_id != "bad-pick" for pick in state.picks)
    assert any(pick.pick_id == "good-pick" for pick in state.picks)


def test_load_inspector_state_skips_corrupt_region_rows(tmp_path: Path) -> None:
    """load_inspector_state skips region rows with invalid JSON."""
    from frontprompt.state.persistence.sqlite import SqlitePersistence

    db_path = tmp_path / "test.db"
    p = SqlitePersistence(db_path)
    with p._conn:
        p._conn.execute(
            "INSERT INTO regions (region_id, origin_session, payload_json, updated_at) "
            "VALUES (?, ?, ?, datetime('now'))",
            ("bad-region", None, "NOT VALID JSON"),
        )
    # Insert a valid pick to keep table non-empty
    p.upsert_pick(_make_pick("anchor-pick"))
    state = p.load_inspector_state()
    assert state is not None
    assert all(getattr(r, "region_id", None) != "bad-region" for r in state.regions)


def test_load_inspector_state_skips_corrupt_relation_rows(tmp_path: Path) -> None:
    """load_inspector_state skips relation rows with invalid JSON."""
    from frontprompt.state.persistence.sqlite import SqlitePersistence

    db_path = tmp_path / "test.db"
    p = SqlitePersistence(db_path)
    with p._conn:
        p._conn.execute(
            "INSERT INTO relations (relation_id, origin_session, payload_json, updated_at) "
            "VALUES (?, ?, ?, datetime('now'))",
            ("bad-rel", None, "{corrupted"),
        )
    p.upsert_pick(_make_pick("anchor2"))
    state = p.load_inspector_state()
    assert state is not None
    assert all(getattr(r, "relation_id", None) != "bad-rel" for r in state.relations)


# ── load_recordings resilience ────────────────────────────────────────────────


def test_load_recordings_skips_corrupt_payload_json(tmp_path: Path) -> None:
    """load_recordings skips recording rows with invalid payload_json."""
    from frontprompt.state.persistence.sqlite import SqlitePersistence

    db_path = tmp_path / "test.db"
    p = SqlitePersistence(db_path)
    with p._conn:
        p._conn.execute(
            "INSERT INTO recordings (recording_id, origin_session, payload_json, status, started_at_ms, updated_at) "
            "VALUES (?, ?, ?, ?, ?, datetime('now'))",
            ("bad-rec", None, "NOT JSON AT ALL", "active", 1000),
        )
    results = p.load_recordings()
    # Corrupt row is skipped — must not raise
    assert all(r.recording_id != "bad-rec" for r in results)


# ── per-entity happy paths — success log lines not covered by bulk save ───────
# upsert_region, delete_region, upsert_relation, delete_relation are per-entity
# mutation helpers. The existing bulk test (test_sqlite_inspector.py) uses
# save_inspector_state (which bypasses these). These tests exercise the success
# path log statements on lines 333, 343, 356, 366.


def test_upsert_region_success_path(tmp_path: Path) -> None:
    """upsert_region with a real connection succeeds and logs debug (line 333)."""
    p = _make_fresh_persistence(tmp_path)
    p.upsert_region(_make_region("r-happy"))
    # Verify it's persisted
    row = p._conn.execute("SELECT region_id FROM regions WHERE region_id = 'r-happy'").fetchone()
    assert row is not None


def test_delete_region_success_path(tmp_path: Path) -> None:
    """delete_region with a real connection succeeds and logs debug (line 343)."""
    p = _make_fresh_persistence(tmp_path)
    p.upsert_region(_make_region("r-to-del"))
    p.delete_region("r-to-del")
    row = p._conn.execute("SELECT region_id FROM regions WHERE region_id = 'r-to-del'").fetchone()
    assert row is None


def test_upsert_relation_success_path(tmp_path: Path) -> None:
    """upsert_relation with a real connection succeeds and logs debug (line 356)."""
    p = _make_fresh_persistence(tmp_path)
    p.upsert_relation(_make_relation("rel-happy"))
    row = p._conn.execute("SELECT relation_id FROM relations WHERE relation_id = 'rel-happy'").fetchone()
    assert row is not None


def test_delete_relation_success_path(tmp_path: Path) -> None:
    """delete_relation with a real connection succeeds and logs debug (line 366)."""
    p = _make_fresh_persistence(tmp_path)
    p.upsert_relation(_make_relation("rel-to-del"))
    p.delete_relation("rel-to-del")
    row = p._conn.execute("SELECT relation_id FROM relations WHERE relation_id = 'rel-to-del'").fetchone()
    assert row is None


def test_save_inspector_state_empty_picks_clears_all(tmp_path: Path) -> None:
    """save_inspector_state with empty picks executes DELETE FROM picks (line 394)."""
    from frontprompt.state.state import InspectorState

    p = _make_fresh_persistence(tmp_path)
    # First insert a pick to make the table non-empty
    p.upsert_pick(_make_pick("p-pre-existing"))
    # Now save with empty picks — should delete all
    empty_state = InspectorState()
    p.save_inspector_state(empty_state)
    rows = p._conn.execute("SELECT COUNT(*) FROM picks").fetchone()
    assert rows[0] == 0, "save_inspector_state with empty picks should clear the picks table"
