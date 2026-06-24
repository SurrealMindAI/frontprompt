"""StateManager — Inspector mutation tests.

Konzentriert sich auf die neuen Inspector-Methoden. Panel-Methoden existieren
schon im manager; einheitliche Lock-Discipline + Listener-Broadcast werden
implizit über add_pick atomicity-test mitgeprüft.
"""

from __future__ import annotations

import pytest

from frontprompt.state import StateManager
from frontprompt.state.state import (
    ElementFingerprint,
    ElementRect,
    InspectorState,
    Pick,
    PickElement,
    Region,
    Relation,
)

# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------


def _make_pick(pick_id: str = "p-001", comment: str = "") -> Pick:
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
    )


# ---------------------------------------------------------------------------
# Snapshot-Default — inspector_state ist enthalten
# ---------------------------------------------------------------------------


def test_initial_snapshot_contains_default_inspector_state() -> None:
    sm = StateManager(session_id="test-session")
    snap = sm.snapshot()
    assert snap.inspector_state.active is False
    assert snap.inspector_state.picks == []
    assert snap.inspector_state.active_pick_id is None


def test_snapshot_is_deep_copy_of_inspector_state() -> None:
    """Mutationen am snapshot dürfen den manager-state nicht ändern."""
    sm = StateManager(session_id="test-session")
    snap = sm.snapshot()
    snap.inspector_state.picks.append(_make_pick("leak"))
    snap.inspector_state.active = True

    fresh = sm.snapshot()
    assert fresh.inspector_state.picks == []
    assert fresh.inspector_state.active is False


# ---------------------------------------------------------------------------
# set_inspector_active
# ---------------------------------------------------------------------------


@pytest.mark.anyio
async def test_set_inspector_active_true() -> None:
    sm = StateManager(session_id="test-session")
    snap = await sm.set_inspector_active(True)
    assert snap.inspector_state.active is True


@pytest.mark.anyio
async def test_set_inspector_active_false() -> None:
    sm = StateManager(session_id="test-session")
    await sm.set_inspector_active(True)
    snap = await sm.set_inspector_active(False)
    assert snap.inspector_state.active is False


@pytest.mark.anyio
async def test_set_inspector_active_does_not_touch_panels() -> None:
    """Derived-state-Vertrag: panel_state bleibt unangetastet."""
    sm = StateManager(session_id="test-session")
    before = sm.snapshot().panel_state.model_dump()
    await sm.set_inspector_active(True)
    after = sm.snapshot().panel_state.model_dump()
    assert before == after


# ---------------------------------------------------------------------------
# add_pick — atomic operation
# ---------------------------------------------------------------------------


@pytest.mark.anyio
async def test_add_pick_appends_to_list() -> None:
    sm = StateManager(session_id="test-session")
    snap = await sm.add_pick(_make_pick("p1"))
    assert len(snap.inspector_state.picks) == 1
    assert snap.inspector_state.picks[0].pick_id == "p1"


@pytest.mark.anyio
async def test_add_pick_sets_active_pick_id() -> None:
    sm = StateManager(session_id="test-session")
    snap = await sm.add_pick(_make_pick("p1"))
    assert snap.inspector_state.active_pick_id == "p1"


@pytest.mark.anyio
async def test_add_pick_clears_inspector_active() -> None:
    """Atomic: activate + click should result in single snapshot with active=False."""
    sm = StateManager(session_id="test-session")
    await sm.set_inspector_active(True)
    snap = await sm.add_pick(_make_pick("p1"))
    assert snap.inspector_state.active is False


@pytest.mark.anyio
async def test_add_pick_replaces_existing_pick_id_idempotent() -> None:
    """Wenn dieselbe pick_id zweimal kommt (re-send / retry), wird der existing ersetzt."""
    sm = StateManager(session_id="test-session")
    await sm.add_pick(_make_pick("p1", comment="first"))
    snap = await sm.add_pick(_make_pick("p1", comment="second"))
    assert len(snap.inspector_state.picks) == 1
    assert snap.inspector_state.picks[0].comment == "second"


