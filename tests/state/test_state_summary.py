"""StateManager.state_summary() — navigable structured overview.

The full StateSnapshot is a firehose for an AI agent (counts in the hundreds,
hundreds of KB of JSON). ``state_summary()`` returns a SMALL, typed
:class:`~frontprompt.state.state.StateSummary` with counts + grouping so an
agent gets overview-first, drill-down-on-demand. This suite asserts the
grouping/counts are correct AND that the serialized summary is tiny vs the
full snapshot.
"""

from __future__ import annotations

import pytest

from frontprompt.state import StateManager
from frontprompt.state.state import (
    ElementFingerprint,
    ElementRect,
    Pick,
    PickElement,
    Region,
    Relation,
    StateSummary,
)

# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------


def _make_pick(pick_id: str, url: str) -> Pick:
    return Pick(
        pick_id=pick_id,
        url=url,
        timestamp_ms=1_700_000_000_000,
        element=PickElement(
            selector=f"#{pick_id}",
            fingerprint=ElementFingerprint(tag="div", attributes={"id": pick_id}),
            text_snippet=f"text-{pick_id}",
            rect=ElementRect(x=0.0, y=0.0, width=100.0, height=40.0),
        ),
    )


def _make_region(region_id: str) -> Region:
    return Region(
        region_id=region_id,
        rect=ElementRect(x=0.0, y=0.0, width=200.0, height=200.0),
        timestamp_ms=1_700_000_000_000,
    )


async def _populate_cross_session(sm: StateManager) -> None:
    """Two origin sessions, multiple hostnames, picks + regions + relations.

    The manager stamps ``origin_session`` to *its own* session_id on every
    mutation (steal-on-mutate). To plant picks owned by a foreign session, we
    add them then hand-stamp the in-memory entity's origin_session — exactly
    the shape a cross-session SQLite load produces.
    """
    # Owned picks (current session) across two hostnames.
    await sm.add_pick(_make_pick("p-own-a1", "https://example.com/a"))
    await sm.add_pick(_make_pick("p-own-a2", "https://example.com/b"))
    await sm.add_pick(_make_pick("p-own-b1", "https://shop.test/cart"))
    # A data: URL pick — must NOT leak the full blob into the summary.
    await sm.add_pick(_make_pick("p-own-data", "data:text/html,<h1>hi</h1>"))

    # Foreign picks (another session). Add, then re-stamp provenance.
    await sm.add_pick(_make_pick("p-foreign-1", "https://example.com/c"))
    await sm.add_pick(_make_pick("p-foreign-2", "https://other.test/x"))

    snap = sm.snapshot()
    for p in snap.inspector_state.picks:
        if p.pick_id.startswith("p-foreign"):
            # Reach into the live manager state to set foreign provenance.
            for live in sm._inspector_state.picks:  # test-only provenance plant
                if live.pick_id == p.pick_id:
                    live.origin_session = "other-session"

    # Regions + one relation between two owned picks.
    await sm.add_region(_make_region("r-1"))
    await sm.add_relation(
        Relation(
            relation_id="rel-1",
            source_id="p-own-a1",
            source_kind="pick",
            target_id="p-own-a2",
            target_kind="pick",
            kind="relates_to",
            timestamp_ms=1_700_000_000_000,
        )
    )


# ---------------------------------------------------------------------------
# Shape + typing
# ---------------------------------------------------------------------------


def test_empty_summary_shape() -> None:
    sm = StateManager(session_id="sess-current")
    summary = sm.state_summary()

    assert isinstance(summary, StateSummary)
    assert summary.current_session_id == "sess-current"
    assert summary.active_pick_id is None
    assert summary.active_region_id is None
    assert summary.counts.picks == 0
    assert summary.counts.regions == 0
    assert summary.counts.relations == 0
    assert summary.by_origin_session == []
    assert summary.by_hostname == []
    assert summary.owned_vs_foreign.owned == 0
    assert summary.owned_vs_foreign.foreign == 0
    # schema_version mirrors the snapshot's.
    assert summary.schema_version


# ---------------------------------------------------------------------------
# Counts + grouping
# ---------------------------------------------------------------------------


@pytest.mark.anyio
async def test_counts_are_correct() -> None:
    sm = StateManager(session_id="sess-current")
    await _populate_cross_session(sm)

    summary = sm.state_summary()
    assert summary.counts.picks == 6
    assert summary.counts.regions == 1
    assert summary.counts.relations == 1


@pytest.mark.anyio
async def test_by_origin_session_grouping() -> None:
    sm = StateManager(session_id="sess-current")
    await _populate_cross_session(sm)

    summary = sm.state_summary()
    groups = {g.session: g for g in summary.by_origin_session}
    # Current session owns 4 picks, the region, and the relation.
    assert groups["sess-current"].picks == 4
    assert groups["sess-current"].regions == 1
    assert groups["sess-current"].relations == 1
    # The foreign session owns 2 picks, no regions/relations.
    assert groups["other-session"].picks == 2
    assert groups["other-session"].regions == 0
    assert groups["other-session"].relations == 0


@pytest.mark.anyio
async def test_by_hostname_grouping() -> None:
    sm = StateManager(session_id="sess-current")
    await _populate_cross_session(sm)

    summary = sm.state_summary()
    hosts = {h.hostname: h.picks for h in summary.by_hostname}
    # example.com: a1, a2 (owned) + c (foreign) = 3
    assert hosts["example.com"] == 3
    assert hosts["shop.test"] == 1
    assert hosts["other.test"] == 1
    # data: URL collapses to a stable short label, never the blob.
    assert hosts["data:"] == 1
    assert all("<h1>" not in h for h in hosts)


@pytest.mark.anyio
async def test_owned_vs_foreign_split() -> None:
    sm = StateManager(session_id="sess-current")
    await _populate_cross_session(sm)

    summary = sm.state_summary()
    assert summary.owned_vs_foreign.owned == 4
    assert summary.owned_vs_foreign.foreign == 2


# ---------------------------------------------------------------------------
# Size invariant — the whole point: tiny vs the full snapshot.
# ---------------------------------------------------------------------------


@pytest.mark.anyio
async def test_summary_is_tiny_vs_full_snapshot() -> None:
    sm = StateManager(session_id="sess-current")
    # Plant many picks so the full snapshot is genuinely large.
    for i in range(300):
        await sm.add_pick(_make_pick(f"p-{i:04d}", f"https://example.com/page/{i}"))

    summary_json = sm.state_summary().model_dump_json()
    snapshot_json = sm.snapshot().model_dump_json()

    # The summary must be a small fraction of the full dump.
    assert len(summary_json) < len(snapshot_json) / 20
    # And in absolute terms, comfortably small.
    assert len(summary_json) < 4_000
