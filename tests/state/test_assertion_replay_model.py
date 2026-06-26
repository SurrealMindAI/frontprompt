"""Tests für AssertionEntry, ParameterDeclaration, ReplayReport/StepResult/Progress — Section 1.

TDD: Tests geschrieben ZUERST (RED), dann Implementierung (GREEN).
Deckt: AssertionType, AssertionComparator, AssertionEntry, ParameterDeclaration,
Recording.parameters, ReplayStatus, ReplayStepResult, ReplayReport, ReplayProgress,
RecordingsState.active_replay_progress, StateSnapshot 0.9.0 + backward-compat.
"""

from __future__ import annotations

import pytest
from pydantic import ValidationError


# ---------------------------------------------------------------------------
# AssertionType
# ---------------------------------------------------------------------------


def test_assertion_type_accepts_all_five() -> None:
    """AssertionType akzeptiert alle fünf gültigen Werte."""
    from pydantic import TypeAdapter

    from frontprompt.state.state import AssertionType

    ta: TypeAdapter[AssertionType] = TypeAdapter(AssertionType)
    for val in ("selector_exists", "text_equals", "text_contains", "visible", "url_equals"):
        assert ta.validate_python(val) == val


def test_assertion_type_rejects_unknown() -> None:
    """AssertionType lehnt unbekannte Werte ab."""
    from pydantic import TypeAdapter

    from frontprompt.state.state import AssertionType

    ta: TypeAdapter[AssertionType] = TypeAdapter(AssertionType)
    with pytest.raises(ValidationError):
        ta.validate_python("not_a_type")


# ---------------------------------------------------------------------------
# AssertionComparator
# ---------------------------------------------------------------------------


def test_assertion_comparator_accepts_all_four() -> None:
    """AssertionComparator akzeptiert 'equals', 'contains', 'regex', 'none'."""
    from pydantic import TypeAdapter

    from frontprompt.state.state import AssertionComparator

    ta: TypeAdapter[AssertionComparator] = TypeAdapter(AssertionComparator)
    for val in ("equals", "contains", "regex", "none"):
        assert ta.validate_python(val) == val


def test_assertion_comparator_rejects_unknown() -> None:
    from pydantic import TypeAdapter

    from frontprompt.state.state import AssertionComparator

    ta: TypeAdapter[AssertionComparator] = TypeAdapter(AssertionComparator)
    with pytest.raises(ValidationError):
        ta.validate_python("greater_than")


# ---------------------------------------------------------------------------
# AssertionEntry
# ---------------------------------------------------------------------------


def _make_assertion_entry_data(
    *,
    assertion_type: str = "selector_exists",
    comparator: str = "none",
    expected: str | None = None,
    target: str = "button#submit",
    target_kind: str = "selector",
) -> dict:
    return {
        "kind": "assertion",
        "seq": 3,
        "timestamp_ms": 1000,
        "assertion_id": "a1b2c3d4-e5f6-7890-abcd-ef1234567890",
        "assertion_type": assertion_type,
        "target": target,
        "target_kind": target_kind,
        "expected": expected,
        "comparator": comparator,
        "description": "Check button is present",
    }


def test_assertion_entry_selector_exists_roundtrip() -> None:
    """AssertionEntry mit assertion_type='selector_exists' — round-trip."""
    from frontprompt.state.state import AssertionEntry

    entry = AssertionEntry(**_make_assertion_entry_data(assertion_type="selector_exists"))
    assert entry.kind == "assertion"
    assert entry.assertion_type == "selector_exists"
    assert entry.expected is None
    assert entry.comparator == "none"

    restored = AssertionEntry.model_validate_json(entry.model_dump_json())
    assert restored == entry


def test_assertion_entry_text_equals_with_expected() -> None:
    """AssertionEntry mit assertion_type='text_equals' und non-None expected."""
    from frontprompt.state.state import AssertionEntry

    entry = AssertionEntry(
        **_make_assertion_entry_data(
            assertion_type="text_equals",
            comparator="equals",
            expected="Submit",
        )
    )
    assert entry.assertion_type == "text_equals"
    assert entry.expected == "Submit"
    assert entry.comparator == "equals"

    restored = AssertionEntry.model_validate_json(entry.model_dump_json())
    assert restored == entry