@pytest.mark.anyio
async def test_add_pick_preserves_order_across_multiple() -> None:
    sm = StateManager(session_id="test-session")
    await sm.add_pick(_make_pick("a"))
    await sm.add_pick(_make_pick("b"))
    snap = await sm.add_pick(_make_pick("c"))
    assert [p.pick_id for p in snap.inspector_state.picks] == ["a", "b", "c"]
    assert snap.inspector_state.active_pick_id == "c"


# ---------------------------------------------------------------------------
# select_pick
# ---------------------------------------------------------------------------


@pytest.mark.anyio
async def test_select_pick_changes_active_pick_id() -> None:
    sm = StateManager(session_id="test-session")
    await sm.add_pick(_make_pick("a"))
    await sm.add_pick(_make_pick("b"))  # active_pick_id is now 'b'
    snap = await sm.select_pick("a")
    assert snap.inspector_state.active_pick_id == "a"


@pytest.mark.anyio
async def test_select_pick_unknown_id_is_noop() -> None:
    """Unbekannte pick_id ändert nichts — wir broadcasten trotzdem (idempotent rehydrate)."""
    sm = StateManager(session_id="test-session")
    await sm.add_pick(_make_pick("a"))
    snap = await sm.select_pick("ghost")
    assert snap.inspector_state.active_pick_id == "a"  # unchanged


# ---------------------------------------------------------------------------
# update_pick_comment
# ---------------------------------------------------------------------------


@pytest.mark.anyio
async def test_update_pick_comment_patches_existing_pick() -> None:
    sm = StateManager(session_id="test-session")
    await sm.add_pick(_make_pick("a"))
    snap = await sm.update_pick_comment("a", "edited comment")
    assert snap.inspector_state.picks[0].comment == "edited comment"


@pytest.mark.anyio
async def test_update_pick_comment_unknown_id_is_noop() -> None:
    sm = StateManager(session_id="test-session")
    await sm.add_pick(_make_pick("a"))
    snap = await sm.update_pick_comment("ghost", "won't land")
    assert snap.inspector_state.picks[0].comment == ""


# ---------------------------------------------------------------------------
# delete_pick
# ---------------------------------------------------------------------------


@pytest.mark.anyio
async def test_delete_pick_removes_from_list() -> None:
    sm = StateManager(session_id="test-session")
    await sm.add_pick(_make_pick("a"))
    await sm.add_pick(_make_pick("b"))
    snap = await sm.delete_pick("a")
    assert [p.pick_id for p in snap.inspector_state.picks] == ["b"]


@pytest.mark.anyio
async def test_delete_active_pick_clears_active_pick_id() -> None:
    sm = StateManager(session_id="test-session")
    await sm.add_pick(_make_pick("a"))  # active = a
    snap = await sm.delete_pick("a")
    assert snap.inspector_state.active_pick_id is None


@pytest.mark.anyio
async def test_delete_nonactive_pick_preserves_active_pick_id() -> None:
    sm = StateManager(session_id="test-session")
    await sm.add_pick(_make_pick("a"))
    await sm.add_pick(_make_pick("b"))  # active = b
    snap = await sm.delete_pick("a")
    assert snap.inspector_state.active_pick_id == "b"


@pytest.mark.anyio
async def test_delete_pick_unknown_id_is_noop() -> None:
    sm = StateManager(session_id="test-session")
    await sm.add_pick(_make_pick("a"))
    snap = await sm.delete_pick("ghost")
    assert len(snap.inspector_state.picks) == 1


# ---------------------------------------------------------------------------
# Listener-Broadcast — inspector mutations triggern listener
# ---------------------------------------------------------------------------


