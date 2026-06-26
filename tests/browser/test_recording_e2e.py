"""End-to-end recorder tests: 8 functional full-stack scenarios.

Uses LazyBrowserSessionProvider (real frontprompt show subprocess) + the served
playground HTTP fixture from conftest.py (playground_server / playground_url).

Scenarios:
  1 — capture round-trip + Python-owned gap-free seq
  2 — snapshot visibility regression guard (COL-2):
        GetSnapshotRequest shows recordings_state.active_recording_id
  3 — pick-during-recording auto-link:
        PickBySelectorRequest during active recording → pick_ref entry in timeline
  4 — cross-origin / navigation survival:
        active_recording_id unchanged + navigation entry after NavigateRequest
  5 — HUD-chrome exclusion:
        FloatingRecorderToolbar clicks NOT recorded
  6 — wire-economy (no wheel/scroll entries)
  7 — read-side parity:
        GetRecordingsRequest/GetRecordingRequest IPC ↔ CLI recordings list/get
  8 — UI render smoke (shadow-DOM):
        shadow-DOM eval shows Recordings tab + recording name in LeftPanel

Each scenario starts its own browser recording (start → drive → stop → assert) against
the module-scoped shared browser session (LazyBrowserSessionProvider).
No assumptions about pre-existing state — each scenario is self-contained.
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
    EvalJsRequest,
    GetRecordingRequest,
    GetRecordingsRequest,
    GetSnapshotRequest,
    NavigateRequest,
    PickBySelectorRequest,
)
from frontprompt.mcp_server import LazyBrowserSessionProvider


# ---------------------------------------------------------------------------
# Chromium availability guard
# ---------------------------------------------------------------------------


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


# ---------------------------------------------------------------------------
# Module-level session provider (one browser per module run)
# ---------------------------------------------------------------------------

_provider: LazyBrowserSessionProvider | None = None
_tmp_dir: Path | None = None
_playground_base: str = ""  # set by _setup_provider


@pytest.fixture(scope="module", autouse=True)
def _setup_provider(playground_server: str) -> Iterator[None]:
    """Spawn one frontprompt show subprocess for the whole module.

    Navigates to recorder-playground.html as the start URL.
    Each scenario navigates as needed, restoring state at the end.
    """
    global _provider, _tmp_dir, _playground_base
    _tmp_dir = Path(tempfile.mkdtemp(prefix="fp-e2e-rec07-", dir="/tmp"))
    _playground_base = playground_server
    _provider = LazyBrowserSessionProvider(playground_server + "/recorder-playground.html")
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


# ---------------------------------------------------------------------------
# Recording lifecycle helpers (identical pattern to test_recorder_playground_e2e.py)
# ---------------------------------------------------------------------------

_SCHEMA = "0.8.0"


async def _start_recording(sock: Path, name: str = "e2e-test") -> str:
    """Trigger recording_start_requested via window.__fp, wait for active_recording_id.

    After Python's StateManager confirms the recording is active (GetSnapshotRequest),
    waits an extra 200ms to ensure the state_snapshot broadcast has propagated to the
    Svelte frontend via page.evaluate. The EventInterceptor reads
    backendState.recordings.activeRecordingId (frontend state), so events fired before
    the broadcast completes are silently dropped.
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
                # Broadcast barrier: Python state is updated but the state_snapshot
                # page.evaluate to the Svelte frontend may still be in-flight.
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


# ---------------------------------------------------------------------------
# Scenario 1 — capture round-trip + gap-free seq
# ---------------------------------------------------------------------------