def test_assertion_entry_url_equals() -> None:
    """AssertionEntry mit assertion_type='url_equals' (target_kind='url')."""
    from frontprompt.state.state import AssertionEntry

    entry = AssertionEntry(
        **_make_assertion_entry_data(
            assertion_type="url_equals",
            comparator="equals",
            expected="https://example.com/dashboard",
            target="",
            target_kind="url",
        )
    )
    assert entry.assertion_type == "url_equals"
    assert entry.target_kind == "url"
    assert entry.expected == "https://example.com/dashboard"

    restored = AssertionEntry.model_validate_json(entry.model_dump_json())
    assert restored == entry


def test_assertion_entry_routes_correctly_in_timeline_union() -> None:
    """AssertionEntry mit kind='assertion' wird korrekt in der TimelineEntry-Union gerouted."""
    from pydantic import TypeAdapter

    from frontprompt.state.state import AssertionEntry, TimelineEntry

    ta: TypeAdapter[TimelineEntry] = TypeAdapter(TimelineEntry)
    result = ta.validate_python(_make_assertion_entry_data())
    assert isinstance(result, AssertionEntry)
    assert result.kind == "assertion"


# ---------------------------------------------------------------------------
# ParameterDeclaration
# ---------------------------------------------------------------------------


def test_parameter_declaration_all_fields_roundtrip() -> None:
    """ParameterDeclaration round-trip mit allen vier Feldern."""
    from frontprompt.state.state import ParameterDeclaration

    param = ParameterDeclaration(
        name="login_url",
        param_type="url",
        description="Base URL for login flow",
        default_value="https://example.com/login",
    )
    assert param.name == "login_url"
    assert param.param_type == "url"
    assert param.description == "Base URL for login flow"
    assert param.default_value == "https://example.com/login"

    restored = ParameterDeclaration.model_validate_json(param.model_dump_json())
    assert restored == param


def test_parameter_declaration_default_value_none() -> None:
    """ParameterDeclaration mit default_value=None (no default)."""
    from frontprompt.state.state import ParameterDeclaration

    param = ParameterDeclaration(
        name="username",
        param_type="string",
        description="Login username",
        default_value=None,
    )
    assert param.default_value is None

    restored = ParameterDeclaration.model_validate_json(param.model_dump_json())
    assert restored == param


def test_parameter_declaration_no_default_value_key() -> None:
    """ParameterDeclaration ohne default_value key deserialisiert mit default_value=None."""
    from frontprompt.state.state import ParameterDeclaration

    param = ParameterDeclaration.model_validate(
        {"name": "selector", "param_type": "selector", "description": "Target element"}
    )
    assert param.default_value is None


# ---------------------------------------------------------------------------
# Recording.parameters
# ---------------------------------------------------------------------------


def test_recording_with_parameters_roundtrip() -> None:
    """Recording mit parameters=[ParameterDeclaration(...)] round-trippt korrekt."""
    from frontprompt.state.state import ParameterDeclaration, Recording

    params = [
        ParameterDeclaration(name="base_url", param_type="url", description="Base URL"),
        ParameterDeclaration(name="user", param_type="string", description="Username", default_value="admin"),
    ]
    rec = Recording(
        recording_id="rec-param-001",
        name="Parametrized",
        status="active",
        started_at_ms=1000,
        parameters=params,
    )
    assert len(rec.parameters) == 2
    assert rec.parameters[0].name == "base_url"

    restored = Recording.model_validate_json(rec.model_dump_json())
    assert len(restored.parameters) == 2
    assert restored.parameters[1].default_value == "admin"


def test_recording_without_parameters_defaults_to_empty_list() -> None:
    """Recording ohne parameters-Key deserialisiert mit parameters=[] (backward-compat)."""
    import json

    from frontprompt.state.state import Recording

    data = {
        "recording_id": "rec-no-params",
        "name": "Old Recording",
        "status": "stopped",
        "started_at_ms": 1000,
        "ended_at_ms": 2000,
    }
    rec = Recording.model_validate_json(json.dumps(data))
    assert rec.parameters == []


# ---------------------------------------------------------------------------
# ReplayStatus
# ---------------------------------------------------------------------------


def test_replay_status_accepts_all_three() -> None:
    """ReplayStatus akzeptiert 'completed', 'failed', 'aborted'."""
    from pydantic import TypeAdapter

    from frontprompt.state.state import ReplayStatus

    ta: TypeAdapter[ReplayStatus] = TypeAdapter(ReplayStatus)
    for val in ("completed", "failed", "aborted"):
        assert ta.validate_python(val) == val


