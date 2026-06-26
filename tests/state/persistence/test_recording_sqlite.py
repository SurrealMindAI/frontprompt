"""Tests für SqlitePersistence — Recording-Domäne (sub-plan 01, Section 3).

Deckt: load_recordings, upsert_recording, append_timeline_entry,
mark_recording_stopped, update_recording_meta, delete_recording,
Resilience (corrupt JSON), WAL concurrent-read.
"""

from __future__ import annotations

from pathlib import Path

import pytest


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _make_recording(recording_id: str = "rec-001", name: str = "Test Recording") -> "Recording":
    from frontprompt.state.state import Recording

    return Recording(
        recording_id=recording_id,
        name=name,
        description="A test recording",
        status="active",
        started_at_ms=1_700_000_000_000,
        origin_session="sess-test",
    )


def _make_page_event(seq: int = 0, timestamp_ms: int = 1000) -> "PageEventEntry":
    from frontprompt.state.state import PageEventEntry

    return PageEventEntry(
        kind="page_event",
        seq=seq,
        timestamp_ms=timestamp_ms,
        event_type="click",
        target="button#submit",
        target_path=["html", "body", "button"],
        default_prevented=False,
        key=None,
    )


def _make_nav_entry(seq: int = 0, timestamp_ms: int = 2000) -> "NavigationEntry":
    from frontprompt.state.state import NavigationEntry

    return NavigationEntry(
        kind="navigation",
        seq=seq,
        timestamp_ms=timestamp_ms,
        from_url="https://a.com",
        to_url="https://b.com",
    )


# ---------------------------------------------------------------------------
# load_recordings — empty
# ---------------------------------------------------------------------------


def test_load_recordings_empty_db(tmp_path: Path) -> None:
    """load_recordings() auf leerer DB gibt [] zurück."""
    from frontprompt.state.persistence.sqlite import SqlitePersistence

    db = SqlitePersistence(tmp_path / "fp.db")
    assert db.load_recordings() == []


# ---------------------------------------------------------------------------
# upsert_recording + load_recordings — round-trip
# ---------------------------------------------------------------------------


def test_upsert_and_load_recording_roundtrip(tmp_path: Path) -> None:
    """upsert_recording + load_recordings round-trip preserves alle Felder."""
    from frontprompt.state.persistence.sqlite import SqlitePersistence
    from frontprompt.state.state import Recording

    db_path = tmp_path / "fp.db"
    rec = _make_recording("rec-rt-001", "My Recording")

    SqlitePersistence(db_path).upsert_recording(rec)

    loaded = SqlitePersistence(db_path).load_recordings()
    assert len(loaded) == 1
    loaded_rec = loaded[0]
    assert isinstance(loaded_rec, Recording)
    assert loaded_rec.recording_id == "rec-rt-001"
    assert loaded_rec.name == "My Recording"
    assert loaded_rec.description == "A test recording"
    assert loaded_rec.status == "active"
    assert loaded_rec.started_at_ms == 1_700_000_000_000
    assert loaded_rec.origin_session == "sess-test"
    assert loaded_rec.entries == []


def test_upsert_recording_is_idempotent(tmp_path: Path) -> None:
    """Zweiter upsert mit selber recording_id überschreibt (last-write-wins)."""
    from frontprompt.state.persistence.sqlite import SqlitePersistence

    db_path = tmp_path / "fp.db"
    db = SqlitePersistence(db_path)

    rec1 = _make_recording("rec-idem", "Original")
    db.upsert_recording(rec1)

    from frontprompt.state.state import Recording

    rec2 = Recording(
        recording_id="rec-idem",
        name="Updated",
        status="active",
        started_at_ms=1000,
    )
    db.upsert_recording(rec2)

    loaded = db.load_recordings()
    assert len(loaded) == 1
    assert loaded[0].name == "Updated"


# ---------------------------------------------------------------------------
# append_timeline_entry
# ---------------------------------------------------------------------------


def test_append_timeline_entry_appends(tmp_path: Path) -> None:
    """append_timeline_entry hängt an Einträge an — via load_recordings sichtbar."""
    from frontprompt.state.persistence.sqlite import SqlitePersistence

    db_path = tmp_path / "fp.db"
    db = SqlitePersistence(db_path)
    rec = _make_recording("rec-append")
    db.upsert_recording(rec)

    entry = _make_page_event(seq=0, timestamp_ms=1000)
    db.append_timeline_entry("rec-append", entry)

    loaded = db.load_recordings()
    assert len(loaded) == 1
    assert len(loaded[0].entries) == 1
    assert loaded[0].entries[0].kind == "page_event"
    assert loaded[0].entries[0].seq == 0


def test_timeline_entries_loaded_in_seq_order(tmp_path: Path) -> None:
    """Timeline-Einträge werden in seq-Reihenfolge geladen."""
    from frontprompt.state.persistence.sqlite import SqlitePersistence

    db_path = tmp_path / "fp.db"
    db = SqlitePersistence(db_path)
    rec = _make_recording("rec-order")
    db.upsert_recording(rec)

    # append out of order to test that DB orders by seq
    nav2 = _make_nav_entry(seq=2, timestamp_ms=3000)
    click0 = _make_page_event(seq=0, timestamp_ms=1000)
    click1 = _make_page_event(seq=1, timestamp_ms=2000)

    db.append_timeline_entry("rec-order", nav2)
    db.append_timeline_entry("rec-order", click0)
    db.append_timeline_entry("rec-order", click1)

    loaded = db.load_recordings()
    entries = loaded[0].entries
    assert len(entries) == 3
    assert [e.seq for e in entries] == [0, 1, 2]