@pytest.mark.anyio
async def test_inspector_mutations_notify_listeners() -> None:
    sm = StateManager(session_id="test-session")
    received: list[InspectorState] = []

    def listener(snap: object) -> None:
        received.append(snap.inspector_state)  # type: ignore[union-attr]

    sm.add_snapshot_listener(listener)

    await sm.set_inspector_active(True)
    await sm.add_pick(_make_pick("a"))
    await sm.update_pick_comment("a", "edit")
    await sm.delete_pick("a")
    await sm.set_inspector_active(False)

    assert len(received) == 5
    # After set_inspector_active(True): active=True, no picks
    assert received[0].active is True
    # After add_pick: active=False (atomic), pick present
    assert received[1].active is False
    assert len(received[1].picks) == 1
    # After update_pick_comment: comment edited
    assert received[2].picks[0].comment == "edit"
    # After delete_pick: empty
    assert received[3].picks == []
    # After set_inspector_active(False): still empty, inactive
    assert received[4].active is False


# ---------------------------------------------------------------------------
# Relations — add / delete / update / cascade
# ---------------------------------------------------------------------------


def _make_relation(
    relation_id: str = "rel-001",
    source: str = "p-001",
    source_kind: str = "pick",
    target: str = "p-002",
    target_kind: str = "pick",
    kind: str = "relates_to",
    note: str | None = None,
) -> Relation:
    return Relation(
        relation_id=relation_id,
        source_id=source,
        source_kind=source_kind,  # type: ignore[arg-type]
        target_id=target,
        target_kind=target_kind,  # type: ignore[arg-type]
        kind=kind,  # type: ignore[arg-type]
        note=note,
        timestamp_ms=1_700_000_000_001,
    )


def _make_region(
    region_id: str = "reg-001",
    member_pick_ids: list[str] | None = None,
    note: str | None = None,
) -> Region:
    return Region(
        region_id=region_id,
        rect=ElementRect(x=0.0, y=0.0, width=200.0, height=100.0),
        member_pick_ids=member_pick_ids or [],
        note=note,
        timestamp_ms=1_700_000_000_002,
    )


@pytest.mark.anyio
async def test_add_relation_appends() -> None:
    sm = StateManager(session_id="test-session")
    await sm.add_pick(_make_pick("p-001"))
    await sm.add_pick(_make_pick("p-002"))
    snap = await sm.add_relation(_make_relation())
    assert len(snap.inspector_state.relations) == 1
    assert snap.inspector_state.relations[0].relation_id == "rel-001"


@pytest.mark.anyio
async def test_add_relation_last_write_wins_by_id() -> None:
    sm = StateManager(session_id="test-session")
    await sm.add_pick(_make_pick("p-001"))
    await sm.add_pick(_make_pick("p-002"))
    await sm.add_relation(_make_relation(kind="relates_to"))
    snap = await sm.add_relation(_make_relation(kind="triggers"))
    assert len(snap.inspector_state.relations) == 1
    assert snap.inspector_state.relations[0].kind == "triggers"


@pytest.mark.anyio
async def test_add_relation_rejects_unknown_source() -> None:
    sm = StateManager(session_id="test-session")
    await sm.add_pick(_make_pick("p-001"))  # only p-001, not p-002
    snap = await sm.add_relation(_make_relation(source="p-001", target="p-missing"))
    assert snap.inspector_state.relations == []


@pytest.mark.anyio
async def test_add_relation_rejects_unknown_target() -> None:
    sm = StateManager(session_id="test-session")
    await sm.add_pick(_make_pick("p-002"))  # only p-002
    snap = await sm.add_relation(_make_relation(source="p-missing", target="p-002"))
    assert snap.inspector_state.relations == []


@pytest.mark.anyio
async def test_add_relation_self_loop_rejected_at_manager() -> None:
    """Pydantic-level rejection ist primary; manager-level is defensive (z.B.
    falls source==target durch model-mutation rein käme). Hier testen wir den
    Pydantic-Pfad — Relation lässt sich nicht mal mit self-loop construct'en.
    """
    sm = StateManager(session_id="test-session")
    await sm.add_pick(_make_pick("p-001"))
    # Pydantic blocks construction outright:
    import pytest as _pytest
    from pydantic import ValidationError

    with _pytest.raises(ValidationError):
        Relation(
            relation_id="rel-loop",
            source_id="p-001",
            source_kind="pick",
            target_id="p-001",
            target_kind="pick",
            kind="relates_to",
            timestamp_ms=0,
        )
    snap = sm.snapshot()
    assert snap.inspector_state.relations == []