def test_replay_status_rejects_unknown() -> None:
    from pydantic import TypeAdapter

    from frontprompt.state.state import ReplayStatus

    ta: TypeAdapter[ReplayStatus] = TypeAdapter(ReplayStatus)
    with pytest.raises(ValidationError):
        ta.validate_python("running")


# ---------------------------------------------------------------------------
# ReplayStepResult
# ---------------------------------------------------------------------------


def _make_step_result(**kwargs) -> dict:
    defaults = {
        "seq": 0,
        "kind": "page_event",
        "ok": True,
        "skipped": False,
        "skipped_reason": None,
        "error": None,
        "assertion_passed": None,
        "assertion_actual": None,
        "duration_ms": 42,
    }
    defaults.update(kwargs)
    return defaults


def test_replay_step_result_non_assertion_step() -> None:
    """ReplayStepResult mit assertion_passed=None (nicht-assertion step)."""
    from frontprompt.state.state import ReplayStepResult

    step = ReplayStepResult(**_make_step_result(seq=0, kind="page_event", ok=True))
    assert step.assertion_passed is None
    assert step.assertion_actual is None
    assert step.ok is True
    assert step.skipped is False

    restored = ReplayStepResult.model_validate_json(step.model_dump_json())
    assert restored == step


def test_replay_step_result_assertion_failed() -> None:
    """ReplayStepResult mit assertion_passed=False und assertion_actual gesetzt."""
    from frontprompt.state.state import ReplayStepResult

    step = ReplayStepResult(
        **_make_step_result(
            seq=2,
            kind="assertion",
            ok=True,
            assertion_passed=False,
            assertion_actual="Wrong text",
        )
    )
    assert step.ok is True  # step ran but assertion failed
    assert step.assertion_passed is False
    assert step.assertion_actual == "Wrong text"

    restored = ReplayStepResult.model_validate_json(step.model_dump_json())
    assert restored == step


def test_replay_step_result_skipped() -> None:
    """ReplayStepResult mit skipped=True und skipped_reason gesetzt."""
    from frontprompt.state.state import ReplayStepResult

    step = ReplayStepResult(
        **_make_step_result(
            seq=1,
            kind="pick_ref",
            ok=True,
            skipped=True,
            skipped_reason="pick_ref_skipped_mvp",
        )
    )
    assert step.skipped is True
    assert step.skipped_reason == "pick_ref_skipped_mvp"

    restored = ReplayStepResult.model_validate_json(step.model_dump_json())
    assert restored == step


# ---------------------------------------------------------------------------
# ReplayReport
# ---------------------------------------------------------------------------


def _make_replay_report(**kwargs) -> dict:
    defaults: dict = {
        "replay_id": "rep-001",
        "recording_id": "rec-001",
        "parameters": {},
        "status": "completed",
        "started_at_ms": 1000,
        "ended_at_ms": 2000,
        "step_results": [],
        "error": None,
        "origin_session": None,
    }
    defaults.update(kwargs)
    return defaults


def test_replay_report_roundtrip() -> None:
    """ReplayReport round-trip mit step_results=[...]."""
    from frontprompt.state.state import ReplayReport, ReplayStepResult

    step = ReplayStepResult(**_make_step_result(seq=0, kind="page_event", ok=True))
    report = ReplayReport(**_make_replay_report(step_results=[step]))

    assert report.replay_id == "rep-001"
    assert len(report.step_results) == 1
    assert report.status == "completed"

    restored = ReplayReport.model_validate_json(report.model_dump_json())
    assert len(restored.step_results) == 1
    assert restored.step_results[0].seq == 0


def test_replay_report_status_completed() -> None:
    """ReplayReport mit status='completed' validiert korrekt."""
    from frontprompt.state.state import ReplayReport

    report = ReplayReport(**_make_replay_report(status="completed"))
    assert report.status == "completed"


def test_replay_report_step_results_with_assertion_actual() -> None:
    """step_results überleben persistence round-trip inkl. assertion_actual."""
    from frontprompt.state.state import ReplayReport, ReplayStepResult

    step = ReplayStepResult(
        **_make_step_result(
            seq=1,
            kind="assertion",
            ok=True,
            assertion_passed=False,
            assertion_actual="actual text here",
        )
    )
    report = ReplayReport(**_make_replay_report(step_results=[step]))

    restored = ReplayReport.model_validate_json(report.model_dump_json())
    assert restored.step_results[0].assertion_actual == "actual text here"
    assert restored.step_results[0].assertion_passed is False


