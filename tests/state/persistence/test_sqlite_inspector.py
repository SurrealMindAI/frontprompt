"""Tests for SqlitePersistence — inspector state (save/load, delete-missing, ephemeral reset)."""

from __future__ import annotations

import sqlite3
from pathlib import Path
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from frontprompt.state.state import Pick, Region, Relation

# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _make_pick(pick_id: str, url: str = "https://example.com", origin_session: str | None = None) -> Pick:
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


def _make_region(region_id: str, origin_session: str | None = None) -> Region:
    from frontprompt.state.state import ElementRect, Region

    return Region(
        region_id=region_id,
        rect=ElementRect(x=0.0, y=0.0, width=50.0, height=50.0),
        timestamp_ms=2000,
        origin_session=origin_session,
    )


def _make_relation(relation_id: str, source_id: str, target_id: str, origin_session: str | None = None) -> Relation:
    from frontprompt.state.state import Relation

    return Relation(
        relation_id=relation_id,
        source_id=source_id,
        source_kind="pick",
        target_id=target_id,
        target_kind="pick",
        kind="relates_to",
        timestamp_ms=3000,
        origin_session=origin_session,
    )


# ---------------------------------------------------------------------------
# Tests
# ---------------------------------------------------------------------------


def test_inspector_round_trip(tmp_path: Path) -> None:
    """save_inspector_state + fresh load returns InspectorState equal to original (incl. origin_session)."""
    from frontprompt.state.persistence.sqlite import SqlitePersistence
    from frontprompt.state.state import InspectorState

    db_path = tmp_path / "fp.db"

    pick_a = _make_pick("pick-a", url="https://example.com/a", origin_session="s1")
    pick_b = _make_pick("pick-b", url="https://example.com/b", origin_session=None)
    region = _make_region("region-1", origin_session="s1")
    relation = _make_relation("rel-1", source_id="pick-a", target_id="pick-b", origin_session="s1")

    original = InspectorState(
        picks=[pick_a, pick_b],
        regions=[region],
        relations=[relation],
    )

    # save via first instance
    SqlitePersistence(db_path).save_inspector_state(original)

    # load via fresh second instance — proves disk persistence
    loaded = SqlitePersistence(db_path).load_inspector_state()
    assert loaded is not None, "load_inspector_state returned None after save"

    # entity collections must match
    assert len(loaded.picks) == 2
    assert len(loaded.regions) == 1
    assert len(loaded.relations) == 1

    # picks preserved including origin_session and url
    loaded_by_id = {p.pick_id: p for p in loaded.picks}
    assert loaded_by_id["pick-a"].origin_session == "s1"
    assert loaded_by_id["pick-a"].url == "https://example.com/a"
    assert loaded_by_id["pick-b"].origin_session is None

    # region preserved
    assert loaded.regions[0].region_id == "region-1"
    assert loaded.regions[0].origin_session == "s1"

    # relation preserved
    assert loaded.relations[0].relation_id == "rel-1"
    assert loaded.relations[0].origin_session == "s1"


def test_delete_missing(tmp_path: Path) -> None:
    """save with 3 picks then save with 2 → DB holds exactly 2 rows in picks table."""

    from frontprompt.state.persistence.sqlite import SqlitePersistence
    from frontprompt.state.state import InspectorState

    db_path = tmp_path / "fp.db"

    state_3 = InspectorState(
        picks=[
            _make_pick("p1"),
            _make_pick("p2"),
            _make_pick("p3"),
        ]
    )
    SqlitePersistence(db_path).save_inspector_state(state_3)

    # second save with one pick removed
    state_2 = InspectorState(
        picks=[
            _make_pick("p1"),
            _make_pick("p3"),
        ]
    )
    SqlitePersistence(db_path).save_inspector_state(state_2)

    # verify via raw connection
    conn = sqlite3.connect(str(db_path))
    rows = conn.execute("SELECT pick_id FROM picks ORDER BY pick_id").fetchall()
    conn.close()

    assert len(rows) == 2, f"Expected 2 rows, got {len(rows)}: {rows}"
    pick_ids = {r[0] for r in rows}
    assert pick_ids == {"p1", "p3"}, f"Wrong picks in DB: {pick_ids}"


def test_load_resets_ephemeral_selection(tmp_path: Path) -> None:
    """Loaded InspectorState always has active=False, active_pick_id=None, active_region_id=None."""
    from frontprompt.state.persistence.sqlite import SqlitePersistence
    from frontprompt.state.state import InspectorState

    db_path = tmp_path / "fp.db"

    pick = _make_pick("p-eph")
    region = _make_region("r-eph")

    # state saved with ephemeral selection fields set
    state_with_selection = InspectorState(
        active=True,
        active_pick_id="p-eph",
        active_region_id=None,
        picks=[pick],
        regions=[region],
    )
    SqlitePersistence(db_path).save_inspector_state(state_with_selection)

    loaded = SqlitePersistence(db_path).load_inspector_state()
    assert loaded is not None, "load_inspector_state returned None after save"

    # ephemeral fields reset to model defaults
    assert loaded.active is False, f"Expected active=False, got {loaded.active!r}"
    assert loaded.active_pick_id is None, f"Expected active_pick_id=None, got {loaded.active_pick_id!r}"
    assert loaded.active_region_id is None, f"Expected active_region_id=None, got {loaded.active_region_id!r}"

    # entity collections intact
    assert len(loaded.picks) == 1
    assert len(loaded.regions) == 1


def test_load_inspector_empty_returns_none(tmp_path: Path) -> None:
    """load_inspector_state on a fresh DB (no save) returns None."""
    from frontprompt.state.persistence.sqlite import SqlitePersistence

    db_path = tmp_path / "fp.db"
    result = SqlitePersistence(db_path).load_inspector_state()
    assert result is None, f"Expected None on empty DB, got {result!r}"
