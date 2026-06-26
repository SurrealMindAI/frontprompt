"""ReplayPlayer — unit tests using test doubles (no real Chromium).

All tests use a FakeReplayPageController (records calls) and a mock StateManager.
These run in CI without any browser dependency.
"""

from __future__ import annotations

import asyncio
from typing import Any
from unittest.mock import AsyncMock, MagicMock, call, patch

import pytest

from frontprompt.state.state import (
    AssertionEntry,
    NavigationEntry,
    PageEventEntry,
    PickRefEntry,
    Recording,
    ReplayProgress,
    ReplayStepResult,
)


# ---------------------------------------------------------------------------
# Test doubles
# ---------------------------------------------------------------------------


class FakeReplayPageController:
    """Minimal test double for PlaywrightPageController used by ReplayPlayer.

    Records calls to navigate, click_selector, keyboard_type, keyboard_press,
    and evaluate_assertion. Returns configurable results.
    """

    def __init__(self) -> None:
        self.navigate_calls: list[str] = []
        self.click_calls: list[str] = []
        self.keyboard_type_calls: list[str] = []
        self.keyboard_press_calls: list[str] = []
        self.evaluate_assertion_calls: list[AssertionEntry] = []

        # Configurable results (default ok=True)
        self.navigate_result: dict[str, Any] = {"ok": True, "navigated_to": "https://example.com"}
        self.click_result: dict[str, Any] = {"ok": True}
        self.keyboard_type_result: dict[str, Any] = {"ok": True}
        self.keyboard_press_result: dict[str, Any] = {"ok": True}
        self.evaluate_assertion_result: dict[str, Any] = {
            "ok": True,
            "assertion_passed": True,
            "assertion_actual": None,
        }

        # Mock page property (needed for cross-origin detection in navigate)
        self.page = MagicMock()
        self.page.url = "https://example.com"

    async def navigate(self, url: str) -> dict[str, Any]:
        self.navigate_calls.append(url)
        return self.navigate_result

    async def click_selector(self, selector: str) -> dict[str, Any]:
        self.click_calls.append(selector)
        return self.click_result

    async def keyboard_type(self, text: str) -> dict[str, Any]:
        self.keyboard_type_calls.append(text)
        return self.keyboard_type_result

    async def keyboard_press(self, key: str) -> dict[str, Any]:
        self.keyboard_press_calls.append(key)
        return self.keyboard_press_result

    async def evaluate_assertion(self, entry: AssertionEntry) -> dict[str, Any]:
        self.evaluate_assertion_calls.append(entry)
        return self.evaluate_assertion_result


def _make_recording(entries: list = None, parameters: list = None) -> Recording:
    return Recording(
        recording_id="rec-001",
        name="Test Recording",
        status="stopped",
        started_at_ms=1000,
        ended_at_ms=2000,
        entries=entries or [],
        parameters=parameters or [],
    )


def _make_state_manager_mock() -> AsyncMock:
    sm = AsyncMock()
    sm.set_active_replay_progress = AsyncMock(return_value=MagicMock())
    sm.save_replay_report = AsyncMock(return_value=None)
    return sm


def _make_nav_entry(seq: int = 0, to_url: str = "https://example.com") -> NavigationEntry:
    return NavigationEntry(
        seq=seq,
        timestamp_ms=1000 + seq * 100,
        from_url="about:blank",
        to_url=to_url,
    )


def _make_page_event(
    seq: int = 0,
    event_type: str = "click",
    target: str = "button#submit",
    key: str | None = None,
) -> PageEventEntry:
    return PageEventEntry(
        seq=seq,
        timestamp_ms=1000 + seq * 100,
        event_type=event_type,  # type: ignore[arg-type]
        target=target,
        default_prevented=False,
        key=key,
    )


def _make_assertion_entry(seq: int = 0) -> AssertionEntry:
    return AssertionEntry(
        seq=seq,
        timestamp_ms=1000 + seq * 100,
        assertion_id="a-001",
        assertion_type="selector_exists",
        target="h1",
        target_kind="selector",
        comparator="none",
        description="Check heading",
    )


