"""End-to-end replay tests: record → assert → replay → report — full stack.

Uses LazyBrowserSessionProvider (real frontprompt show subprocess) + the served
playground HTTP fixture from conftest.py (playground_server / playground_url).
Auto-skips when no Playwright Chromium binary is present.

Scenarios:
  1 — Basic record → replay round-trip: click + observable DOM effect
  2 — Assertion: selector_exists pass (h1 present → assertion_passed=True)
  3 — Assertion: text_equals fail with actual value captured
  4 — Navigation replay: recorded nav replays and browser URL changes to target
  5 — dry_run mode: browser state unchanged, all steps ok=True + skipped=True
  6 — Agent start/stop recording via IPC socket (not bridge)
  7 — MCP tool round-trip: IPC start/stop/replay → valid ReplayReport
  8 — CLI replay command: exit 0 + JSON with "status" key
  9 — Replay report persistence: stored report fetched via GetReplayReportRequest

Note on parametrised navigation (Scenario 4): The current agent write-surface
has no API to inject NavigationEntry objects with {{template}} URLs — navigations
are captured automatically by the daemon from real browser events with actual URLs.
Scenario 4 therefore tests that navigation replay works correctly with a real URL,
and that passing extra (unused) parameters does not break the replay engine.
True template substitution in navigation requires a "create recording with template
entries" API that is out of scope for sub-plan 07.
"""

from __future__ import annotations

import json
import shutil
import tempfile
from collections.abc import Iterator
from pathlib import Path
from typing import Any
from unittest.mock import MagicMock, patch

import anyio
import pytest
from click.testing import CliRunner

from frontprompt.cli import main as cli_main
from frontprompt.ipc import query
from frontprompt.ipc.protocol import (
    AddAssertionRequest,
    EvalJsRequest,
    GetPageInfoRequest,
    GetRecordingRequest,
    GetReplayReportRequest,
    GetSnapshotRequest,
    NavigateRequest,
    RunReplayRequest,
    StartRecordingRequest,
    StopRecordingRequest,
)
from frontprompt.mcp_server import LazyBrowserSessionProvider
from frontprompt.state.state import ReplayReport


# ── Chromium availability guard ──────────────────────────────────────────────


def _chromium_binary_available() -> bool:
    candidates = [
        Path.home() / "Library" / "Caches" / "ms-playwright",
        Path.home() / ".cache" / "ms-playwright",
    ]
    for cache in candidates:
        if cache.is_dir() and any(p.name.startswith("chromium-") for p in cache.iterdir()):
            return True
    return shutil.which("chromium") is not None


_SKIP = pytest.mark.skipif(
    not _chromium_binary_available(),
    reason="Playwright Chromium binary not installed.",
)


# ── Module-level session provider (one browser per module run) ────────────────

_provider: LazyBrowserSessionProvider | None = None
_tmp_dir: Path | None = None
_playground_base: str = ""  # set by _setup_provider


@pytest.fixture(scope="module", autouse=True)
def _setup_provider(playground_server: str) -> Iterator[None]:
    """Spawn one frontprompt show subprocess for the whole module.

    Navigates to replay-fixture.html as the start URL. Each scenario
    navigates as needed, restoring state afterwards.
    """
    global _provider, _tmp_dir, _playground_base
    _tmp_dir = Path(tempfile.mkdtemp(prefix="fp-e2e-replay-", dir="/tmp"))
    _playground_base = playground_server
    _provider = LazyBrowserSessionProvider(playground_server + "/replay-fixture.html")
    yield
    import asyncio as _asyncio

    if _provider is not None:
        try:
            loop = _asyncio.new_event_loop()
            loop.run_until_complete(_provider.close())
            loop.close()
        except Exception:
            pass
    if _tmp_dir is not None:
        shutil.rmtree(_tmp_dir, ignore_errors=True)


async def _get_socket() -> Path:
    assert _provider is not None
    meta = await _provider.get()
    return Path(meta.socket_path)


# ── Recording lifecycle helpers (bridge path) ─────────────────────────────────

#: Bridge schema version (matches bridge/messages.py SCHEMA_VERSION).
_SCHEMA = "0.9.0"