@pytest.mark.anyio
@_SKIP
async def test_capture_round_trip(anyio_backend: str) -> None:
    """Click and keydown on page elements; assert timeline has both event types + gap-free seq."""
    sock = await _get_socket()

    recording_id = await _start_recording(sock, "e2e-scenario-1")

    # Assert via GetRecordingsRequest that the recording exists and is active
    recordings_resp = await query(sock, GetRecordingsRequest())
    assert recordings_resp.ok, f"GetRecordingsRequest failed: {recordings_resp.error}"
    metas = recordings_resp.data
    active = [m for m in metas if m.get("recording_id") == recording_id]
    assert len(active) == 1, f"Expected 1 active recording for id={recording_id!r}, got metas: {metas}"
    assert active[0]["status"] == "active", f"Expected status=active, got: {active[0]}"

    # Click #btn-primary
    await query(
        sock,
        EvalJsRequest(
            expression="document.querySelector('#btn-primary').click()",
            mutating=True,
        ),
    )
    await _wait_for_entry_count(sock, recording_id, 1)

    # Keydown on #input-text
    await query(
        sock,
        EvalJsRequest(
            expression=(
                "(() => {"
                "  const el = document.querySelector('#input-text');"
                "  el.focus();"
                "  el.value = 'h';"
                "  el.dispatchEvent(new KeyboardEvent('keydown', {key: 'h', bubbles: true, cancelable: true}));"
                "})()"
            ),
            mutating=True,
        ),
    )
    await _wait_for_entry_count(sock, recording_id, 2)

    await _stop_recording(sock, recording_id)

    # Fetch full recording
    rec_resp = await query(sock, GetRecordingRequest(recording_id=recording_id))
    assert rec_resp.ok, f"GetRecordingRequest failed: {rec_resp.error}"
    entries = rec_resp.data["entries"]

    # At least 1 click and 1 keydown
    click_entries = [
        e for e in entries if e.get("kind") == "page_event" and e.get("event_type") == "click"
    ]
    keydown_entries = [
        e for e in entries if e.get("kind") == "page_event" and e.get("event_type") == "keydown"
    ]
    assert len(click_entries) >= 1, f"Expected ≥1 click entry, all entries: {entries}"
    assert len(keydown_entries) >= 1, f"Expected ≥1 keydown entry, all entries: {entries}"

    # Click targets #btn-primary
    assert any("btn-primary" in e.get("target", "") for e in click_entries), (
        f"Expected click on #btn-primary, targets: {[e.get('target') for e in click_entries]}"
    )

    # seq is gap-free monotone: [0, 1, 2, ..., N-1]
    seqs = [e["seq"] for e in entries]
    assert seqs == list(range(len(seqs))), f"seq not gap-free monotonic: {seqs}"

    # Recording status is stopped after _stop_recording
    assert rec_resp.data["status"] == "stopped", f"Expected stopped, got: {rec_resp.data['status']}"


# ---------------------------------------------------------------------------
# Scenario 2 — snapshot visibility regression guard (COL-2)
# ---------------------------------------------------------------------------


@pytest.mark.anyio
@_SKIP
async def test_snapshot_visibility_col2(anyio_backend: str) -> None:
    """GetSnapshotRequest reflects active_recording_id + non-empty recordings list (COL-2 guard)."""
    sock = await _get_socket()

    recording_id = await _start_recording(sock, "e2e-scenario-2")

    # Fetch snapshot while recording is active
    snap = await query(sock, GetSnapshotRequest())
    assert snap.ok, f"GetSnapshotRequest failed: {snap.error}"

    recordings_state = snap.data.get("recordings_state", {})
    assert recordings_state.get("active_recording_id") == recording_id, (
        f"Expected active_recording_id={recording_id!r}, got: {recordings_state}"
    )
    assert len(recordings_state.get("recordings", [])) > 0, (
        f"Expected non-empty recordings list in snapshot.recordings_state, got: {recordings_state}"
    )

    # The active recording must appear in the recordings list
    meta = next(
        (m for m in recordings_state["recordings"] if m["recording_id"] == recording_id),
        None,
    )
    assert meta is not None, (
        f"Recording {recording_id!r} missing from snapshot.recordings_state.recordings — "
        f"COL-2: StateManager.snapshot() not wired to live _recordings_state"
    )
    assert meta["status"] == "active", (
        f"Expected status=active in snapshot recording meta, got: {meta}"
    )

    await _stop_recording(sock, recording_id)


# ---------------------------------------------------------------------------
# Scenario 3 — pick-during-recording auto-link
# ---------------------------------------------------------------------------