def _make_pick_ref(seq: int = 0) -> PickRefEntry:
    return PickRefEntry(
        seq=seq,
        timestamp_ms=1000 + seq * 100,
        pick_id="pick-001",
    )


# ---------------------------------------------------------------------------
# Section 3 tests
# ---------------------------------------------------------------------------


@pytest.mark.anyio
async def test_empty_recording_returns_completed_report() -> None:
    """Recording with 0 entries → ReplayReport(status='completed', step_results=[])."""
    from frontprompt.ipc.replay_player import ReplayPlayer

    controller = FakeReplayPageController()
    sm = _make_state_manager_mock()
    recording = _make_recording()

    player = ReplayPlayer(recording=recording, parameters={}, page_controller=controller, state_manager=sm)
    report = await player.run()

    assert report.status == "completed"
    assert report.step_results == []
    assert report.recording_id == "rec-001"


@pytest.mark.anyio
async def test_navigation_entry_calls_navigate_and_returns_ok_result() -> None:
    """Navigation entry → navigate() called with to_url, ReplayStepResult(kind='navigation', ok=True)."""
    from frontprompt.ipc.replay_player import ReplayPlayer

    controller = FakeReplayPageController()
    sm = _make_state_manager_mock()
    recording = _make_recording(entries=[_make_nav_entry(seq=0, to_url="https://example.com")])

    player = ReplayPlayer(recording=recording, parameters={}, page_controller=controller, state_manager=sm)
    report = await player.run()

    assert controller.navigate_calls == ["https://example.com"]
    assert len(report.step_results) == 1
    step = report.step_results[0]
    assert step.seq == 0
    assert step.kind == "navigation"
    assert step.ok is True
    assert step.skipped is False


@pytest.mark.anyio
async def test_page_event_click_calls_click_selector() -> None:
    """Page event click → click_selector() called with target."""
    from frontprompt.ipc.replay_player import ReplayPlayer

    controller = FakeReplayPageController()
    sm = _make_state_manager_mock()
    recording = _make_recording(entries=[_make_page_event(seq=0, event_type="click", target="button#ok")])

    player = ReplayPlayer(recording=recording, parameters={}, page_controller=controller, state_manager=sm)
    report = await player.run()

    assert controller.click_calls == ["button#ok"]
    step = report.step_results[0]
    assert step.ok is True
    assert step.kind == "page_event"


@pytest.mark.anyio
async def test_page_event_keydown_printable_calls_keyboard_type() -> None:
    """Page event keydown with printable key → keyboard_type() called with key."""
    from frontprompt.ipc.replay_player import ReplayPlayer

    controller = FakeReplayPageController()
    sm = _make_state_manager_mock()
    recording = _make_recording(
        entries=[_make_page_event(seq=0, event_type="keydown", target="input#name", key="a")]
    )

    player = ReplayPlayer(recording=recording, parameters={}, page_controller=controller, state_manager=sm)
    report = await player.run()

    assert controller.keyboard_type_calls == ["a"]
    assert controller.keyboard_press_calls == []


@pytest.mark.anyio
async def test_page_event_keydown_enter_calls_keyboard_press() -> None:
    """Page event keydown Enter → keyboard_press() called."""
    from frontprompt.ipc.replay_player import ReplayPlayer

    controller = FakeReplayPageController()
    sm = _make_state_manager_mock()
    recording = _make_recording(
        entries=[_make_page_event(seq=0, event_type="keydown", target="input#search", key="Enter")]
    )

    player = ReplayPlayer(recording=recording, parameters={}, page_controller=controller, state_manager=sm)
    await player.run()

    assert controller.keyboard_press_calls == ["Enter"]
    assert controller.keyboard_type_calls == []