@pytest.mark.anyio
async def test_delete_relation_removes() -> None:
    sm = StateManager(session_id="test-session")
    await sm.add_pick(_make_pick("p-001"))
    await sm.add_pick(_make_pick("p-002"))
    await sm.add_relation(_make_relation())
    snap = await sm.delete_relation("rel-001")
    assert snap.inspector_state.relations == []


@pytest.mark.anyio
async def test_delete_relation_unknown_id_is_noop() -> None:
    sm = StateManager(session_id="test-session")
    await sm.add_pick(_make_pick("p-001"))
    await sm.add_pick(_make_pick("p-002"))
    await sm.add_relation(_make_relation())
    snap = await sm.delete_relation("rel-does-not-exist")
    assert len(snap.inspector_state.relations) == 1


@pytest.mark.anyio
async def test_update_relation_replaces_kind_and_note() -> None:
    sm = StateManager(session_id="test-session")
    await sm.add_pick(_make_pick("p-001"))
    await sm.add_pick(_make_pick("p-002"))
    await sm.add_relation(_make_relation(kind="relates_to", note="initial"))
    snap = await sm.update_relation("rel-001", kind="triggers", note="edited")
    assert snap.inspector_state.relations[0].kind == "triggers"
    assert snap.inspector_state.relations[0].note == "edited"


@pytest.mark.anyio
async def test_update_relation_can_clear_note() -> None:
    sm = StateManager(session_id="test-session")
    await sm.add_pick(_make_pick("p-001"))
    await sm.add_pick(_make_pick("p-002"))
    await sm.add_relation(_make_relation(note="initial"))
    snap = await sm.update_relation("rel-001", kind="relates_to", note=None)
    assert snap.inspector_state.relations[0].note is None


@pytest.mark.anyio
async def test_update_relation_unknown_id_is_noop() -> None:
    sm = StateManager(session_id="test-session")
    await sm.add_pick(_make_pick("p-001"))
    await sm.add_pick(_make_pick("p-002"))
    await sm.add_relation(_make_relation())
    snap = await sm.update_relation("rel-does-not-exist", kind="triggers", note="x")
    assert snap.inspector_state.relations[0].kind == "relates_to"  # unverändert


@pytest.mark.anyio
async def test_delete_pick_cascades_relations() -> None:
    """3 picks A/B/C, 3 relations A→B, B→C, A→C — delete pick B → 2 relations dropped (alle die B involvieren)."""
    sm = StateManager(session_id="test-session")
    await sm.add_pick(_make_pick("p-A"))
    await sm.add_pick(_make_pick("p-B"))
    await sm.add_pick(_make_pick("p-C"))
    await sm.add_relation(_make_relation("r-AB", source="p-A", target="p-B"))
    await sm.add_relation(_make_relation("r-BC", source="p-B", target="p-C"))
    await sm.add_relation(_make_relation("r-AC", source="p-A", target="p-C"))
    snap = await sm.delete_pick("p-B")
    assert len(snap.inspector_state.relations) == 1
    assert snap.inspector_state.relations[0].relation_id == "r-AC"


@pytest.mark.anyio
async def test_delete_pick_cascade_single_snapshot() -> None:
    """Cascade-mutations sind atomar — eine listener-callback, nicht eine pro relation."""
    sm = StateManager(session_id="test-session")
    received: list[InspectorState] = []

    def listener(snap: object) -> None:
        received.append(snap.inspector_state)  # type: ignore[union-attr]

    await sm.add_pick(_make_pick("p-A"))
    await sm.add_pick(_make_pick("p-B"))
    await sm.add_relation(_make_relation("r-1", source="p-A", target="p-B"))
    await sm.add_relation(_make_relation("r-2", source="p-B", target="p-A"))
    sm.add_snapshot_listener(listener)

    await sm.delete_pick("p-B")
    # exactly ONE listener call from the cascade-mutation, despite removing 1 pick + 2 relations
    assert len(received) == 1
    assert len(received[0].picks) == 1
    assert received[0].relations == []