async def _start_recording(sock: Path, name: str = "e2e-test") -> str:
    """Trigger recording_start_requested via window.__fp, wait for active_recording_id.

    After Python's StateManager confirms the recording is active (GetSnapshotRequest),
    waits an extra 200 ms to ensure the state_snapshot broadcast has propagated to the
    Svelte frontend. The EventInterceptor reads backendState.recordings.activeRecordingId
    (frontend state), so events fired before the broadcast completes are silently dropped.
    """
    expr = (
        f"window.__fp({{kind: 'recording_start_requested', schema_version: '{_SCHEMA}', "
        f"name: {json.dumps(name)}, description: ''}})"
    )
    await query(sock, EvalJsRequest(expression=expr, mutating=True))
    for _ in range(20):
        snap = await query(sock, GetSnapshotRequest())
        if snap.ok:
            rid = snap.data.get("recordings_state", {}).get("active_recording_id")
            if rid:
                await anyio.sleep(0.2)
                return rid
        await anyio.sleep(0.1)
    raise AssertionError("active_recording_id never set after recording_start_requested")


async def _stop_recording(sock: Path, recording_id: str) -> None:
    """Trigger recording_stop_requested via window.__fp, wait for active_recording_id → None."""
    expr = (
        f"window.__fp({{kind: 'recording_stop_requested', schema_version: '{_SCHEMA}', "
        f"recording_id: {json.dumps(recording_id)}}})"
    )
    await query(sock, EvalJsRequest(expression=expr, mutating=True))
    for _ in range(20):
        snap = await query(sock, GetSnapshotRequest())
        if snap.ok:
            rid = snap.data.get("recordings_state", {}).get("active_recording_id")
            if rid is None:
                return
        await anyio.sleep(0.1)
    raise AssertionError("recording never stopped after recording_stop_requested")


async def _wait_for_entry_count(
    sock: Path, recording_id: str, expected_count: int, retries: int = 30
) -> list[dict[str, Any]]:
    """Poll GetRecordingRequest until entries reach expected_count."""
    rec = None
    for _ in range(retries):
        rec = await query(sock, GetRecordingRequest(recording_id=recording_id))
        if rec.ok:
            entries = rec.data.get("entries", [])
            if len(entries) >= expected_count:
                return entries
        await anyio.sleep(0.1)
    entries = rec.data.get("entries", []) if rec and rec.ok else []
    raise AssertionError(
        f"Expected {expected_count} entries, got {len(entries)}. "
        f"Entries: {[e.get('event_type', e.get('kind')) for e in entries]}"
    )


async def _wait_for_ipc_start_broadcast(sock: Path, recording_id: str) -> None:
    """After StartRecordingRequest, poll until the broadcast reaches the frontend.

    Required so the EventInterceptor sets activeRecordingId before any browser
    interactions are fired.
    """
    for _ in range(20):
        snap = await query(sock, GetSnapshotRequest())
        if snap.ok:
            rid = snap.data.get("recordings_state", {}).get("active_recording_id")
            if rid == recording_id:
                await anyio.sleep(0.2)
                return
        await anyio.sleep(0.1)
    raise AssertionError(f"active_recording_id {recording_id!r} never visible in snapshot after StartRecordingRequest")


# ── Scenarios ─────────────────────────────────────────────────────────────────


@pytest.mark.anyio
@_SKIP
async def test_basic_record_replay_round_trip(anyio_backend: str) -> None:
    """Scenario 1: Record a click, run replay, assert status=completed + DOM effect observed.

    This is the core round-trip: record → stop → navigate back to reset DOM →
    run replay → verify the replay actually re-drove the page (data-clicked="true").
    """
    sock = await _get_socket()

    # Navigate to the fixture page for a clean slate
    await query(sock, NavigateRequest(url=_playground_base + "/replay-fixture.html"))
    await anyio.sleep(0.3)

    # Record a click on #btn-click
    recording_id = await _start_recording(sock, "replay-e2e-1-basic")

    await query(sock, EvalJsRequest(
        expression="document.querySelector('#btn-click').click()",
        mutating=True,
    ))
    await _wait_for_entry_count(sock, recording_id, 1)

    await _stop_recording(sock, recording_id)

    # Reset page state before replay (so the DOM starts in initial "not clicked" state)
    await query(sock, NavigateRequest(url=_playground_base + "/replay-fixture.html"))
    await anyio.sleep(0.3)

    # Verify #click-result is in initial state (not yet clicked)
    init_resp = await query(sock, EvalJsRequest(
        expression="document.querySelector('#click-result').getAttribute('data-clicked')",
        mutating=False,
    ))
    assert init_resp.ok
    assert init_resp.data.get("result") is None, (
        f"Expected #click-result to be in initial state (no data-clicked), got: {init_resp.data!r}"
    )

    # Run replay
    replay_resp = await query(sock, RunReplayRequest(recording_id=recording_id))
    assert replay_resp.ok, f"RunReplayRequest failed: {replay_resp.error}"

    report = replay_resp.data
    assert report["status"] == "completed", (
        f"Expected status=completed, got: {report['status']!r}"
    )
    assert len(report["step_results"]) >= 1, (
        "Expected at least 1 step result in ReplayReport"
    )

    # All non-skipped steps must have ok=True
    for step in report["step_results"]:
        if not step["skipped"]:
            assert step["ok"], (
                f"Expected ok=True for non-skipped step seq={step['seq']}, got: {step}"
            )

    # Verify DOM effect: the replay actually re-drove the page
    # (button was clicked by the replay player → DOM changed)
    dom_resp = await query(sock, EvalJsRequest(
        expression="document.querySelector('#click-result').getAttribute('data-clicked')",
        mutating=False,
    ))
    assert dom_resp.ok
    assert dom_resp.data.get("result") == "true", (
        f"Expected DOM change after replay (data-clicked='true'), got: {dom_resp.data!r}. "
        f"Replay may not have executed the click on #btn-click."
    )