@pytest.mark.anyio
async def test_page_event_pointerdown_is_skipped() -> None:
    """Page event pointerdown → skipped=True, skipped_reason='pointerdown_skipped_mvp'."""
    from frontprompt.ipc.replay_player import ReplayPlayer

    controller = FakeReplayPageController()
    sm = _make_state_manager_mock()
    recording = _make_recording(
        entries=[_make_page_event(seq=0, event_type="pointerdown", target="div#area")]
    )

    player = ReplayPlayer(recording=recording, parameters={}, page_controller=controller, state_manager=sm)
    report = await player.run()

    assert controller.click_calls == []
    step = report.step_results[0]
    assert step.skipped is True
    assert step.skipped_reason == "pointerdown_skipped_mvp"
    assert step.ok is True


@pytest.mark.anyio
async def test_pick_ref_is_skipped() -> None:
    """pick_ref entry → skipped=True, skipped_reason='pick_ref_skipped_mvp'."""
    from frontprompt.ipc.replay_player import ReplayPlayer

    controller = FakeReplayPageController()
    sm = _make_state_manager_mock()
    recording = _make_recording(entries=[_make_pick_ref(seq=0)])

    player = ReplayPlayer(recording=recording, parameters={}, page_controller=controller, state_manager=sm)
    report = await player.run()

    step = report.step_results[0]
    assert step.skipped is True
    assert step.skipped_reason == "pick_ref_skipped_mvp"
    assert step.ok is True


@pytest.mark.anyio
async def test_assertion_entry_calls_evaluate_assertion_and_captures_result() -> None:
    """Assertion entry → evaluate_assertion() called, result captured in step."""
    from frontprompt.ipc.replay_player import ReplayPlayer

    controller = FakeReplayPageController()
    controller.evaluate_assertion_result = {
        "ok": True,
        "assertion_passed": True,
        "assertion_actual": None,
    }
    sm = _make_state_manager_mock()
    recording = _make_recording(entries=[_make_assertion_entry(seq=0)])

    player = ReplayPlayer(recording=recording, parameters={}, page_controller=controller, state_manager=sm)
    report = await player.run()

    assert len(controller.evaluate_assertion_calls) == 1
    step = report.step_results[0]
    assert step.ok is True
    assert step.assertion_passed is True
    assert step.kind == "assertion"


@pytest.mark.anyio
async def test_dry_run_makes_no_browser_calls() -> None:
    """dry_run=True → no browser calls, all steps ok=True, skipped=True, reason='dry_run'."""
    from frontprompt.ipc.replay_player import ReplayPlayer

    controller = FakeReplayPageController()
    sm = _make_state_manager_mock()
    recording = _make_recording(
        entries=[
            _make_nav_entry(seq=0),
            _make_page_event(seq=1, event_type="click", target="button#ok"),
        ]
    )

    player = ReplayPlayer(
        recording=recording, parameters={}, page_controller=controller, state_manager=sm, dry_run=True
    )
    report = await player.run()

    assert controller.navigate_calls == []
    assert controller.click_calls == []
    assert all(s.skipped is True for s in report.step_results)
    assert all(s.skipped_reason == "dry_run" for s in report.step_results)
    assert all(s.ok is True for s in report.step_results)


@pytest.mark.anyio
async def test_real_time_false_no_sleep() -> None:
    """real_time=False → no anyio.sleep() calls."""
    from frontprompt.ipc.replay_player import ReplayPlayer

    controller = FakeReplayPageController()
    sm = _make_state_manager_mock()
    recording = _make_recording(
        entries=[
            _make_nav_entry(seq=0),
            _make_nav_entry(seq=1, to_url="https://example.com/page2"),
        ]
    )

    sleep_calls = []
    with patch("frontprompt.ipc.replay_player.anyio") as mock_anyio:
        mock_anyio.sleep = AsyncMock(side_effect=lambda _: sleep_calls.append(_))
        player = ReplayPlayer(
            recording=recording, parameters={}, page_controller=controller, state_manager=sm, real_time=False
        )
        await player.run()

    assert sleep_calls == []


