"""Tests für replay_reports SQLite-Persistenz — Section 2 TDD (sub-plan 01).

Deckt: save_replay_report, get_replay_report, list_replay_reports_meta —
per-entity WAL JSON-blob pattern analog dem Recorder's Persistenz.
"""

from __future__ import annotations

import tempfile
from pathlib import Path

import pytest

from frontprompt.state.state import (
    ReplayReport,
    ReplayReportMeta,
    ReplayStepResult,
)


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------


@pytest.fixture()
def sqlite_persistence(tmp_path: Path):
    """Frische SqlitePersistence für jeden Test (kein shared state)."""
    from frontprompt.state.persistence.sqlite import SqlitePersistence

    return SqlitePersistence(tmp_path / "test.db")


def _make_step(seq: int = 0, kind: str = "page_event", ok: bool = True) -> ReplayStepResult:
    return ReplayStepResult(
        seq=seq,
        kind=kind,
        ok=ok,
        skipped=False,
        skipped_reason=None,
        error=None,
        assertion_passed=None,
        assertion_actual=None,
        duration_ms=10,
    )


def _make_report(
    replay_id: str = "rep-001",
    recording_id: str = "rec-001",
    status: str = "completed",
    step_results: list[ReplayStepResult] | None = None,
) -> ReplayReport:
    return ReplayReport(
        replay_id=replay_id,
        recording_id=recording_id,
        parameters={"base_url": "https://example.com"} if replay_id == "rep-param" else {},
        status=status,  # type: ignore[arg-type]
        started_at_ms=1000,
        ended_at_ms=2000,
        step_results=step_results or [],
        error=None,
        origin_session="sess-001",
    )


# ---------------------------------------------------------------------------
# save_replay_report + get_replay_report
# ---------------------------------------------------------------------------


def test_save_and_get_replay_report_roundtrip(sqlite_persistence) -> None:
    """save_replay_report + get_replay_report round-trip."""
    report = _make_report()
    sqlite_persistence.save_replay_report(report)

    retrieved = sqlite_persistence.get_replay_report("rep-001")
    assert retrieved is not None
    assert retrieved.replay_id == "rep-001"
    assert retrieved.recording_id == "rec-001"
    assert retrieved.status == "completed"
    assert retrieved.started_at_ms == 1000
    assert retrieved.ended_at_ms == 2000


def test_get_replay_report_unknown_returns_none(sqlite_persistence) -> None:
    """get_replay_report('unknown-id') liefert None."""
    result = sqlite_persistence.get_replay_report("does-not-exist")
    assert result is None


def test_step_results_survive_roundtrip(sqlite_persistence) -> None:
    """step_results überleben den SQLite round-trip inkl. assertion_actual und skipped_reason."""
    steps = [
        ReplayStepResult(
            seq=0,
            kind="assertion",
            ok=True,
            skipped=False,
            skipped_reason=None,
            error=None,
            assertion_passed=False,
            assertion_actual="wrong text",
            duration_ms=15,
        ),
        ReplayStepResult(
            seq=1,
            kind="pick_ref",
            ok=True,
            skipped=True,
            skipped_reason="pick_ref_skipped_mvp",
            error=None,
            assertion_passed=None,
            assertion_actual=None,
            duration_ms=0,
        ),
    ]
    report = _make_report(step_results=steps)
    sqlite_persistence.save_replay_report(report)

    retrieved = sqlite_persistence.get_replay_report("rep-001")
    assert retrieved is not None
    assert len(retrieved.step_results) == 2
    assert retrieved.step_results[0].assertion_actual == "wrong text"
    assert retrieved.step_results[0].assertion_passed is False
    assert retrieved.step_results[1].skipped_reason == "pick_ref_skipped_mvp"
    assert retrieved.step_results[1].skipped is True


# ---------------------------------------------------------------------------
# list_replay_reports_meta
# ---------------------------------------------------------------------------


def test_list_replay_reports_meta_returns_all(sqlite_persistence) -> None:
    """list_replay_reports_meta(recording_id=None) liefert alle Reports als ReplayReportMeta."""
    sqlite_persistence.save_replay_report(_make_report(replay_id="rep-001", recording_id="rec-A"))
    sqlite_persistence.save_replay_report(_make_report(replay_id="rep-002", recording_id="rec-B"))

    metas = sqlite_persistence.list_replay_reports_meta(recording_id=None)
    assert len(metas) == 2
    ids = {m.replay_id for m in metas}
    assert ids == {"rep-001", "rep-002"}
    # Meta should be ReplayReportMeta instances (no step_results field)
    for meta in metas:
        assert isinstance(meta, ReplayReportMeta)
        assert not hasattr(meta, "step_results") or not hasattr(meta.model_fields, "step_results")


def test_list_replay_reports_meta_filtered_by_recording_id(sqlite_persistence) -> None:
    """list_replay_reports_meta(recording_id='rec-A') liefert nur Reports für diese Recording."""
    sqlite_persistence.save_replay_report(_make_report(replay_id="rep-001", recording_id="rec-A"))
    sqlite_persistence.save_replay_report(_make_report(replay_id="rep-002", recording_id="rec-A"))
    sqlite_persistence.save_replay_report(_make_report(replay_id="rep-003", recording_id="rec-B"))

    metas = sqlite_persistence.list_replay_reports_meta(recording_id="rec-A")
    assert len(metas) == 2
    assert all(m.recording_id == "rec-A" for m in metas)


def test_two_reports_same_recording_both_retrievable(sqlite_persistence) -> None:
    """Zwei Reports für dieselbe Recording sind getrennt abrufbar und unterscheidbar."""
    report_1 = _make_report(replay_id="rep-X1", recording_id="rec-shared", status="completed")
    report_2 = _make_report(replay_id="rep-X2", recording_id="rec-shared", status="failed")
    sqlite_persistence.save_replay_report(report_1)
    sqlite_persistence.save_replay_report(report_2)

    r1 = sqlite_persistence.get_replay_report("rep-X1")
    r2 = sqlite_persistence.get_replay_report("rep-X2")
    assert r1 is not None
    assert r2 is not None
    assert r1.status == "completed"
    assert r2.status == "failed"
    assert r1.replay_id != r2.replay_id