@pytest.mark.anyio
@_SKIP
async def test_assertion_selector_exists_pass(anyio_backend: str) -> None:
    """Scenario 2: Add selector_exists assertion for h1; replay → assertion_passed=True.

    Tests the assertion evaluation path: AddAssertionRequest inserts an AssertionEntry
    into the recording timeline, replay evaluates it against the live DOM and reports pass.
    """
    sock = await _get_socket()

    await query(sock, NavigateRequest(url=_playground_base + "/replay-fixture.html"))
    await anyio.sleep(0.3)

    recording_id = await _start_recording(sock, "replay-e2e-2-selector-exists")

    # Record one interaction so the recording has a non-empty timeline
    await query(sock, EvalJsRequest(
        expression="document.querySelector('#btn-click').click()",
        mutating=True,
    ))
    await _wait_for_entry_count(sock, recording_id, 1)
    await _stop_recording(sock, recording_id)

    # Add assertion: h1 should exist (selector_exists — always passes on replay-fixture.html)
    assert_resp = await query(sock, AddAssertionRequest(
        recording_id=recording_id,
        assertion_type="selector_exists",
        target="h1",
        target_kind="selector",
        expected=None,
        comparator="none",
        description="h1 heading must be present",
    ))
    assert assert_resp.ok, f"AddAssertionRequest failed: {assert_resp.error}"
    assertion_id = assert_resp.data.get("assertion_id")
    assert assertion_id, f"Expected non-empty assertion_id in response: {assert_resp.data}"

    # Reset page and run replay
    await query(sock, NavigateRequest(url=_playground_base + "/replay-fixture.html"))
    await anyio.sleep(0.3)

    replay_resp = await query(sock, RunReplayRequest(recording_id=recording_id))
    assert replay_resp.ok, f"RunReplayRequest failed: {replay_resp.error}"

    report = replay_resp.data
    assert report["status"] == "completed", f"Expected completed, got: {report['status']!r}"

    assertion_steps = [s for s in report["step_results"] if s["kind"] == "assertion"]
    assert len(assertion_steps) >= 1, (
        f"Expected ≥1 assertion step in replay report, got step kinds: "
        f"{[s['kind'] for s in report['step_results']]}"
    )

    for step in assertion_steps:
        assert step["assertion_passed"] is True, (
            f"Expected selector_exists for h1 to pass on replay-fixture.html, got: {step}"
        )