@pytest.mark.anyio
async def test_real_time_true_calls_sleep_between_steps() -> None:
    """real_time=True → anyio.sleep() called with delta_ms/1000 between steps."""
    from frontprompt.ipc.replay_player import ReplayPlayer

    controller = FakeReplayPageController()
    sm = _make_state_manager_mock()
    # entries with 500ms gap
    recording = _make_recording(
        entries=[
            NavigationEntry(seq=0, timestamp_ms=1000, from_url="about:blank", to_url="https://a.com"),
            NavigationEntry(seq=1, timestamp_ms=1500, from_url="https://a.com", to_url="https://b.com"),
        ]
    )

    sleep_calls: list[float] = []

    async def _fake_sleep(seconds: float) -> None:
        sleep_calls.append(seconds)

    with patch("frontprompt.ipc.replay_player.anyio") as mock_anyio:
        mock_anyio.sleep = _fake_sleep
        player = ReplayPlayer(
            recording=recording, parameters={}, page_controller=controller, state_manager=sm, real_time=True
        )
        await player.run()

    # Should have slept for the delta: 500ms → 0.5s (between entry 0 and entry 1)
    assert len(sleep_calls) >= 1
    assert abs(sleep_calls[0] - 0.5) < 0.01


@pytest.mark.anyio
async def test_parameter_substitution_in_navigation_url() -> None:
    """{{base_url}} in navigation.to_url → replaced with provided value."""
    from frontprompt.ipc.replay_player import ReplayPlayer

    controller = FakeReplayPageController()
    sm = _make_state_manager_mock()
    recording = _make_recording(
        entries=[_make_nav_entry(seq=0, to_url="{{base_url}}/dashboard")]
    )

    player = ReplayPlayer(
        recording=recording,
        parameters={"base_url": "https://my-app.com"},
        page_controller=controller,
        state_manager=sm,
    )
    await player.run()

    assert controller.navigate_calls == ["https://my-app.com/dashboard"]


@pytest.mark.anyio
async def test_parameter_substitution_in_keydown_text() -> None:
    """{{query}} in page_event.key (keydown) → replaced with provided value."""
    from frontprompt.ipc.replay_player import ReplayPlayer

    controller = FakeReplayPageController()
    sm = _make_state_manager_mock()
    recording = _make_recording(
        entries=[_make_page_event(seq=0, event_type="keydown", target="input#search", key="{{query}}")]
    )

    player = ReplayPlayer(
        recording=recording,
        parameters={"query": "hello world"},
        page_controller=controller,
        state_manager=sm,
    )
    await player.run()

    assert controller.keyboard_type_calls == ["hello world"]


@pytest.mark.anyio
async def test_missing_parameter_step_fails_but_replay_continues() -> None:
    """Missing parameter → step fails with error='missing parameter: <name>', replay continues."""
    from frontprompt.ipc.replay_player import ReplayPlayer

    controller = FakeReplayPageController()
    sm = _make_state_manager_mock()
    recording = _make_recording(
        entries=[
            _make_nav_entry(seq=0, to_url="{{missing_param}}/page"),
            _make_nav_entry(seq=1, to_url="https://example.com"),
        ]
    )

    player = ReplayPlayer(recording=recording, parameters={}, page_controller=controller, state_manager=sm)
    report = await player.run()

    # First step fails with missing parameter error
    assert report.step_results[0].ok is False
    assert "missing parameter" in report.step_results[0].error
    assert "missing_param" in report.step_results[0].error

    # Second step succeeds (replay continued)
    assert report.step_results[1].ok is True
    assert controller.navigate_calls == ["https://example.com"]


@pytest.mark.anyio
async def test_playwright_exception_in_click_step_fails_but_replay_continues() -> None:
    """Playwright exception during click_selector → ReplayStepResult(ok=False), replay continues."""
    from frontprompt.ipc.replay_player import ReplayPlayer

    controller = FakeReplayPageController()
    controller.click_result = {"ok": False, "error": "element not found"}
    sm = _make_state_manager_mock()
    recording = _make_recording(
        entries=[
            _make_page_event(seq=0, event_type="click", target="button#missing"),
            _make_nav_entry(seq=1, to_url="https://example.com"),
        ]
    )

    player = ReplayPlayer(recording=recording, parameters={}, page_controller=controller, state_manager=sm)
    report = await player.run()

    assert report.step_results[0].ok is False
    assert report.step_results[0].error == "element not found"
    # Second step still ran
    assert report.step_results[1].ok is True
    assert controller.navigate_calls == ["https://example.com"]