# ---------------------------------------------------------------------------
# mark_recording_stopped
# ---------------------------------------------------------------------------


def test_mark_recording_stopped(tmp_path: Path) -> None:
    """mark_recording_stopped ändert status + ended_at_ms, bewahrt Einträge."""
    from frontprompt.state.persistence.sqlite import SqlitePersistence

    db_path = tmp_path / "fp.db"
    db = SqlitePersistence(db_path)
    rec = _make_recording("rec-stop")
    db.upsert_recording(rec)
    db.append_timeline_entry("rec-stop", _make_page_event(seq=0))

    db.mark_recording_stopped("rec-stop", ended_at_ms=9_999_999_999)

    loaded = db.load_recordings()
    assert len(loaded) == 1
    stopped = loaded[0]
    assert stopped.status == "stopped"
    assert stopped.ended_at_ms == 9_999_999_999
    # entries preserved
    assert len(stopped.entries) == 1


# ---------------------------------------------------------------------------
# update_recording_meta
# ---------------------------------------------------------------------------


def test_update_recording_meta(tmp_path: Path) -> None:
    """update_recording_meta ändert nur name + description."""
    from frontprompt.state.persistence.sqlite import SqlitePersistence

    db_path = tmp_path / "fp.db"
    db = SqlitePersistence(db_path)
    rec = _make_recording("rec-rename", "Original Name")
    db.upsert_recording(rec)

    db.update_recording_meta("rec-rename", name="New Name", description="New desc")

    loaded = db.load_recordings()
    assert len(loaded) == 1
    updated = loaded[0]
    assert updated.name == "New Name"
    assert updated.description == "New desc"
    # status unchanged
    assert updated.status == "active"


# ---------------------------------------------------------------------------
# delete_recording
# ---------------------------------------------------------------------------


def test_delete_recording_removes_recording_and_entries(tmp_path: Path) -> None:
    """delete_recording entfernt das Recording und alle zugehörigen Einträge (cascade)."""
    from frontprompt.state.persistence.sqlite import SqlitePersistence

    db_path = tmp_path / "fp.db"
    db = SqlitePersistence(db_path)
    rec = _make_recording("rec-del")
    db.upsert_recording(rec)
    db.append_timeline_entry("rec-del", _make_page_event(seq=0))
    db.append_timeline_entry("rec-del", _make_nav_entry(seq=1))

    db.delete_recording("rec-del")

    loaded = db.load_recordings()
    assert loaded == []

    # Verify timeline_entries are gone too (cascade)
    import sqlite3

    conn = sqlite3.connect(str(db_path))
    rows = conn.execute("SELECT * FROM timeline_entries WHERE recording_id = ?", ("rec-del",)).fetchall()
    conn.close()
    assert rows == [], f"Expected no timeline_entries after delete, got: {rows}"


def test_delete_recording_idempotent(tmp_path: Path) -> None:
    """delete_recording für unbekannte ID ist ein no-op."""
    from frontprompt.state.persistence.sqlite import SqlitePersistence

    db = SqlitePersistence(tmp_path / "fp.db")
    db.delete_recording("nonexistent-id")  # no exception


# ---------------------------------------------------------------------------
# Resilience — corrupt JSON row skipped with warning
# ---------------------------------------------------------------------------


def test_corrupt_timeline_entry_json_skipped(tmp_path: Path) -> None:
    """Corrupt JSON in timeline_entries wird übersprungen (no crash, warning log)."""
    import sqlite3

    from frontprompt.state.persistence.sqlite import SqlitePersistence

    db_path = tmp_path / "fp.db"
    db = SqlitePersistence(db_path)
    rec = _make_recording("rec-corrupt")
    db.upsert_recording(rec)

    # Inject a corrupt row directly
    conn = sqlite3.connect(str(db_path))
    conn.execute(
        "INSERT INTO timeline_entries (recording_id, seq, kind, timestamp_ms, payload_json) "
        "VALUES (?, ?, ?, ?, ?)",
        ("rec-corrupt", 0, "page_event", 1000, "THIS IS NOT JSON{{{"),
    )
    conn.commit()
    conn.close()

    # Should not raise — corrupt rows are skipped
    loaded = db.load_recordings()
    assert len(loaded) == 1
    assert loaded[0].entries == []  # corrupt row skipped


# ---------------------------------------------------------------------------
# WAL concurrent sessions
# ---------------------------------------------------------------------------


def test_wal_concurrent_sessions(tmp_path: Path) -> None:
    """Zwei SqlitePersistence-Instanzen auf gleicher DB: session A appends, session B reads."""
    from frontprompt.state.persistence.sqlite import SqlitePersistence

    db_path = tmp_path / "fp.db"
    session_a = SqlitePersistence(db_path)
    session_b = SqlitePersistence(db_path)

    rec = _make_recording("rec-wal")
    session_a.upsert_recording(rec)
    session_a.append_timeline_entry("rec-wal", _make_page_event(seq=0))

    loaded = session_b.load_recordings()
    assert len(loaded) == 1
    assert len(loaded[0].entries) == 1