@pytest.mark.anyio
@_SKIP
async def test_assertion_text_equals_fail(anyio_backend: str) -> None:
    """Scenario 3: text_equals with wrong expected → assertion_passed=False, actual captured.

    The ReplayReport status must be 'completed' even when assertions fail — a run
    finishes regardless of assertion outcomes. The assertion_actual field captures
    the actual DOM text for diagnostic purposes.
    """
    sock = await _get_socket()

    await query(sock, NavigateRequest(url=_playground_base + "/replay-fixture.html"))
    await anyio.sleep(0.3)

    recording_id = await _start_recording(sock, "replay-e2e-3-text-fail")

    await query(sock, EvalJsRequest(
        expression="document.querySelector('#btn-click').click()",
        mutating=True,
    ))
    await _wait_for_entry_count(sock, recording_id, 1)
    await _stop_recording(sock, recording_id)

    # Add assertion that will intentionally fail: h1 text is NOT "WRONG_TEXT"
    assert_resp = await query(sock, AddAssertionRequest(
        recording_id=recording_id,
        assertion_type="text_equals",
        target="h1",
        target_kind="selector",
        expected="WRONG_TEXT",
        comparator="equals",
        description="h1 text check (intentionally wrong expected)",
    ))
    assert assert_resp.ok, f"AddAssertionRequest failed: {assert_resp.error}"

    # Reset page and run replay
    await query(sock, NavigateRequest(url=_playground_base + "/replay-fixture.html"))
    await anyio.sleep(0.3)

    replay_resp = await query(sock, RunReplayRequest(recording_id=recording_id))
    assert replay_resp.ok, f"RunReplayRequest failed: {replay_resp.error}"

    report = replay_resp.data
    # Replay MUST complete even when assertions fail (completed ≠ all assertions passed)
    assert report["status"] == "completed", (
        f"Expected status=completed (replay finishes regardless of assertion failures), "
        f"got: {report['status']!r}"
    )

    assertion_steps = [s for s in report["step_results"] if s["kind"] == "assertion"]
    assert len(assertion_steps) >= 1, (
        f"Expected ≥1 assertion step in replay report"
    )

    for step in assertion_steps:
        assert step["assertion_passed"] is False, (
            f"Expected text_equals with WRONG_TEXT to fail on h1, got: {step}"
        )
        assert step["assertion_actual"] is not None, (
            f"Expected assertion_actual to contain actual h1 text for diagnostics, got: {step}"
        )
        # The actual text is "Replay Fixture Heading" (from replay-fixture.html)
        assert "Replay Fixture Heading" in step["assertion_actual"], (
            f"Expected assertion_actual to contain the actual h1 text 'Replay Fixture Heading', "
            f"got: {step['assertion_actual']!r}"
        )


@pytest.mark.anyio
@_SKIP
async def test_navigation_replay(anyio_backend: str) -> None:
    """Scenario 4: Record a navigation, replay navigates browser to the target URL.

    Tests that NavigationEntry replay works end-to-end: the browser actually navigates
    to the recorded URL during replay. Provides extra (unused) parameters to verify
    the parameter binding mechanism handles them gracefully without error.

    Note: True {{template}} URL substitution in NavigationEntry objects requires the
    recording to contain template strings in to_url, which is only achievable by
    injecting entries directly into the StateManager's internal store — no public IPC
    API for this exists in the current implementation (Deviation from sub-plan Scenario 4).
    """
    sock = await _get_socket()

    fixture_url = _playground_base + "/replay-fixture.html"
    page2_url = _playground_base + "/page2.html"

    await query(sock, NavigateRequest(url=fixture_url))
    await anyio.sleep(0.3)

    recording_id = await _start_recording(sock, "replay-e2e-4-nav")

    # Navigate to page2 during recording → NavigationEntry captured in timeline
    nav_resp = await query(sock, NavigateRequest(url=page2_url))
    assert nav_resp.ok, f"NavigateRequest to page2 failed: {nav_resp.error}"
    await _wait_for_entry_count(sock, recording_id, 1)

    await _stop_recording(sock, recording_id)

    # Return to fixture before replay (replay will navigate to page2 again)
    await query(sock, NavigateRequest(url=fixture_url))
    await anyio.sleep(0.3)

    # Verify starting URL is at replay-fixture (not page2)
    info_before = await query(sock, GetPageInfoRequest())
    assert info_before.ok
    assert "replay-fixture" in info_before.data["url"], (
        f"Expected to start at replay-fixture, got: {info_before.data['url']!r}"
    )

    # Run replay with extra (unused) parameters — verifies that extra params don't break replay
    replay_resp = await query(sock, RunReplayRequest(
        recording_id=recording_id,
        parameters={"base_url": _playground_base},
    ))
    assert replay_resp.ok, f"RunReplayRequest failed: {replay_resp.error}"

    report = replay_resp.data
    assert report["status"] == "completed", f"Expected completed, got: {report['status']!r}"

    # All navigation steps must succeed
    nav_steps = [s for s in report["step_results"] if s["kind"] == "navigation"]
    assert len(nav_steps) >= 1, (
        f"Expected ≥1 navigation step in replay report, "
        f"got kinds: {[s['kind'] for s in report['step_results']]}"
    )
    for step in nav_steps:
        assert step["ok"], (
            f"Expected navigation step ok=True, got: {step}"
        )

    # Assert browser URL changed to page2 after replay drove the navigation
    info_after = await query(sock, GetPageInfoRequest())
    assert info_after.ok
    assert "page2" in info_after.data["url"], (
        f"Expected browser to navigate to page2 during replay, "
        f"current URL: {info_after.data['url']!r}"
    )

    # Restore to fixture for subsequent tests
    await query(sock, NavigateRequest(url=fixture_url))
    await anyio.sleep(0.3)