@pytest.mark.anyio
async def test_cancelled_error_returns_failed_report() -> None:
    """Unrecoverable CancelledError → ReplayReport(status='failed', error='...')."""
    from frontprompt.ipc.replay_player import ReplayPlayer

    controller = FakeReplayPageController()
    sm = _make_state_manager_mock()

    async def _raise_cancel(url: str) -> dict[str, Any]:
        raise asyncio.CancelledError("test cancellation")

    controller.navigate = _raise_cancel  # type: ignore[method-assign]
    recording = _make_recording(entries=[_make_nav_entry(seq=0)])

    player = ReplayPlayer(recording=recording, parameters={}, page_controller=controller, state_manager=sm)
    report = await player.run()

    assert report.status == "failed"
    assert report.error is not None


@pytest.mark.anyio
async def test_replay_progress_updated_before_each_step() -> None:
    """set_active_replay_progress() called before each step, None after completion."""
    from frontprompt.ipc.replay_player import ReplayPlayer

    controller = FakeReplayPageController()
    sm = _make_state_manager_mock()
    recording = _make_recording(
        entries=[
            _make_nav_entry(seq=0),
            _make_nav_entry(seq=1, to_url="https://example.com/page2"),
        ]
    )

    player = ReplayPlayer(recording=recording, parameters={}, page_controller=controller, state_manager=sm)
    await player.run()

    # set_active_replay_progress called: once per step (=2) + final None
    assert sm.set_active_replay_progress.call_count >= 3
    # Last call is with None (progress cleared)
    last_call_arg = sm.set_active_replay_progress.call_args_list[-1].args[0]
    assert last_call_arg is None


@pytest.mark.anyio
async def test_unknown_entry_kind_is_skipped_forward_compat() -> None:
    """Unknown/non-actionable TimelineEntry kind → skipped=True (forward-compat for transcript_segment)."""
    from frontprompt.ipc.replay_player import ReplayPlayer

    # We use region_ref (existing kind that's also skipped) to verify the skip path
    from frontprompt.state.state import RegionRefEntry

    controller = FakeReplayPageController()
    sm = _make_state_manager_mock()
    region_entry = RegionRefEntry(seq=0, timestamp_ms=1000, region_id="region-001")
    recording = _make_recording(entries=[region_entry])

    player = ReplayPlayer(recording=recording, parameters={}, page_controller=controller, state_manager=sm)
    report = await player.run()

    step = report.step_results[0]
    assert step.skipped is True
    assert step.ok is True


@pytest.mark.anyio
async def test_report_status_is_completed_when_all_steps_pass() -> None:
    """All steps passing → ReplayReport.status='completed'."""
    from frontprompt.ipc.replay_player import ReplayPlayer

    controller = FakeReplayPageController()
    sm = _make_state_manager_mock()
    recording = _make_recording(entries=[_make_nav_entry(seq=0)])

    player = ReplayPlayer(recording=recording, parameters={}, page_controller=controller, state_manager=sm)
    report = await player.run()

    assert report.status == "completed"


@pytest.mark.anyio
async def test_save_replay_report_called_after_run() -> None:
    """save_replay_report() is called on state_manager after run completes."""
    from frontprompt.ipc.replay_player import ReplayPlayer

    controller = FakeReplayPageController()
    sm = _make_state_manager_mock()
    recording = _make_recording()

    player = ReplayPlayer(recording=recording, parameters={}, page_controller=controller, state_manager=sm)
    report = await player.run()

    sm.save_replay_report.assert_called_once()
    saved = sm.save_replay_report.call_args.args[0]
    assert saved.replay_id == report.replay_id