@pytest.mark.anyio
@_SKIP
async def test_pick_during_recording_auto_link(anyio_backend: str) -> None:
    """PickBySelectorRequest during active recording auto-links as pick_ref timeline entry."""
    sock = await _get_socket()

    recording_id = await _start_recording(sock, "e2e-scenario-3")

    # Programmatic pick while recording is active
    pick_resp = await query(
        sock,
        PickBySelectorRequest(selector="#btn-primary", comment="during-recording-auto-link", limit=1),
    )
    assert pick_resp.ok, f"PickBySelectorRequest failed: {pick_resp.error}"
    assert pick_resp.data["captured"] == 1, f"Expected 1 pick captured, got: {pick_resp.data}"
    pick_id = pick_resp.data["pick_ids"][0]

    # Wait for pick_ref entry to appear in the timeline
    entries = await _wait_for_entry_count(sock, recording_id, 1)

    await _stop_recording(sock, recording_id)

    # Assert pick_ref entry with matching pick_id
    pick_refs = [e for e in entries if e.get("kind") == "pick_ref"]
    assert len(pick_refs) >= 1, (
        f"Expected ≥1 pick_ref entry, got kinds: {[e['kind'] for e in entries]}"
    )
    matching = [p for p in pick_refs if p.get("pick_id") == pick_id]
    assert len(matching) >= 1, (
        f"Expected pick_ref entry with pick_id={pick_id!r}, "
        f"pick_ref entries: {pick_refs}"
    )

    # seq is interleaved correctly (pick_ref must be in the seq order)
    seqs = [e["seq"] for e in entries]
    assert seqs == list(range(len(seqs))), f"seq not monotonic: {seqs}"


# ---------------------------------------------------------------------------
# Scenario 4 — cross-origin / navigation survival
# ---------------------------------------------------------------------------


@pytest.mark.anyio
@_SKIP
async def test_cross_origin_nav_survival(anyio_backend: str) -> None:
    """active_recording_id survives NavigateRequest; timeline gains navigation entry."""
    sock = await _get_socket()
    page_a = _playground_base + "/recorder-playground.html"
    page_b = _playground_base + "/recorder-playground-2.html"

    # Ensure we're on page A first
    await query(sock, NavigateRequest(url=page_a))
    await anyio.sleep(0.3)  # allow overlay to reinitialize

    recording_id = await _start_recording(sock, "e2e-scenario-4")

    # Click something on page A (adds page_event entry)
    await query(
        sock,
        EvalJsRequest(
            expression="document.querySelector('#btn-primary').click()",
            mutating=True,
        ),
    )
    await _wait_for_entry_count(sock, recording_id, 1)

    # Navigate to page B
    nav_resp = await query(sock, NavigateRequest(url=page_b))
    assert nav_resp.ok, f"NavigateRequest to page B failed: {nav_resp.error}"

    # Poll: active_recording_id must STILL be set after navigation (cross-origin survival)
    for _ in range(30):
        snap = await query(sock, GetSnapshotRequest())
        if snap.ok:
            rid = snap.data.get("recordings_state", {}).get("active_recording_id")
            if rid == recording_id:
                break
        await anyio.sleep(0.1)
    else:
        snap = await query(sock, GetSnapshotRequest())
        rid = snap.data.get("recordings_state", {}).get("active_recording_id") if snap.ok else None
        raise AssertionError(
            f"active_recording_id changed after navigation — cross-origin survival broken. "
            f"Expected {recording_id!r}, got {rid!r}"
        )

    # Wait for navigation entry to appear (Python observes URL change → NavigationEntry)
    await _wait_for_entry_count(sock, recording_id, 2)

    await _stop_recording(sock, recording_id)

    # Restore navigation to page A for subsequent tests
    await query(sock, NavigateRequest(url=page_a))
    await anyio.sleep(0.3)

    # Fetch full recording
    rec_resp = await query(sock, GetRecordingRequest(recording_id=recording_id))
    assert rec_resp.ok
    entries = rec_resp.data["entries"]

    # Assert navigation entry with correct from_url / to_url
    nav_entries = [e for e in entries if e.get("kind") == "navigation"]
    assert len(nav_entries) >= 1, (
        f"Expected ≥1 navigation entry, entry kinds: {[e['kind'] for e in entries]}"
    )
    nav_entry = nav_entries[0]
    assert page_a in nav_entry.get("from_url", ""), (
        f"Expected from_url to contain {page_a!r}, got nav_entry: {nav_entry}"
    )
    # to_url matches page_b (may have trailing fragment or query)
    assert page_b in nav_entry.get("to_url", "") or nav_entry.get("to_url", "") == page_b, (
        f"Expected to_url to contain {page_b!r}, got nav_entry: {nav_entry}"
    )

    # Click on page A also appears (page_event before nav entry)
    click_entries = [
        e for e in entries if e.get("kind") == "page_event" and e.get("event_type") == "click"
    ]
    assert len(click_entries) >= 1, (
        f"Expected ≥1 click entry (from page A), all entries: {entries}"
    )


# ---------------------------------------------------------------------------
# Scenario 5 — HUD-chrome exclusion
# ---------------------------------------------------------------------------

