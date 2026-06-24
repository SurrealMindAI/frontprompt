"""Tests for frontprompt.state.persistence.sqlite — SqlitePersistence schema init + panel state."""

from __future__ import annotations

from pathlib import Path
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from frontprompt.state.state import PanelStateView


def _make_panel_state() -> PanelStateView:
    from frontprompt.state.state import PanelStateView, PanelView

    return PanelStateView(
        top=PanelView(open=True, size=56),
        bottom=PanelView(open=False, size=220),
        left=PanelView(open=True, size=300),
        right=PanelView(open=True, size=340),
    )


def test_init_creates_schema_and_wal(tmp_path: Path) -> None:
    """Constructing SqlitePersistence creates 5 tables + seeds schema_meta + sets WAL."""
    import sqlite3

    from frontprompt.state.persistence.sqlite import SqlitePersistence

    db_path = tmp_path / "fp.db"
    SqlitePersistence(db_path)

    # verify via a fresh raw connection (not via the class under test)
    conn = sqlite3.connect(str(db_path))
    cur = conn.cursor()

    # WAL mode
    row = cur.execute("PRAGMA journal_mode").fetchone()
    assert row is not None
    assert row[0] == "wal", f"Expected journal_mode=wal, got {row[0]!r}"

    # all five tables exist
    tables = {r[0] for r in cur.execute("SELECT name FROM sqlite_master WHERE type='table'").fetchall()}
    expected_tables = {"panel_state", "picks", "regions", "relations", "schema_meta"}
    assert expected_tables <= tables, f"Missing tables: {expected_tables - tables}"

    # schema_meta seeded with version 1
    row = cur.execute("SELECT value FROM schema_meta WHERE key='db_schema_version'").fetchone()
    assert row is not None, "schema_meta row 'db_schema_version' missing"
    assert row[0] == "1", f"Expected value='1', got {row[0]!r}"

    conn.close()


def test_panel_round_trip(tmp_path: Path) -> None:
    """save_panel_state + fresh load returns an equal PanelStateView."""
    from frontprompt.state.persistence.sqlite import SqlitePersistence

    db_path = tmp_path / "fp.db"
    original = _make_panel_state()

    # save via first instance
    SqlitePersistence(db_path).save_panel_state(original)

    # load via a fresh second instance to prove disk persistence
    loaded = SqlitePersistence(db_path).load_panel_state()
    assert loaded is not None, "load_panel_state returned None after save"
    assert loaded == original, f"Round-trip mismatch:\noriginal={original!r}\nloaded={loaded!r}"


def test_load_panel_empty_returns_none(tmp_path: Path) -> None:
    """load_panel_state on a fresh DB (no save) returns None."""
    from frontprompt.state.persistence.sqlite import SqlitePersistence

    db_path = tmp_path / "fp.db"
    result = SqlitePersistence(db_path).load_panel_state()
    assert result is None, f"Expected None on empty DB, got {result!r}"