# ---------------------------------------------------------------------------
# Regions — add / delete / update / select / cascade (Schema 0.4.0)
# ---------------------------------------------------------------------------


@pytest.mark.anyio
async def test_add_region_appends_and_sets_active() -> None:
    sm = StateManager(session_id="test-session")
    await sm.add_pick(_make_pick("p-1"))
    snap = await sm.add_region(_make_region(member_pick_ids=["p-1"]))
    assert len(snap.inspector_state.regions) == 1
    assert snap.inspector_state.regions[0].region_id == "reg-001"
    assert snap.inspector_state.active_region_id == "reg-001"
    assert snap.inspector_state.active_pick_id is None  # mutually exclusive


@pytest.mark.anyio
async def test_add_region_filters_unknown_members() -> None:
    sm = StateManager(session_id="test-session")
    await sm.add_pick(_make_pick("p-1"))
    snap = await sm.add_region(_make_region(member_pick_ids=["p-1", "p-ghost"]))
    assert snap.inspector_state.regions[0].member_pick_ids == ["p-1"]


@pytest.mark.anyio
async def test_add_region_last_write_wins_by_id() -> None:
    sm = StateManager(session_id="test-session")
    await sm.add_pick(_make_pick("p-1"))
    await sm.add_region(_make_region(member_pick_ids=["p-1"], note="initial"))
    snap = await sm.add_region(_make_region(member_pick_ids=["p-1"], note="updated"))
    assert len(snap.inspector_state.regions) == 1
    assert snap.inspector_state.regions[0].note == "updated"


@pytest.mark.anyio
async def test_delete_region_removes_and_clears_active() -> None:
    sm = StateManager(session_id="test-session")
    await sm.add_pick(_make_pick("p-1"))
    await sm.add_region(_make_region())
    snap = await sm.delete_region("reg-001")
    assert snap.inspector_state.regions == []
    assert snap.inspector_state.active_region_id is None


@pytest.mark.anyio
async def test_delete_region_cascades_relations() -> None:
    """Region als Relation-endpoint: löschen cascadet relations involving region."""
    sm = StateManager(session_id="test-session")
    await sm.add_pick(_make_pick("p-1"))
    await sm.add_region(_make_region())
    # Relation pick → region
    await sm.add_relation(
        _make_relation(
            "r-pr",
            source="p-1",
            source_kind="pick",
            target="reg-001",
            target_kind="region",
        ),
    )
    snap = await sm.delete_region("reg-001")
    assert snap.inspector_state.regions == []
    assert snap.inspector_state.relations == []  # cascaded


@pytest.mark.anyio
async def test_delete_pick_removes_from_region_members_but_keeps_region() -> None:
    """Pick weg → aus region.member_pick_ids entfernt; Region bleibt (container-semantik)."""
    sm = StateManager(session_id="test-session")
    await sm.add_pick(_make_pick("p-A"))
    await sm.add_pick(_make_pick("p-B"))
    await sm.add_region(_make_region(member_pick_ids=["p-A", "p-B"]))
    snap = await sm.delete_pick("p-A")
    assert len(snap.inspector_state.regions) == 1
    assert snap.inspector_state.regions[0].member_pick_ids == ["p-B"]


@pytest.mark.anyio
async def test_select_region_sets_active_and_clears_pick() -> None:
    sm = StateManager(session_id="test-session")
    await sm.add_pick(_make_pick("p-1"))
    await sm.add_region(_make_region())
    # Activate pick first
    await sm.select_pick("p-1")
    # Now select region — should clear active_pick_id
    snap = await sm.select_region("reg-001")
    assert snap.inspector_state.active_region_id == "reg-001"
    assert snap.inspector_state.active_pick_id is None