# JavaScript that clicks the FloatingRecorderToolbar drag handle.
# The handle is inside the <fp-overlay> shadow root — isHudChrome=true means
# this click must NOT appear as a page_event in the recording timeline.
_CLICK_TOOLBAR_DRAG_HANDLE_JS = """
(() => {
  const overlay = document.querySelector('fp-overlay');
  if (!overlay || !overlay.shadowRoot) return 'no-overlay';
  const handle = overlay.shadowRoot.querySelector('.rec-toolbar__drag-handle');
  if (!handle) return 'no-toolbar';
  handle.click();
  return 'clicked';
})()
"""


@pytest.mark.anyio
@_SKIP
async def test_hud_chrome_exclusion(anyio_backend: str) -> None:
    """FloatingRecorderToolbar drag-handle clicks are excluded from recording timeline."""
    sock = await _get_socket()

    recording_id = await _start_recording(sock, "e2e-scenario-5")

    # Click a real page element first — proves recording IS capturing events
    await query(
        sock,
        EvalJsRequest(
            expression="document.querySelector('#btn-primary').click()",
            mutating=True,
        ),
    )
    await _wait_for_entry_count(sock, recording_id, 1)

    # Click on the FloatingRecorderToolbar drag handle (HUD chrome — must be excluded)
    toolbar_result = await query(
        sock, EvalJsRequest(expression=_CLICK_TOOLBAR_DRAG_HANDLE_JS, mutating=False)
    )
    assert toolbar_result.ok, f"Toolbar click eval failed: {toolbar_result.error}"
    result_val = toolbar_result.data.get("result") if toolbar_result.ok else None
    assert result_val == "clicked", (
        f"Expected toolbar drag-handle to be found and clicked, got: {result_val!r}. "
        f"FloatingRecorderToolbar may not be rendered yet — broadcast barrier not waited?"
    )

    # Wait to ensure no delayed entry slips through
    await anyio.sleep(0.3)

    await _stop_recording(sock, recording_id)

    rec_resp = await query(sock, GetRecordingRequest(recording_id=recording_id))
    assert rec_resp.ok
    entries = rec_resp.data["entries"]

    # Exactly 1 page_event: the btn-primary click only
    page_events = [e for e in entries if e.get("kind") == "page_event"]
    assert len(page_events) == 1, (
        f"Expected exactly 1 page_event (btn-primary click, toolbar excluded), "
        f"got {len(page_events)} page_events: "
        f"{[{'event_type': e.get('event_type'), 'target': e.get('target')} for e in page_events]}"
    )
    assert "btn-primary" in page_events[0].get("target", ""), (
        f"Expected the single page_event to target #btn-primary, got: {page_events[0]}"
    )


# ---------------------------------------------------------------------------
# Scenario 6 — wire-economy (no wheel/scroll entries)
# ---------------------------------------------------------------------------

_DISPATCH_WHEEL_SCROLL_JS = """
(() => {
  document.dispatchEvent(new WheelEvent('wheel', {bubbles: true, cancelable: true, deltaY: 100}));
  window.dispatchEvent(new Event('scroll'));
  document.dispatchEvent(new WheelEvent('wheel', {bubbles: true, cancelable: true, deltaY: -50}));
  window.dispatchEvent(new Event('scroll'));
  return 'dispatched';
})()
"""


@pytest.mark.anyio
@_SKIP
async def test_wire_economy_no_wheel_scroll(anyio_backend: str) -> None:
    """wheel and scroll events are NOT forwarded to recording timeline (wire-economy guard)."""
    sock = await _get_socket()

    recording_id = await _start_recording(sock, "e2e-scenario-6")

    # Dispatch wheel + scroll events
    result = await query(
        sock, EvalJsRequest(expression=_DISPATCH_WHEEL_SCROLL_JS, mutating=False)
    )
    assert result.ok, f"Wheel/scroll dispatch failed: {result.error}"

    # Wait to allow any in-flight forwarding (there should be none)
    await anyio.sleep(0.3)

    await _stop_recording(sock, recording_id)

    rec_resp = await query(sock, GetRecordingRequest(recording_id=recording_id))
    assert rec_resp.ok
    entries = rec_resp.data["entries"]

    # Zero page_events — wheel/scroll are excluded for wire-economy
    page_events = [e for e in entries if e.get("kind") == "page_event"]
    assert len(page_events) == 0, (
        f"Expected 0 page_events (wheel/scroll excluded), got {len(page_events)}: "
        f"{[{'event_type': e.get('event_type'), 'target': e.get('target')} for e in page_events]}"
    )


