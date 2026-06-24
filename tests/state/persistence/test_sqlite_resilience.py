"""Tests for SqlitePersistence resilience + make_persistence factory.

Covers:
- corrupt payload rows are skipped (valid rows still returned)
- save failures are swallowed and logged (no raise)
- make_persistence falls back to InMemoryPersistence on unwritable path
"""

from __future__ import annotations

from pathlib import Path

# ---------------------------------------------------------------------------
# Helpers (copied from sibling test files — same tiny factory)
# ---------------------------------------------------------------------------


def _make_pick(pick_id: str, url: str = "https://example.com", origin_session: str | None = None) -> object:
    from frontprompt.state.state import ElementFingerprint, ElementRect, Pick, PickElement

    return Pick(
        pick_id=pick_id,
        url=url,
        timestamp_ms=1000,
        element=PickElement(
            selector=f"#{pick_id}",
            fingerprint=ElementFingerprint(tag="div"),
            text_snippet="snippet",
            rect=ElementRect(x=0.0, y=0.0, width=10.0, height=10.0),
        ),
        origin_session=origin_session,
    )


# ---------------------------------------------------------------------------
# Test: corrupt payload row is skipped; valid row still returned
# ---------------------------------------------------------------------------


def test_corrupt_payload_row_skipped(tmp_path: Path) -> None:
    """A picks row with non-JSON payload_json is skipped; valid picks are returned.

    Uses structlog.testing.capture_logs to assert warning is emitted for the
    corrupt row.
    """
    import structlog.testing

    from frontprompt.state.persistence.sqlite import SqlitePersistence

    db_path = tmp_path / "fp.db"

    # bootstrap schema via normal constructor
    sp = SqlitePersistence(db_path)

    # insert a valid pick via the ORM path
    from frontprompt.state.state import InspectorState

    valid_pick = _make_pick("valid-pick")
    sp.save_inspector_state(InspectorState(picks=[valid_pick]))

    # now inject a corrupt row directly via raw sqlite
    import sqlite3

    conn = sqlite3.connect(str(db_path))
    conn.execute(
        """
        INSERT INTO picks (pick_id, origin_session, url, payload_json, updated_at)
        VALUES ('corrupt-pick', NULL, 'https://example.com', 'NOT JSON AT ALL', datetime('now'))
        """
    )
    conn.commit()
    conn.close()

    # load via a fresh instance — corrupt row must be skipped, valid one returned
    sp2 = SqlitePersistence(db_path)
    with structlog.testing.capture_logs() as logs:
        result = sp2.load_inspector_state()

    assert result is not None, "load_inspector_state returned None — expected valid pick"
    assert len(result.picks) == 1, f"Expected 1 pick (valid), got {result.picks!r}"
    assert result.picks[0].pick_id == "valid-pick"

    warning_events = [e for e in logs if e.get("log_level") == "warning"]
    assert len(warning_events) >= 1, f"Expected at least 1 warning for corrupt row, logs={logs}"
    assert any("state.persistence.load.row_skipped" in str(e.get("event", "")) for e in warning_events), (
        f"Expected event 'state.persistence.load.row_skipped' in warnings, got: {warning_events}"
    )


# ---------------------------------------------------------------------------
# Test: make_persistence falls back to InMemoryPersistence on unwritable path
# ---------------------------------------------------------------------------


def test_make_persistence_falls_back_on_unwritable_path(tmp_path: Path) -> None:
    """make_persistence with an uncreatable path returns InMemoryPersistence, no raise."""
    import structlog.testing

    from frontprompt.state.persistence import make_persistence
    from frontprompt.state.persistence.in_memory import InMemoryPersistence

    # /dev/null/subdir cannot be created (file in place of directory)
    bad_path = Path("/dev/null/nonexistent_dir/fp.db")

    with structlog.testing.capture_logs() as logs:
        result = make_persistence(db_path=bad_path)

    assert isinstance(result, InMemoryPersistence), f"Expected InMemoryPersistence fallback, got {type(result)!r}"

    warning_events = [e for e in logs if e.get("log_level") == "warning"]
    assert len(warning_events) >= 1, f"Expected warning for degraded init, logs={logs}"
    assert any("state.persistence.init.degraded_to_in_memory" in str(e.get("event", "")) for e in warning_events), (
        f"Expected event 'state.persistence.init.degraded_to_in_memory', got: {warning_events}"
    )


# ---------------------------------------------------------------------------
# Test: save failure is swallowed and logged
# ---------------------------------------------------------------------------


def test_save_failure_is_swallowed(tmp_path: Path) -> None:
    """save_inspector_state swallows sqlite3.Error and logs a warning — does not raise.

    Forces a real sqlite3.ProgrammingError (subclass of sqlite3.Error) by closing the
    underlying connection before calling save.  sqlite3.Connection.execute is a C-extension
    slot and cannot be monkeypatched; triggering a real error is the reliable approach.
    """
    import structlog.testing

    from frontprompt.state.persistence.sqlite import SqlitePersistence
    from frontprompt.state.state import InspectorState

    db_path = tmp_path / "fp.db"
    sp = SqlitePersistence(db_path)

    state = InspectorState(picks=[_make_pick("p1")])

    # close the underlying connection — any subsequent execute raises
    # sqlite3.ProgrammingError("Cannot operate on a closed database.")
    sp._conn.close()

    with structlog.testing.capture_logs() as logs:
        # must not raise
        sp.save_inspector_state(state)

    warning_events = [e for e in logs if e.get("log_level") == "warning"]
    assert len(warning_events) >= 1, f"Expected warning for save failure, logs={logs}"
    assert any("state.persistence.save.failed" in str(e.get("event", "")) for e in warning_events), (
        f"Expected event 'state.persistence.save.failed', got: {warning_events}"
    )
