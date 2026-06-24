"""StateManager <-> persistence integration tests (Task 6).

Covers the integration core of the sqlite-persistence plan:

- session_id injection (required kwarg, stored on the manager)
- inspector-state load on init (pre-seeded SqlitePersistence DB hydrates picks)
- origin_session stamping on add/update mutations
- steal-on-mutate: a different session_id takes ownership when it mutates an
  existing entity (verified in BOTH the snapshot and the DB row)
- panel + inspector both persist together (reload in a fresh manager)
"""

from __future__ import annotations

from pathlib import Path

import pytest

from frontprompt.state import StateManager
from frontprompt.state.persistence.sqlite import SqlitePersistence
from frontprompt.state.state import (
    ElementFingerprint,
    ElementRect,
    InspectorState,
    Pick,
    PickElement,
)

# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _make_pick(pick_id: str = "p-001", comment: str = "", origin_session: str | None = None) -> Pick:
    return Pick(
        pick_id=pick_id,
        url="https://example.com/",
        timestamp_ms=1_700_000_000_000,
        element=PickElement(
            selector=f"#{pick_id}",
            fingerprint=ElementFingerprint(tag="div", attributes={"id": pick_id}),
            text_snippet=f"text-{pick_id}",
            rect=ElementRect(x=0.0, y=0.0, width=100.0, height=40.0),
        ),
        comment=comment,
        origin_session=origin_session,
    )


def _origin_session_in_db(db_path: Path, pick_id: str) -> str | None:
    """Read the persisted origin_session for a pick directly from disk."""
    persistence = SqlitePersistence(db_path)
    loaded = persistence.load_inspector_state()
    assert loaded is not None
    match = next((p for p in loaded.picks if p.pick_id == pick_id), None)
    assert match is not None
    return match.origin_session


# ---------------------------------------------------------------------------
# load-on-init
# ---------------------------------------------------------------------------


def test_load_inspector_on_init(tmp_path: Path) -> None:
    """A pre-seeded DB hydrates inspector_state.picks on construction."""
    db_path = tmp_path / "fp.db"
    seed = SqlitePersistence(db_path)
    seed.save_inspector_state(InspectorState(picks=[_make_pick("seed-1", origin_session="A")]))

    sm = StateManager(session_id="A", persistence=SqlitePersistence(db_path))
    snap = sm.snapshot()

    pick_ids = [p.pick_id for p in snap.inspector_state.picks]
    assert pick_ids == ["seed-1"]


# ---------------------------------------------------------------------------
# origin_session stamping
# ---------------------------------------------------------------------------


@pytest.mark.anyio
async def test_add_pick_stamps_origin_session(tmp_path: Path) -> None:
    """add_pick stamps origin_session = session_id in both snapshot and DB."""
    db_path = tmp_path / "fp.db"
    sm = StateManager(session_id="A", persistence=SqlitePersistence(db_path))

    snap = await sm.add_pick(_make_pick("p-1"))

    pick = next(p for p in snap.inspector_state.picks if p.pick_id == "p-1")
    assert pick.origin_session == "A"
    assert _origin_session_in_db(db_path, "p-1") == "A"


@pytest.mark.anyio
async def test_steal_on_mutate(tmp_path: Path) -> None:
    """A pick owned by A is re-stamped to B when B mutates it (snapshot + DB)."""
    db_path = tmp_path / "fp.db"
    seed = SqlitePersistence(db_path)
    seed.save_inspector_state(InspectorState(picks=[_make_pick("p-1", origin_session="A")]))

    sm = StateManager(session_id="B", persistence=SqlitePersistence(db_path))
    snap = await sm.update_pick_comment("p-1", "changed by B")

    pick = next(p for p in snap.inspector_state.picks if p.pick_id == "p-1")
    assert pick.comment == "changed by B"
    assert pick.origin_session == "B"
    assert _origin_session_in_db(db_path, "p-1") == "B"


# ---------------------------------------------------------------------------
# panel + inspector saved together
# ---------------------------------------------------------------------------


@pytest.mark.anyio
async def test_concurrent_managers_deletes_stick(tmp_path: Path) -> None:
    """Two managers on the SAME global db: a delete in A is not resurrected by B.

    Regression for the picks-accumulation bug. Real sessions all share one
    ``state.db``; B must never re-write its stale in-memory full set over A's
    deletions.
    """
    db_path = tmp_path / "fp.db"

    sm_a = StateManager(session_id="A", persistence=SqlitePersistence(db_path))
    await sm_a.add_pick(_make_pick("p-1"))
    await sm_a.add_pick(_make_pick("p-2"))

    # B starts up and loads p-1 + p-2 into its own memory.
    sm_b = StateManager(session_id="B", persistence=SqlitePersistence(db_path))
    assert {p.pick_id for p in sm_b.snapshot().inspector_state.picks} == {"p-1", "p-2"}

    # A deletes everything.
    await sm_a.delete_pick("p-1")
    await sm_a.delete_pick("p-2")

    # B adds a new pick — must not resurrect p-1 / p-2.
    await sm_b.add_pick(_make_pick("p-3"))

    fresh = StateManager(session_id="C", persistence=SqlitePersistence(db_path))
    assert {p.pick_id for p in fresh.snapshot().inspector_state.picks} == {"p-3"}


@pytest.mark.anyio
async def test_panel_and_inspector_saved_together(tmp_path: Path) -> None:
    """Toggling a panel and adding a pick both persist; a fresh manager sees both."""
    db_path = tmp_path / "fp.db"
    sm = StateManager(session_id="A", persistence=SqlitePersistence(db_path))

    await sm.toggle_panel("bottom")  # default closed -> open
    await sm.add_pick(_make_pick("p-1"))

    reloaded = StateManager(session_id="A", persistence=SqlitePersistence(db_path))
    snap = reloaded.snapshot()

    assert snap.panel_state.bottom.open is True
    assert [p.pick_id for p in snap.inspector_state.picks] == ["p-1"]