# ---------------------------------------------------------------------------
# Scenario 7 — read-side parity (CLI ↔ IPC)
# ---------------------------------------------------------------------------


@pytest.mark.anyio
@_SKIP
async def test_read_side_parity_cli_ipc(anyio_backend: str) -> None:
    """CLI recordings list/get returns same data as IPC GetRecordingsRequest/GetRecordingRequest."""
    sock = await _get_socket()
    assert _provider is not None
    meta = await _provider.get()

    # Create a stopped recording with at least one event
    recording_id = await _start_recording(sock, "e2e-scenario-7")
    await query(
        sock,
        EvalJsRequest(
            expression="document.querySelector('#btn-primary').click()",
            mutating=True,
        ),
    )
    await _wait_for_entry_count(sock, recording_id, 1)
    await _stop_recording(sock, recording_id)

    # IPC: read recordings list and full recording
    ipc_list_resp = await query(sock, GetRecordingsRequest())
    assert ipc_list_resp.ok, f"GetRecordingsRequest failed: {ipc_list_resp.error}"
    ipc_recordings: list[dict[str, Any]] = ipc_list_resp.data

    ipc_get_resp = await query(sock, GetRecordingRequest(recording_id=recording_id))
    assert ipc_get_resp.ok, f"GetRecordingRequest failed: {ipc_get_resp.error}"
    ipc_recording: dict[str, Any] = ipc_get_resp.data

    # CLI: run in thread (anyio.to_thread.run_sync) to avoid event-loop nesting with
    # the CLI's internal anyio.run(). The worker thread creates a fresh event loop.
    fake_session = MagicMock(socket_path=meta.socket_path, session_id=meta.session_id)

    def _extract_json(output: str) -> Any:
        # Click 8.2+ removed mix_stderr; structlog log lines are prepended to output.
        # Log lines also start with '[' (e.g. "[info     ] ..."), so we try each
        # line-start candidate in order and keep the first that parses cleanly.
        lines = output.splitlines()
        for i, line in enumerate(lines):
            if line and line[0] in "[{":
                try:
                    return json.loads("\n".join(lines[i:]))
                except json.JSONDecodeError:
                    continue
        raise ValueError(f"No JSON found in CLI output: {output!r}")

    def _cli_list() -> tuple[int, Any]:
        runner = CliRunner()
        with patch("frontprompt.cli._resolve_session", return_value=fake_session):
            r = runner.invoke(cli_main, ["recordings", "list"])
        if r.exit_code != 0:
            return r.exit_code, r.output
        return r.exit_code, _extract_json(r.output)

    def _cli_get() -> tuple[int, Any]:
        runner = CliRunner()
        with patch("frontprompt.cli._resolve_session", return_value=fake_session):
            r = runner.invoke(cli_main, ["recordings", "get", recording_id])
        if r.exit_code != 0:
            return r.exit_code, r.output
        return r.exit_code, _extract_json(r.output)

    cli_list_exit, cli_recordings = await anyio.to_thread.run_sync(_cli_list)
    assert cli_list_exit == 0, (
        f"CLI recordings list failed (exit {cli_list_exit}): {cli_recordings}"
    )

    cli_get_exit, cli_recording = await anyio.to_thread.run_sync(_cli_get)
    assert cli_get_exit == 0, (
        f"CLI recordings get failed (exit {cli_get_exit}): {cli_recording}"
    )

    # Parity: our recording appears in both IPC list and CLI list
    ipc_ids = {r["recording_id"] for r in ipc_recordings}
    cli_ids = {r["recording_id"] for r in cli_recordings}
    assert recording_id in ipc_ids, (
        f"IPC list missing recording {recording_id!r}: {ipc_recordings}"
    )
    assert recording_id in cli_ids, (
        f"CLI list missing recording {recording_id!r}: {cli_recordings}"
    )

    # Parity: full recording shape matches
    assert cli_recording["recording_id"] == ipc_recording["recording_id"], (
        f"recording_id mismatch: CLI={cli_recording['recording_id']!r} vs IPC={ipc_recording['recording_id']!r}"
    )
    assert cli_recording["name"] == ipc_recording["name"], (
        f"name mismatch: CLI={cli_recording['name']!r} vs IPC={ipc_recording['name']!r}"
    )
    assert cli_recording["status"] == ipc_recording["status"], (
        f"status mismatch: CLI={cli_recording['status']!r} vs IPC={ipc_recording['status']!r}"
    )
    assert cli_recording["status"] == "stopped", (
        f"Expected recording to be stopped, got: {cli_recording['status']!r}"
    )
    # Entry count parity
    cli_entry_count = len(cli_recording.get("entries", []))
    ipc_entry_count = len(ipc_recording.get("entries", []))
    assert cli_entry_count == ipc_entry_count, (
        f"CLI and IPC entry counts differ: CLI={cli_entry_count}, IPC={ipc_entry_count}"
    )
    assert ipc_entry_count >= 1, (
        f"Expected ≥1 entry in full recording (from the click), got: {ipc_entry_count}"
    )