@pytest.mark.anyio
async def test_add_relation_accepts_region_endpoint() -> None:
    sm = StateManager(session_id="test-session")
    await sm.add_pick(_make_pick("p-1"))
    await sm.add_region(_make_region())
    snap = await sm.add_relation(
        _make_relation(
            "r-pr",
            source="p-1",
            source_kind="pick",
            target="reg-001",
            target_kind="region",
        ),
    )
    assert len(snap.inspector_state.relations) == 1
    assert snap.inspector_state.relations[0].target_kind == "region"


@pytest.mark.anyio
async def test_add_relation_rejects_unknown_region_endpoint() -> None:
    sm = StateManager(session_id="test-session")
    await sm.add_pick(_make_pick("p-1"))
    snap = await sm.add_relation(
        _make_relation(
            source="p-1",
            source_kind="pick",
            target="reg-ghost",
            target_kind="region",
        ),
    )
    assert snap.inspector_state.relations == []  # rejected


@pytest.mark.anyio
async def test_update_region_patches_note() -> None:
    sm = StateManager(session_id="test-session")
    await sm.add_region(_make_region())
    snap = await sm.update_region("reg-001", note="updated")
    assert snap.inspector_state.regions[0].note == "updated"


# ---------------------------------------------------------------------------
# Lock-scope: _notify_listeners called OUTSIDE lock
# ---------------------------------------------------------------------------


@pytest.mark.anyio
async def test_notify_listeners_called_outside_lock() -> None:
    """Listener that schedules a nested mutation must complete without deadlock.

    Before the fix: _post_mutate holds the lock while calling listeners.
    The nested mutation tries to acquire the same lock → deadlock (anyio.fail_after
    triggers as TimeoutError).

    After fix: lock is released before _notify_listeners → nested mutation
    completes cleanly.
    """
    import anyio

    sm = StateManager(session_id="test-session")

    nested_completed = False
    unsubscribe = None

    async def _listener_with_nested_mutation(snap: object) -> None:
        nonlocal nested_completed
        if nested_completed:
            # Guard against re-entrant calls (the nested mutation also fires listeners)
            return
        # Unsubscribe first to prevent re-entrant infinite loop
        if unsubscribe is not None:
            unsubscribe()
        # Schedule a nested mutation — before fix this deadlocks because
        # the lock is still held when this listener fires.
        await sm.toggle_panel("left")
        nested_completed = True

    unsubscribe = sm.add_snapshot_listener(_listener_with_nested_mutation)

    with anyio.fail_after(2.0):
        # This triggers the listener, which triggers the nested mutation
        await sm.toggle_panel("right")

    assert nested_completed is True, (
        "Nested mutation inside listener did not complete — lock was likely still held during listener dispatch"
    )


# ---------------------------------------------------------------------------
# snapshot() deep copy via model_copy(deep=True)
# ---------------------------------------------------------------------------


def test_snapshot_panel_state_is_deep_copy() -> None:
    """Mutating snap.panel_state.top.open must not change manager state."""
    sm = StateManager(session_id="test-session")
    snap = sm.snapshot()
    original_open = sm.snapshot().panel_state.top.open
    snap.panel_state.top.open = not original_open
    fresh = sm.snapshot()
    assert fresh.panel_state.top.open == original_open, (
        "Mutation on snap.panel_state.top leaked into manager state — snapshot() is not returning a deep copy"
    )


def test_snapshot_does_not_raise_with_complex_nested_pick() -> None:
    """snapshot() with a Pick that has a full ElementFingerprint must not raise."""
    sm = StateManager(session_id="test-session")
    pick = Pick(
        pick_id="fp-test-001",
        url="https://example.com/",
        timestamp_ms=1_700_000_000_000,
        element=PickElement(
            selector="#fp-test-001",
            fingerprint=ElementFingerprint(
                tag="div",
                attributes={"id": "fp-test-001", "class": "container", "data-x": "y"},
                text="Some text content here",
                path=["html", "body", "main", "div"],
                parent_name="main",
                parent_attribs={"class": "main"},
                parent_text="Parent text",
                siblings=["span", "a"],
                children=["p", "span"],
            ),
            text_snippet="Some text content here",
            rect=ElementRect(x=10.5, y=20.5, width=100.0, height=50.0),
        ),
        comment="test comment",
        color_index=3,
    )

    import anyio

    async def _run() -> None:
        await sm.add_pick(pick)
        for _ in range(5):
            snap = sm.snapshot()
            assert snap.inspector_state.picks[0].pick_id == "fp-test-001"

    try:
        anyio.from_thread.run_sync(anyio.run, _run)
    except RuntimeError:
        import asyncio

        asyncio.run(_run())