@pytest.mark.anyio
@_SKIP
async def test_dry_run_mode(anyio_backend: str) -> None:
    """Scenario 5: dry_run=True → report returned, browser URL unchanged, all steps skipped.

    Records a click + navigation to page2, then runs replay in dry_run mode.
    Verifies that NO browser actions were executed (URL stays at replay-fixture).
    All step_results must have ok=True and skipped=True with skipped_reason='dry_run'.
    """
    sock = await _get_socket()

    fixture_url = _playground_base + "/replay-fixture.html"
    page2_url = _playground_base + "/page2.html"

    await query(sock, NavigateRequest(url=fixture_url))
    await anyio.sleep(0.3)

    recording_id = await _start_recording(sock, "replay-e2e-5-dry-run")

    # Record a click
    await query(sock, EvalJsRequest(
        expression="document.querySelector('#btn-click').click()",
        mutating=True,
    ))
    await _wait_for_entry_count(sock, recording_id, 1)

    # Record a navigation to page2
    await query(sock, NavigateRequest(url=page2_url))
    await _wait_for_entry_count(sock, recording_id, 2)

    await _stop_recording(sock, recording_id)

    # Return to fixture before dry_run replay
    await query(sock, NavigateRequest(url=fixture_url))
    await anyio.sleep(0.3)

    # Record the URL before dry_run
    info_before = await query(sock, GetPageInfoRequest())
    assert info_before.ok
    url_before = info_before.data["url"]
    assert "replay-fixture" in url_before, (
        f"Expected to be at replay-fixture before dry_run, got: {url_before!r}"
    )

    # Run dry_run replay
    replay_resp = await query(sock, RunReplayRequest(recording_id=recording_id, dry_run=True))
    assert replay_resp.ok, f"RunReplayRequest dry_run failed: {replay_resp.error}"

    report = replay_resp.data
    assert report["status"] == "completed", (
        f"Expected dry_run replay to report status=completed, got: {report['status']!r}"
    )
    assert len(report["step_results"]) >= 1, "Expected ≥1 step results in dry_run report"

    # All steps must be ok=True + skipped=True with reason='dry_run'
    for step in report["step_results"]:
        assert step["ok"], (
            f"Expected ok=True in dry_run step seq={step['seq']}, got: {step}"
        )
        assert step["skipped"], (
            f"Expected skipped=True in dry_run step seq={step['seq']}, got: {step}"
        )
        assert step.get("skipped_reason") == "dry_run", (
            f"Expected skipped_reason='dry_run' for step seq={step['seq']}, "
            f"got: {step.get('skipped_reason')!r}"
        )

    # Browser URL must be unchanged — no navigation executed in dry_run
    info_after = await query(sock, GetPageInfoRequest())
    assert info_after.ok
    url_after = info_after.data["url"]
    assert "replay-fixture" in url_after, (
        f"Expected browser URL to remain at replay-fixture in dry_run mode. "
        f"Before: {url_before!r}, After: {url_after!r}. "
        f"Dry_run may have executed a real navigation to page2."
    )


