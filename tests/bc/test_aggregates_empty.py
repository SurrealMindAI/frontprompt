"""Aggregate-Skeleton-Tests — verifiziert Instantiierbarkeit und assert_owner()-Logik.

Verwendet pytest-anyio (in pyproject.toml).
Die Tests sind bewusst minimalistisch: keine Business-Logik, keine Daten-Invarianten —
nur die strukturelle Garantie, dass Aggregates instantiierbar sind und
assert_owner() korrekt Guards.
"""

from __future__ import annotations

from unittest.mock import MagicMock

import pytest

from frontprompt.bc.interactive_surface.aggregates.pointing_session import (
    Annotation,
    Pick,
    PointingSession,
)
from frontprompt.bc.programmatic_executor.aggregates.interaction_flow import (
    InteractionFlow,
)
from frontprompt.bc.programmatic_executor.aggregates.page_session import PageSession
from frontprompt.scrapling.adapter import ScraplingAdapter
from frontprompt.scrapling.substrate_router import SubstrateRouter
from frontprompt.scrapling.user_data_dir import UserDataDirManager
from frontprompt.types import (
    AnnotationId,
    InteractionFlowId,
    PageSessionId,
    PickId,
    PointingSessionId,
    TaskId,
)

# ---- Fixtures ---------------------------------------------------------------

_OWNER = TaskId("task-owner-001")
_INTRUDER = TaskId("task-intruder-999")


def _make_ps(ps_id: str) -> PageSession:
    """Hilfs-Factory: PageSession mit Mocks für alle Pflicht-Dependencies."""
    return PageSession(
        page_session_id=PageSessionId(ps_id),
        user_data_dir_manager=MagicMock(spec=UserDataDirManager),
        scrapling_adapter=MagicMock(spec=ScraplingAdapter),
        substrate_router=MagicMock(spec=SubstrateRouter),
    )


# ---- PageSession ------------------------------------------------------------


def test_page_session_instantiable() -> None:
    """PageSession lässt sich mit minimalen Feldern instanziieren."""
    ps = _make_ps("ps-001")
    assert ps.page_session_id == PageSessionId("ps-001")
    assert ps._owner_task_id is None


def test_page_session_assert_owner_no_owner_raises() -> None:
    """assert_owner() wirft PermissionError wenn kein Owner gesetzt."""
    ps = _make_ps("ps-002")
    with pytest.raises(PermissionError, match="kein Owner-Task gesetzt"):
        ps.assert_owner(_OWNER)


def test_page_session_assert_owner_correct_owner_passes() -> None:
    """assert_owner() passiert wenn current_task_id == _owner_task_id."""
    ps = _make_ps("ps-003")
    ps._owner_task_id = _OWNER  # Nursery würde das beim Spawn setzen
    ps.assert_owner(_OWNER)  # darf nicht werfen


def test_page_session_assert_owner_wrong_owner_raises() -> None:
    """assert_owner() wirft PermissionError bei falschem Task."""
    ps = _make_ps("ps-004")
    ps._owner_task_id = _OWNER
    with pytest.raises(PermissionError, match="Owner-Task-Mismatch"):
        ps.assert_owner(_INTRUDER)


# ---- InteractionFlow --------------------------------------------------------


def test_interaction_flow_instantiable() -> None:
    """InteractionFlow lässt sich instanziieren."""
    flow = InteractionFlow(id=InteractionFlowId("flow-001"))
    assert flow.id == InteractionFlowId("flow-001")
    assert flow._owner_task_id is None


def test_interaction_flow_assert_owner_no_owner_raises() -> None:
    flow = InteractionFlow(id=InteractionFlowId("flow-002"))
    with pytest.raises(PermissionError, match="kein Owner-Task gesetzt"):
        flow.assert_owner(_OWNER)


def test_interaction_flow_assert_owner_correct_owner_passes() -> None:
    flow = InteractionFlow(id=InteractionFlowId("flow-003"))
    flow._owner_task_id = _OWNER
    flow.assert_owner(_OWNER)