# ---------------------------------------------------------------------------
# Scenario 8 — UI render smoke (shadow-DOM eval)
# ---------------------------------------------------------------------------

# Click the Recordings tab button inside the <fp-overlay> shadow root.
# The TabbedPanel renders one <button role="tab"> per tab; we find the one
# whose label starts with "Recordings".
_CLICK_RECORDINGS_TAB_JS = """
(() => {
  const overlay = document.querySelector('fp-overlay');
  if (!overlay || !overlay.shadowRoot) return 'no-overlay';
  const buttons = Array.from(overlay.shadowRoot.querySelectorAll('button[role="tab"]'));
  const recBtn = buttons.find(b => (b.textContent || '').trim().startsWith('Recordings'));
  if (!recBtn) return 'tab-not-found';
  recBtn.click();
  return 'clicked';
})()
"""

# Read the full text content of the fp-overlay shadow root — used to verify
# the Recordings tab and recording name are rendered.
_READ_SHADOW_TEXT_JS = """
(() => {
  const overlay = document.querySelector('fp-overlay');
  if (!overlay || !overlay.shadowRoot) return '';
  return (overlay.shadowRoot.textContent || '').replace(/\\s+/g, ' ').trim();
})()
"""


@pytest.mark.anyio
@_SKIP
async def test_ui_render_smoke(anyio_backend: str) -> None:
    """Shadow-DOM eval confirms the Recordings tab exists and renders the recording name.

    MIS-005: this is the load-bearing guard for phantom-CSS and unmounted-component
    regressions — jsdom/vitest (sub-plan 05) cannot see shadow-DOM CSS import failures.
    Do NOT remove this test as 'redundant with vitest'.
    """
    sock = await _get_socket()

    # Create a stopped recording with a unique name so we can find it in the DOM
    rec_name = "ui-smoke-e2e-test"
    recording_id = await _start_recording(sock, rec_name)
    await _stop_recording(sock, recording_id)

    # Click the Recordings tab in the LeftPanel (inside fp-overlay shadow root)
    tab_result = await query(
        sock, EvalJsRequest(expression=_CLICK_RECORDINGS_TAB_JS, mutating=False)
    )
    assert tab_result.ok, f"Recordings tab click eval failed: {tab_result.error}"
    result_val = tab_result.data.get("result") if tab_result.ok else None
    assert result_val == "clicked", (
        f"Expected Recordings tab to be found and clicked, got: {result_val!r}. "
        f"Possible causes: left panel not open, tab label changed, shadow DOM not accessible."
    )

    # Wait for Svelte's reactive re-render to complete
    await anyio.sleep(0.4)

    # Read the shadow DOM text content
    text_result = await query(
        sock, EvalJsRequest(expression=_READ_SHADOW_TEXT_JS, mutating=False)
    )
    assert text_result.ok, f"Shadow DOM text read failed: {text_result.error}"
    shadow_text = text_result.data.get("result", "") if text_result.ok else ""
    assert isinstance(shadow_text, str) and len(shadow_text) > 0, (
        f"Expected non-empty shadow DOM text content, got: {shadow_text!r}"
    )

    # Assert "Recordings" tab label is rendered in the shadow DOM
    assert "Recordings" in shadow_text, (
        f"Expected 'Recordings' tab label in shadow DOM text, "
        f"got excerpt: {shadow_text[:500]!r}"
    )

    # Assert the recording name appears in the RecordingsTab list
    assert rec_name in shadow_text, (
        f"Expected recording name {rec_name!r} in shadow DOM text (RecordingsTab list), "
        f"got excerpt: {shadow_text[:500]!r}. "
        f"RecordingsTab may not be rendering the list correctly."
    )