def test_replay_report_step_results_with_skipped_reason() -> None:
    """step_results überleben round-trip inkl. skipped_reason."""
    from frontprompt.state.state import ReplayReport, ReplayStepResult

    step = ReplayStepResult(
        **_make_step_result(
            seq=0,
            kind="pick_ref",
            ok=True,
            skipped=True,
            skipped_reason="pointerdown_skipped_mvp",
        )
    )
    report = ReplayReport(**_make_replay_report(step_results=[step]))

    restored = ReplayReport.model_validate_json(report.model_dump_json())
    assert restored.step_results[0].skipped_reason == "pointerdown_skipped_mvp"


# ---------------------------------------------------------------------------
# ReplayProgress
# ---------------------------------------------------------------------------


def test_replay_progress_roundtrip() -> None:
    """ReplayProgress round-trip."""
    from frontprompt.state.state import ReplayProgress

    progress = ReplayProgress(
        replay_id="rep-001",
        recording_id="rec-001",
        current_seq=3,
        total_steps=10,
        passed_assertions=2,
        failed_assertions=0,
    )
    assert progress.current_seq == 3
    assert progress.total_steps == 10

    restored = ReplayProgress.model_validate_json(progress.model_dump_json())
    assert restored == progress


# ---------------------------------------------------------------------------
# RecordingsState.active_replay_progress
# ---------------------------------------------------------------------------


def test_recordings_state_active_replay_progress_defaults_none() -> None:
    """RecordingsState default: active_replay_progress=None."""
    from frontprompt.state.state import RecordingsState

    state = RecordingsState()
    assert state.active_replay_progress is None


def test_recordings_state_active_replay_progress_populated() -> None:
    """RecordingsState mit active_replay_progress=ReplayProgress(...)."""
    from frontprompt.state.state import RecordingsState, ReplayProgress

    progress = ReplayProgress(
        replay_id="rep-002",
        recording_id="rec-002",
        current_seq=1,
        total_steps=5,
        passed_assertions=1,
        failed_assertions=0,
    )
    state = RecordingsState(active_replay_progress=progress)
    assert state.active_replay_progress is not None
    assert state.active_replay_progress.replay_id == "rep-002"

    restored = RecordingsState.model_validate_json(state.model_dump_json())
    assert restored.active_replay_progress is not None
    assert restored.active_replay_progress.current_seq == 1


# ---------------------------------------------------------------------------
# StateSnapshot 0.9.0
# ---------------------------------------------------------------------------


def test_state_snapshot_schema_version_is_0_9_0() -> None:
    """Nach Schema-Bump 0.9.0 muss StateSnapshot default schema_version '0.9.0' liefern."""
    from frontprompt.state.state import PanelStateView, PanelView, StateSnapshot

    panel = PanelStateView(
        top=PanelView(open=True, size=56),
        bottom=PanelView(open=False, size=220),
        left=PanelView(open=True, size=300),
        right=PanelView(open=True, size=340),
    )
    snap = StateSnapshot(panel_state=panel)
    assert snap.schema_version == "0.9.0"


def test_state_snapshot_0_8_0_without_active_replay_progress_forward_compat() -> None:
    """Alter StateSnapshot 0.8.0 ohne 'active_replay_progress' deserialisiert ohne Fehler."""
    import json

    from frontprompt.state.state import StateSnapshot

    # 0.8.0 payload — no active_replay_progress in recordings_state
    old_payload = {
        "schema_version": "0.8.0",
        "panel_state": {
            "top": {"open": True, "size": 56},
            "bottom": {"open": False, "size": 220},
            "left": {"open": True, "size": 300},
            "right": {"open": True, "size": 340},
        },
        "inspector_state": {
            "active": False,
            "picks": [],
            "active_pick_id": None,
            "regions": [],
            "active_region_id": None,
            "relations": [],
        },
        "recordings_state": {
            "active_recording_id": None,
            "recordings": [],
            "active_detail_recording_id": None,
            "detail_recording": None,
        },
    }
    snap = StateSnapshot.model_validate_json(json.dumps(old_payload))
    # active_replay_progress defaults to None via default=None
    assert snap.recordings_state.active_replay_progress is None