@pytest.mark.anyio
@_SKIP
async def test_agent_start_stop_recording_ipc(anyio_backend: str) -> None:
    """Scenario 6: Start/stop recording via IPC socket → recording visible, entries > 0.

    This scenario exercises the agent write-surface path (StartRecordingRequest /
    StopRecordingRequest) rather than the browser bridge path (window.__fp).
    Both paths route through the same StateManager methods — this test verifies
    the IPC write-side is wired correctly.
    """
    sock = await _get_socket()

    await query(sock, NavigateRequest(url=_playground_base + "/replay-fixture.html"))
    await anyio.sleep(0.3)

    # Start recording via IPC (agent path, not bridge)
    start_resp = await query(sock, StartRecordingRequest(name="agent-ipc-recording"))
    assert start_resp.ok, f"StartRecordingRequest failed: {start_resp.error}"

    recording_id = start_resp.data.get("recording_id")
    assert recording_id, f"Expected non-empty recording_id in response: {start_resp.data}"
    assert start_resp.data.get("name") == "agent-ipc-recording", (
        f"Expected name='agent-ipc-recording', got: {start_resp.data}"
    )

    # Wait for state_snapshot broadcast to reach the frontend EventInterceptor
    await _wait_for_ipc_start_broadcast(sock, recording_id)

    # Interact to generate a timeline entry
    await query(sock, EvalJsRequest(
        expression="document.querySelector('#btn-click').click()",
        mutating=True,
    ))
    await _wait_for_entry_count(sock, recording_id, 1)

    # Stop recording via IPC
    stop_resp = await query(sock, StopRecordingRequest(recording_id=recording_id))
    assert stop_resp.ok, f"StopRecordingRequest failed: {stop_resp.error}"

    # Verify recording is stopped and has entries
    rec_resp = await query(sock, GetRecordingRequest(recording_id=recording_id))
    assert rec_resp.ok, f"GetRecordingRequest failed: {rec_resp.error}"
    recording = rec_resp.data

    assert recording["status"] == "stopped", (
        f"Expected status=stopped after StopRecordingRequest, got: {recording['status']!r}"
    )
    assert len(recording.get("entries", [])) >= 1, (
        f"Expected entry_count > 0 after interactions, got: {len(recording.get('entries', []))}"
    )


@pytest.mark.anyio
@_SKIP
async def test_mcp_tool_round_trip(anyio_backend: str) -> None:
    """Scenario 7: Start/stop/replay via IPC → valid ReplayReport parsed via model_validate.

    This is the MCP tool round-trip scenario: the same sequence of IPC requests
    that `frontprompt_run_replay` executes under the hood, verified end-to-end.
    The response must parse cleanly as a ReplayReport Pydantic model.
    """
    sock = await _get_socket()

    await query(sock, NavigateRequest(url=_playground_base + "/replay-fixture.html"))
    await anyio.sleep(0.3)

    # Start via IPC (mirrors frontprompt_start_recording MCP tool)
    start_resp = await query(sock, StartRecordingRequest(name="mcp-round-trip"))
    assert start_resp.ok, f"StartRecordingRequest failed: {start_resp.error}"
    recording_id = start_resp.data["recording_id"]

    await _wait_for_ipc_start_broadcast(sock, recording_id)

    # Minimal interaction
    await query(sock, EvalJsRequest(
        expression="document.querySelector('#btn-click').click()",
        mutating=True,
    ))
    await _wait_for_entry_count(sock, recording_id, 1)

    # Stop via IPC (mirrors frontprompt_stop_recording MCP tool)
    stop_resp = await query(sock, StopRecordingRequest(recording_id=recording_id))
    assert stop_resp.ok, f"StopRecordingRequest failed: {stop_resp.error}"

    # Reset page before replay
    await query(sock, NavigateRequest(url=_playground_base + "/replay-fixture.html"))
    await anyio.sleep(0.3)

    # Run replay via IPC (mirrors frontprompt_run_replay MCP tool)
    replay_resp = await query(sock, RunReplayRequest(recording_id=recording_id))
    assert replay_resp.ok, f"RunReplayRequest failed: {replay_resp.error}"

    # Validate that the response is a well-formed ReplayReport
    report = ReplayReport.model_validate(replay_resp.data)
    assert report.replay_id, f"Expected non-empty replay_id: {report}"
    assert report.recording_id == recording_id, (
        f"Expected recording_id={recording_id!r}, got: {report.recording_id!r}"
    )
    assert report.status == "completed", f"Expected status=completed, got: {report.status!r}"
    assert len(report.step_results) >= 1, (
        f"Expected ≥1 step result, got: {len(report.step_results)}"
    )


