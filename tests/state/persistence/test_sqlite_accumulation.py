"""Regression tests for the cross-session picks-accumulation bug.

Root cause (reproduced here): the on-disk ``state.db`` is a single global file
shared by every session, but the old ``save_inspector_state`` rewrote the WHOLE
picks set from a session's stale in-memory copy (upsert-all + delete-missing).
A delete in one session was silently resurrected the next time any other
live-or-stale session flushed its own stale full set — picks grew monotonically
(observed 185 -> 219 -> 293) and user deletions never stuck.

The fix makes persistence authoritative + idempotent via per-entity
write-through (upsert one / delete one) so no session ever rewrites another
session's rows from stale memory.
"""

from __future__ import annotations

import sqlite3
from pathlib import Path
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from frontprompt.state.state import Pick


def _make_pick(pick_id: str, origin_session: str | None = None) -> Pick:
    from frontprompt.state.state import ElementFingerprint, ElementRect, Pick, PickElement

    return Pick(
        pick_id=pick_id,
        url="https://example.com/",
        timestamp_ms=1000,
        element=PickElement(
            selector=f"#{pick_id}",
            fingerprint=ElementFingerprint(tag="div"),
            text_snippet="snippet",
            rect=ElementRect(x=0.0, y=0.0, width=10.0, height=10.0),
        ),
        origin_session=origin_session,
    )


def _pick_ids(db_path: Path) -> set[str]:
    conn = sqlite3.connect(str(db_path))
    try:
        return {r[0] for r in conn.execute("SELECT pick_id FROM picks").fetchall()}
    finally:
        conn.close()


def test_delete_pick_writes_through(tmp_path: Path) -> None:
    """delete_pick removes the row on disk — a fresh reader does NOT see it."""
    from frontprompt.state.persistence.sqlite import SqlitePersistence

    db_path = tmp_path / "fp.db"
    p = SqlitePersistence(db_path)
    p.upsert_pick(_make_pick("a"))
    p.upsert_pick(_make_pick("b"))

    p.delete_pick("a")

    assert _pick_ids(db_path) == {"b"}
    reloaded = SqlitePersistence(db_path).load_inspector_state()
    assert reloaded is not None
    assert {pk.pick_id for pk in reloaded.picks} == {"b"}


def test_upsert_pick_idempotent_on_pick_id(tmp_path: Path) -> None:
    """Re-upserting the same pick_id does NOT grow the row count (no duplicates)."""
    from frontprompt.state.persistence.sqlite import SqlitePersistence

    db_path = tmp_path / "fp.db"
    p = SqlitePersistence(db_path)
    p.upsert_pick(_make_pick("a"))
    p.upsert_pick(_make_pick("a"))
    p.upsert_pick(_make_pick("a"))

    assert _pick_ids(db_path) == {"a"}


def test_concurrent_session_does_not_resurrect_deleted_pick(tmp_path: Path) -> None:
    """The headline bug: a stale session must NOT resurrect picks another session deleted.

    Reproduces the observed monotonic-growth / deletes-don't-stick behaviour with
    two persistence instances on the SAME global db (as every real session shares
    ``~/.local/state/frontprompt/state.db``).
    """
    from frontprompt.state.persistence.sqlite import SqlitePersistence

    db_path = tmp_path / "fp.db"

    session_a = SqlitePersistence(db_path)
    session_a.upsert_pick(_make_pick("a", origin_session="A"))
    session_a.upsert_pick(_make_pick("b", origin_session="A"))
    session_a.upsert_pick(_make_pick("c", origin_session="A"))

    # Session B starts up and loads the same three picks into its own memory.
    session_b = SqlitePersistence(db_path)
    loaded_b = session_b.load_inspector_state()
    assert loaded_b is not None
    assert {p.pick_id for p in loaded_b.picks} == {"a", "b", "c"}

    # Session A: user deletes ALL picks (one delete per pick, as the UI does).
    session_a.delete_pick("a")
    session_a.delete_pick("b")
    session_a.delete_pick("c")
    assert _pick_ids(db_path) == set()

    # Session B later adds one NEW pick. It must NOT resurrect a/b/c from its
    # stale in-memory copy — only the genuinely new pick lands.
    session_b.upsert_pick(_make_pick("d", origin_session="B"))

    assert _pick_ids(db_path) == {"d"}