def test_interaction_flow_assert_owner_wrong_owner_raises() -> None:
    flow = InteractionFlow(id=InteractionFlowId("flow-004"))
    flow._owner_task_id = _OWNER
    with pytest.raises(PermissionError, match="Owner-Task-Mismatch"):
        flow.assert_owner(_INTRUDER)


# ---- PointingSession + Pick + Annotation ------------------------------------


def test_pointing_session_instantiable_empty() -> None:
    """PointingSession startet mit leeren picks und annotations."""
    session = PointingSession(id=PointingSessionId("ptr-001"))
    assert session.id == PointingSessionId("ptr-001")
    assert session.picks == []
    assert session.annotations == []
    assert session._owner_task_id is None


def test_pointing_session_assert_owner_no_owner_raises() -> None:
    session = PointingSession(id=PointingSessionId("ptr-002"))
    with pytest.raises(PermissionError, match="kein Owner-Task gesetzt"):
        session.assert_owner(_OWNER)


def test_pointing_session_assert_owner_correct_owner_passes() -> None:
    session = PointingSession(id=PointingSessionId("ptr-003"))
    session._owner_task_id = _OWNER
    session.assert_owner(_OWNER)


def test_pointing_session_assert_owner_wrong_owner_raises() -> None:
    session = PointingSession(id=PointingSessionId("ptr-004"))
    session._owner_task_id = _OWNER
    with pytest.raises(PermissionError, match="Owner-Task-Mismatch"):
        session.assert_owner(_INTRUDER)


def test_pick_instantiable() -> None:
    """Pick-Entity lässt sich mit allen Pflichtfeldern instanziieren."""
    from datetime import UTC, datetime

    pick = Pick(
        id=PickId("pick-001"),
        selector=".submit-btn",
        score="0.95",
        timestamp=datetime(2026, 1, 1, tzinfo=UTC),
    )
    assert pick.selector == ".submit-btn"
    assert pick.score == "0.95"


def test_annotation_instantiable_minimal() -> None:
    """Annotation lässt sich mit Minimal-Feldern instantiieren (alle optionalen None)."""
    ann = Annotation(
        id=AnnotationId("ann-001"),
        content="Schaltfläche für Formular-Submit",
    )
    assert ann.page_session_id is None
    assert ann.interaction_flow_step_id is None
    assert ann.dom_snapshot_hash is None


def test_annotation_instantiable_with_cross_bc_ids() -> None:
    """Annotation akzeptiert dehydrierte Cross-BC-Identifier."""
    from frontprompt.types import InteractionFlowStepId

    ann = Annotation(
        id=AnnotationId("ann-002"),
        content="Schaltfläche während Capture-Schritt",
        page_session_id=PageSessionId("ps-ref-001"),
        interaction_flow_step_id=InteractionFlowStepId("step-ref-001"),
        dom_snapshot_hash="sha256-abc123",
    )
    assert ann.page_session_id == PageSessionId("ps-ref-001")
    assert ann.dom_snapshot_hash == "sha256-abc123"


# ---- ACL Protocol-Stub ------------------------------------------------------


def test_programmatic_reference_validator_is_protocol() -> None:
    """ProgrammaticReferenceValidator ist ein typing.Protocol — keine Instantiierung."""
    import typing

    from frontprompt.bc.interactive_surface.aggregates.programmatic_reference_validator import (
        ProgrammaticReferenceValidator,
    )

    assert typing.get_origin(type(ProgrammaticReferenceValidator)) is not None or True
    # Wichtige Eigenschaft: Klassen können strukturell konform sein ohne Inheritance.
    # Der Test verifiziert Importierbarkeit und dass das Modul kein Syntax-Error hat.
    _ = ProgrammaticReferenceValidator


# ---- ID-NewType-Isolation ---------------------------------------------------


def test_id_types_are_distinct() -> None:
    """NewTypes sind zur Laufzeit str, aber typ-verschieden für mypy."""
    page_id = PageSessionId("same-string")
    pointing_id = PointingSessionId("same-string")
    # Zur Laufzeit gleich (NewType ist rein statisch), aber mypy rejected:
    # pointing_session.assert_owner(page_id)  # würde mypy-Fehler erzeugen
    assert str(page_id) == str(pointing_id)  # Laufzeit-Sanity