@pytest.mark.anyio
@_SKIP
async def test_cli_replay_command(anyio_backend: str) -> None:
    """Scenario 8: CLI `recordings replay <id>` → exit 0 + JSON with 'status' key.

    Uses CliRunner with mocked _resolve_session (same pattern as recorder e2e
    Scenario 7) to invoke the CLI in a thread and avoid event-loop nesting.
    """
    sock = await _get_socket()
    assert _provider is not None
    meta = await _provider.get()

    await query(sock, NavigateRequest(url=_playground_base + "/replay-fixture.html"))
    await anyio.sleep(0.3)

    # Create a recording to replay
    recording_id = await _start_recording(sock, "cli-replay-test")
    await query(sock, EvalJsRequest(
        expression="document.querySelector('#btn-click').click()",
        mutating=True,
    ))
    await _wait_for_entry_count(sock, recording_id, 1)
    await _stop_recording(sock, recording_id)

    fake_session = MagicMock(socket_path=meta.socket_path, session_id=meta.session_id)

    def _extract_json(output: str) -> Any:
        """Extract JSON from CLI output, skipping log lines."""
        lines = output.splitlines()
        for i, line in enumerate(lines):
            if line and line[0] in "[{":
                try:
                    return json.loads("\n".join(lines[i:]))
                except json.JSONDecodeError:
                    continue
        raise ValueError(f"No JSON found in CLI output: {output!r}")

    def _cli_replay() -> tuple[int, Any]:
        runner = CliRunner()
        with patch("frontprompt.cli._resolve_session", return_value=fake_session):
            r = runner.invoke(cli_main, ["recordings", "replay", recording_id])
        if r.exit_code != 0:
            return r.exit_code, r.output
        return r.exit_code, _extract_json(r.output)

    # Run CLI in a thread to avoid asyncio event-loop nesting
    cli_exit, cli_result = await anyio.to_thread.run_sync(_cli_replay)
    assert cli_exit == 0, (
        f"CLI recordings replay failed with exit code {cli_exit}. Output: {cli_result!r}"
    )
    assert isinstance(cli_result, dict), (
        f"Expected dict from CLI recordings replay, got: {type(cli_result).__name__}"
    )
    assert "status" in cli_result, (
        f"Expected 'status' key in CLI replay JSON output: {cli_result}"
    )
    assert cli_result["status"] == "completed", (
        f"Expected status=completed from CLI replay, got: {cli_result.get('status')!r}"
    )


@pytest.mark.anyio
@_SKIP
async def test_replay_report_persistence(anyio_backend: str) -> None:
    """Scenario 9: Run replay → fetch stored report via GetReplayReportRequest → shape matches.

    Verifies that the ReplayReport is persisted in SQLite during RunReplayRequest and
    can be retrieved later via GetReplayReportRequest. This exercises the durable
    SQLite replay_reports table and the get_replay_report StateManager method.
    """
    sock = await _get_socket()

    await query(sock, NavigateRequest(url=_playground_base + "/replay-fixture.html"))
    await anyio.sleep(0.3)

    recording_id = await _start_recording(sock, "report-persistence-test")
    await query(sock, EvalJsRequest(
        expression="document.querySelector('#btn-click').click()",
        mutating=True,
    ))
    await _wait_for_entry_count(sock, recording_id, 1)
    await _stop_recording(sock, recording_id)

    # Reset page before replay
    await query(sock, NavigateRequest(url=_playground_base + "/replay-fixture.html"))
    await anyio.sleep(0.3)

    # Run replay to generate and persist a report
    replay_resp = await query(sock, RunReplayRequest(recording_id=recording_id))
    assert replay_resp.ok, f"RunReplayRequest failed: {replay_resp.error}"
    replay_id = replay_resp.data["replay_id"]

    # Fetch the persisted report from SQLite via GetReplayReportRequest
    report_resp = await query(sock, GetReplayReportRequest(replay_id=replay_id))
    assert report_resp.ok, (
        f"GetReplayReportRequest failed: {report_resp.error}. "
        f"Report may not have been persisted to SQLite during RunReplayRequest."
    )

    stored = report_resp.data
    # Shape matches original report
    assert stored["replay_id"] == replay_id, (
        f"replay_id mismatch: stored={stored['replay_id']!r} != original={replay_id!r}"
    )
    assert stored["recording_id"] == recording_id, (
        f"recording_id mismatch in stored report"
    )
    assert stored["status"] == replay_resp.data["status"], (
        f"status mismatch: stored={stored['status']!r} != original={replay_resp.data['status']!r}"
    )
    assert len(stored.get("step_results", [])) == len(replay_resp.data.get("step_results", [])), (
        f"step_results count mismatch: stored={len(stored.get('step_results', []))} "
        f"!= original={len(replay_resp.data.get('step_results', []))}"
    )