# ---------------------------------------------------------------------------
# unsubscribe lambda — false-positive verification
# ---------------------------------------------------------------------------


@pytest.mark.anyio
async def test_unsubscribe_removes_listener() -> None:
    """Unsubscribe callable must prevent future notifications."""
    sm = StateManager(session_id="test-session")
    calls: list[object] = []
    unsubscribe = sm.add_snapshot_listener(lambda snap: calls.append(snap))
    unsubscribe()
    await sm.toggle_panel("left")
    assert calls == [], "listener was called after unsubscribe"


@pytest.mark.anyio
async def test_unsubscribe_idempotent_on_already_removed() -> None:
    """Calling unsubscribe twice must not raise."""
    sm = StateManager(session_id="test-session")
    unsubscribe = sm.add_snapshot_listener(lambda snap: None)
    unsubscribe()
    unsubscribe()  # second call must not raise


@pytest.mark.anyio
async def test_unsubscribe_survives_listeners_reassignment() -> None:
    """Unsubscribe lambda accesses self._listeners via attribute lookup (lazy).

    This test verifies the lambda is NOT closing over the list object directly.
    If it did close over the old list object, monkey-patching sm._listeners would
    cause unsubscribe to operate on the old list while the manager uses the new list
    — leading to the listener being called after unsubscribe.

    Confirmed false-positive — the lambda uses self._listeners lazily.
    """
    sm = StateManager(session_id="test-session")
    calls: list[object] = []
    unsubscribe = sm.add_snapshot_listener(lambda snap: calls.append(snap))

    # Monkey-patch _listeners to a new list (simulates accidental reassignment)
    original_list = sm._listeners  # type: ignore[attr-defined]
    sm._listeners = list(original_list)  # type: ignore[attr-defined]

    # Unsubscribe must work (no exception) even after _listeners list object changed
    unsubscribe()

    # After unsubscribe the listener must not be called
    await sm.toggle_panel("left")
    assert calls == [], "listener was called after unsubscribe despite list reassignment"


# ---------------------------------------------------------------------------
# StateSnapshot frozen=True (outer only — nested models stay mutable)
# ---------------------------------------------------------------------------


def test_state_snapshot_is_frozen() -> None:
    """Assigning to StateSnapshot.schema_version must raise."""
    from pydantic import ValidationError

    sm = StateManager(session_id="test-session")
    snap = sm.snapshot()
    with pytest.raises((ValidationError, TypeError)):
        snap.schema_version = "mutated"


def test_pick_is_still_mutable() -> None:
    """Pick must remain mutable (frozen=False) — nested models guard."""
    pick = Pick(
        pick_id="p-mut",
        url="https://example.com/",
        timestamp_ms=1_700_000_000_000,
        element=PickElement(
            selector="#p-mut",
            fingerprint=ElementFingerprint(tag="div"),
            text_snippet="x",
            rect=ElementRect(x=0.0, y=0.0, width=10.0, height=10.0),
        ),
    )
    pick.comment = "updated"  # must not raise
    assert pick.comment == "updated"


def test_inspector_state_is_still_mutable() -> None:
    """InspectorState.picks must be appendable (frozen=False) — nested models guard."""
    state = InspectorState()
    new_pick = Pick(
        pick_id="p-append",
        url="https://example.com/",
        timestamp_ms=1_700_000_000_000,
        element=PickElement(
            selector="#p-append",
            fingerprint=ElementFingerprint(tag="span"),
            text_snippet="y",
            rect=ElementRect(x=0.0, y=0.0, width=5.0, height=5.0),
        ),
    )
    state.picks.append(new_pick)  # must not raise
    assert len(state.picks) == 1
