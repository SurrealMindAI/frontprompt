"""End-to-end recorder tests: playground round-trip, screenshot report, all-entry-kinds, parametrized.

Uses LazyBrowserSessionProvider (real frontprompt show subprocess) + the served
playground HTTP fixture from conftest.py (playground_server / playground_url).

Scenarios:
  A — fixture-equality round-trip: scripted interaction → recording matches oracle fixture.
  B — screenshot-per-event visual report: before/after PNGs for each event, HTML report.
  C — every-entry-kind: page_event + pick_ref + region_ref + relation_ref + navigation.
  D — data-driven parametrized: table-driven single-event scenarios, easy to extend.

Each scenario uses the module-scoped session provider (one browser for the full module)
but manages its own recording lifecycle (start → drive → stop → assert).
"""

from __future__ import annotations

import base64
import json
import shutil
import tempfile
import uuid
from collections.abc import Iterator
from pathlib import Path
from typing import Any

import anyio
import pytest

from frontprompt.ipc import query
from frontprompt.ipc.protocol import (
    EvalJsRequest,
    GetRecordingRequest,
    GetSnapshotRequest,
    NavigateRequest,
    PickBySelectorRequest,
    ScreenshotPageRequest,
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
    _tmp_dir = Path(tempfile.mkdtemp(prefix="fp-e2e-rec-", dir="/tmp"))
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
# Recording lifecycle helpers
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
    # Poll until active_recording_id is set (handler runs asynchronously).
    for _ in range(20):
        snap = await query(sock, GetSnapshotRequest())
        if snap.ok:
            rid = snap.data.get("recordings_state", {}).get("active_recording_id")
            if rid:
                # Broadcast barrier: Python state is updated but the state_snapshot
                # page.evaluate to the Svelte frontend may still be in-flight in the
                # show_session process. Sleep 200ms so the show_session event loop
                # completes the broadcast before the test fires any intercepted events.
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
    for _ in range(retries):
        rec = await query(sock, GetRecordingRequest(recording_id=recording_id))
        if rec.ok:
            entries = rec.data.get("entries", [])
            if len(entries) >= expected_count:
                return entries
        await anyio.sleep(0.1)
    entries = rec.data.get("entries", []) if rec.ok else []
    raise AssertionError(
        f"Expected {expected_count} entries, got {len(entries)}. "
        f"Entries: {[e.get('event_type', e.get('kind')) for e in entries]}"
    )


# ---------------------------------------------------------------------------
# Interaction helpers
# ---------------------------------------------------------------------------

_CLICK_BTN_PRIMARY = "document.querySelector('#btn-primary').click()"
_CLICK_BTN_SECONDARY = "document.querySelector('#btn-secondary').click()"

_TYPE_A_INTO_INPUT_TEXT = """
(() => {
  const el = document.querySelector('#input-text');
  el.focus();
  el.value = 'a';
  el.dispatchEvent(new KeyboardEvent('keydown', {key: 'a', bubbles: true, cancelable: true}));
})()
""".strip()

_TYPE_7_INTO_INPUT_TEXT = """
(() => {
  const el = document.querySelector('#input-text');
  el.value += '7';
  el.dispatchEvent(new KeyboardEvent('keydown', {key: '7', bubbles: true, cancelable: true}));
})()
""".strip()

_DRAG_SOURCE_TO_DROP_ZONE = """
(() => {
  document.querySelector('#drag-source').dispatchEvent(
    new PointerEvent('pointerdown', {bubbles: true, cancelable: true})
  );
  document.querySelector('#drop-zone').dispatchEvent(
    new DragEvent('drop', {bubbles: true, cancelable: true})
  );
})()
""".strip()


# ---------------------------------------------------------------------------
# Normalization helpers
# ---------------------------------------------------------------------------

_FIXTURE_PATH = (
    Path(__file__).parent / "fixtures" / "recorder" / "click-type-drag.recording.json"
)


def _normalize_entry(entry: dict[str, Any]) -> dict[str, Any]:
    """Strip volatile fields (timestamp_ms, seq) for fixture comparison."""
    return {
        "kind": entry["kind"],
        "event_type": entry.get("event_type"),
        "target": entry.get("target"),
        "target_path": entry.get("target_path"),
        "key": entry.get("key"),
    }


def _load_fixture() -> dict[str, Any]:
    with open(_FIXTURE_PATH) as f:
        return json.load(f)


# ---------------------------------------------------------------------------
# Scenario A — fixture-equality round-trip
# ---------------------------------------------------------------------------


@pytest.mark.anyio
@_SKIP
async def test_fixture_equality_round_trip(anyio_backend: str) -> None:
    """Drive click→type→drag on recorder-playground.html, assert normalized timeline equals fixture."""
    sock = await _get_socket()

    recording_id = await _start_recording(sock, name="fixture-equality")

    # 1. Click #btn-primary
    await query(sock, EvalJsRequest(expression=_CLICK_BTN_PRIMARY, mutating=True))
    await _wait_for_entry_count(sock, recording_id, 1)

    # 2. Type 'a' into #input-text
    await query(sock, EvalJsRequest(expression=_TYPE_A_INTO_INPUT_TEXT, mutating=True))
    await _wait_for_entry_count(sock, recording_id, 2)

    # 3. Type '7' into #input-text
    await query(sock, EvalJsRequest(expression=_TYPE_7_INTO_INPUT_TEXT, mutating=True))
    await _wait_for_entry_count(sock, recording_id, 3)

    # 4. Drag #drag-source → #drop-zone (captures pointerdown)
    await query(sock, EvalJsRequest(expression=_DRAG_SOURCE_TO_DROP_ZONE, mutating=True))
    await _wait_for_entry_count(sock, recording_id, 4)

    await _stop_recording(sock, recording_id)

    # Fetch full recording
    rec_resp = await query(sock, GetRecordingRequest(recording_id=recording_id))
    assert rec_resp.ok, f"GetRecordingRequest failed: {rec_resp.error}"
    recording = rec_resp.data
    entries = recording["entries"]

    # Load fixture oracle
    fixture = _load_fixture()

    # Assert entry count matches
    assert len(entries) == fixture["entry_count"], (
        f"Expected {fixture['entry_count']} entries, got {len(entries)}. "
        f"Actual: {[_normalize_entry(e) for e in entries]}"
    )

    # Assert each entry's normalized shape matches fixture
    for i, (actual, expected) in enumerate(zip(entries, fixture["entries"])):
        norm = _normalize_entry(actual)
        assert norm["kind"] == expected["kind"], (
            f"Entry {i}: kind mismatch — {norm['kind']!r} != {expected['kind']!r}"
        )
        assert norm["event_type"] == expected.get("event_type"), (
            f"Entry {i}: event_type mismatch — {norm['event_type']!r} != {expected.get('event_type')!r}"
        )
        assert norm["target"] == expected["target"], (
            f"Entry {i}: target mismatch — {norm['target']!r} != {expected['target']!r}"
        )
        assert norm["target_path"] == expected["target_path"], (
            f"Entry {i}: target_path mismatch — {norm['target_path']} != {expected['target_path']}"
        )
        assert norm["key"] == expected.get("key"), (
            f"Entry {i}: key mismatch — {norm['key']!r} != {expected.get('key')!r}"
        )

    # Assert seq is gap-free monotonic (0, 1, 2, 3)
    seqs = [e["seq"] for e in entries]
    assert seqs == list(range(len(seqs))), f"seq not gap-free monotonic: {seqs}"

    # Assert recording status is stopped
    assert recording["status"] == "stopped", f"Expected stopped, got: {recording['status']}"


# ---------------------------------------------------------------------------
# Scenario B — screenshot-per-event visual report
# ---------------------------------------------------------------------------

# Runtime artifact — gitignored (produced only when test runs with chromium).
_REPORT_PATH = Path("/tmp/recorder-e2e-report.html")


async def _screenshot_path(sock: Path) -> Path:
    """Take a page viewport screenshot and return its path."""
    resp = await query(sock, ScreenshotPageRequest(full_page=False))
    assert resp.ok, f"ScreenshotPageRequest failed: {resp}"
    return Path(resp.data["path"])


def _png_to_b64(path: Path) -> str:
    return base64.b64encode(path.read_bytes()).decode("ascii")


def _write_visual_report(
    pairs: list[dict[str, Any]],
    report_path: Path,
) -> None:
    """Write a self-contained HTML with inline base64 before/after screenshot pairs.

    Each pair: {seq, event_type, target, before_path, after_path}.
    No external resources or JavaScript.
    """
    rows = []
    for pair in pairs:
        seq = pair["seq"]
        evtype = pair["event_type"]
        target = pair["target"]
        before_b64 = _png_to_b64(pair["before_path"])
        after_b64 = _png_to_b64(pair["after_path"])
        rows.append(
            f"<tr>"
            f"<td><b>seq={seq}</b><br/>{evtype}<br/><small>{target}</small></td>"
            f'<td><img src="data:image/png;base64,{before_b64}" style="max-width:400px;" alt="before"/></td>'
            f'<td><img src="data:image/png;base64,{after_b64}" style="max-width:400px;" alt="after"/></td>'
            f"</tr>"
        )
    html = (
        "<!DOCTYPE html><html><head><title>Recorder E2E Report</title>"
        "<style>table{border-collapse:collapse}td{border:1px solid #ccc;padding:8px;vertical-align:top}</style>"
        "</head><body>"
        "<h1>Recorder E2E Visual Report</h1>"
        "<table><thead><tr><th>Event</th><th>Before</th><th>After</th></tr></thead>"
        "<tbody>" + "\n".join(rows) + "</tbody></table>"
        "</body></html>"
    )
    report_path.write_text(html, encoding="utf-8")


@pytest.mark.anyio
@_SKIP
async def test_screenshot_per_event_visual_report(anyio_backend: str) -> None:
    """Capture before/after screenshots around each event and produce a visual HTML report."""
    sock = await _get_socket()

    # Reset DOM: navigate to a fresh recorder-playground.html so #drop-zone is in its
    # initial (un-dropped) state. The shared browser session persists DOM across tests —
    # test_fixture_equality_round_trip runs the same drag-drop and leaves #drop-zone
    # showing "Dropped!" with lightgreen background, making before/after identical.
    nav_resp = await query(sock, NavigateRequest(url=_playground_base + "/recorder-playground.html"))
    assert nav_resp.ok, f"Navigate to fresh playground failed: {nav_resp.error}"
    await anyio.sleep(0.3)  # allow overlay to reinitialize after navigation

    recording_id = await _start_recording(sock, name="screenshot-report")

    pairs: list[dict[str, Any]] = []

    # --- Event 1: click #btn-primary ---
    before_click = await _screenshot_path(sock)
    await query(sock, EvalJsRequest(expression=_CLICK_BTN_PRIMARY, mutating=True))
    await _wait_for_entry_count(sock, recording_id, 1)
    after_click = await _screenshot_path(sock)
    pairs.append({
        "seq": 0, "event_type": "click", "target": "button#btn-primary",
        "before_path": before_click, "after_path": after_click,
    })

    # --- Event 2: type 'a' into #input-text ---
    before_type_a = await _screenshot_path(sock)
    await query(sock, EvalJsRequest(expression=_TYPE_A_INTO_INPUT_TEXT, mutating=True))
    await _wait_for_entry_count(sock, recording_id, 2)
    after_type_a = await _screenshot_path(sock)
    pairs.append({
        "seq": 1, "event_type": "keydown", "target": "input#input-text",
        "before_path": before_type_a, "after_path": after_type_a,
    })

    # --- Event 3: type '7' into #input-text ---
    before_type_7 = await _screenshot_path(sock)
    await query(sock, EvalJsRequest(expression=_TYPE_7_INTO_INPUT_TEXT, mutating=True))
    await _wait_for_entry_count(sock, recording_id, 3)
    after_type_7 = await _screenshot_path(sock)
    pairs.append({
        "seq": 2, "event_type": "keydown", "target": "input#input-text",
        "before_path": before_type_7, "after_path": after_type_7,
    })

    # --- Event 4: drag #drag-source → #drop-zone ---
    before_drag = await _screenshot_path(sock)
    await query(sock, EvalJsRequest(expression=_DRAG_SOURCE_TO_DROP_ZONE, mutating=True))
    await _wait_for_entry_count(sock, recording_id, 4)
    after_drag = await _screenshot_path(sock)
    pairs.append({
        "seq": 3, "event_type": "pointerdown+drop", "target": "#drag-source→#drop-zone",
        "before_path": before_drag, "after_path": after_drag,
    })

    await _stop_recording(sock, recording_id)

    # Write visual report
    _write_visual_report(pairs, _REPORT_PATH)
    assert _REPORT_PATH.exists(), f"Report not written at {_REPORT_PATH}"
    assert _REPORT_PATH.stat().st_size > 0, "Report is empty"

    # Assert report has one row per pair (4 page_events)
    report_content = _REPORT_PATH.read_text()
    assert report_content.count("<tr>") >= len(pairs), (
        f"Expected {len(pairs)} rows in report, report content starts: {report_content[:200]}"
    )

    # Assert type and drag produce non-identical before/after screenshots
    for pair in pairs:
        if pair["event_type"] in ("keydown", "pointerdown+drop"):
            before_bytes = pair["before_path"].read_bytes()
            after_bytes = pair["after_path"].read_bytes()
            assert before_bytes != after_bytes, (
                f"Expected before/after to differ for {pair['event_type']} on {pair['target']}, "
                f"but PNGs are identical (DOM change not reflected)"
            )


# ---------------------------------------------------------------------------
# Scenario C — every-entry-kind coverage
# ---------------------------------------------------------------------------

_CREATE_REGION_EXPR = """
(() => {{
  const region = {{
    region_id: '{region_id}',
    rect: {{x: 10, y: 10, width: 80, height: 40}},
    member_pick_ids: [],
    note: null,
    timestamp_ms: Date.now(),
    color_index: 0,
    viewport_snapshot: null,
    origin_session: null
  }};
  return window.__fp({{
    kind: 'region_created_requested',
    schema_version: '{schema}',
    region: region
  }});
}})()
"""

_CREATE_RELATION_EXPR = """
(() => {{
  const rel = {{
    relation_id: '{relation_id}',
    source_id: '{source_pick_id}',
    source_kind: 'pick',
    target_id: '{target_pick_id}',
    target_kind: 'pick',
    kind: 'relates_to',
    note: null,
    timestamp_ms: Date.now(),
    origin_session: null
  }};
  return window.__fp({{
    kind: 'relation_created_requested',
    schema_version: '{schema}',
    relation: rel
  }});
}})()
"""


@pytest.mark.anyio
@_SKIP
async def test_every_timeline_entry_kind(anyio_backend: str) -> None:
    """Assert every TimelineEntry kind (page_event, pick_ref, region_ref, relation_ref, navigation) appears."""
    sock = await _get_socket()
    playground2_url = _playground_base + "/recorder-playground-2.html"
    playground1_url = _playground_base + "/recorder-playground.html"

    recording_id = await _start_recording(sock, name="every-kind")
    expected_count = 0

    # 1. page_event — click
    await query(sock, EvalJsRequest(expression=_CLICK_BTN_PRIMARY, mutating=True))
    expected_count += 1
    await _wait_for_entry_count(sock, recording_id, expected_count)

    # 2. pick_ref — PickBySelectorRequest auto-appends PickRefEntry when recording is active
    pick_resp = await query(sock, PickBySelectorRequest(selector="#btn-primary", comment="for pick_ref", limit=1))
    assert pick_resp.ok, f"PickBySelectorRequest failed: {pick_resp}"
    pick_id_1 = pick_resp.data["pick_ids"][0]
    expected_count += 1
    await _wait_for_entry_count(sock, recording_id, expected_count)

    # 3. pick_ref (second pick, needed for relation source/target)
    pick_resp2 = await query(
        sock, PickBySelectorRequest(selector="#btn-secondary", comment="for relation", limit=1)
    )
    assert pick_resp2.ok
    pick_id_2 = pick_resp2.data["pick_ids"][0]
    expected_count += 1
    await _wait_for_entry_count(sock, recording_id, expected_count)

    # 4. region_ref — send region_created_requested via window.__fp
    region_id = str(uuid.uuid4())
    region_expr = _CREATE_REGION_EXPR.format(region_id=region_id, schema=_SCHEMA)
    await query(sock, EvalJsRequest(expression=region_expr, mutating=True))
    expected_count += 1
    await _wait_for_entry_count(sock, recording_id, expected_count)

    # 5. relation_ref — send relation_created_requested via window.__fp
    relation_id = str(uuid.uuid4())
    relation_expr = _CREATE_RELATION_EXPR.format(
        relation_id=relation_id,
        source_pick_id=pick_id_1,
        target_pick_id=pick_id_2,
        schema=_SCHEMA,
    )
    await query(sock, EvalJsRequest(expression=relation_expr, mutating=True))
    expected_count += 1
    await _wait_for_entry_count(sock, recording_id, expected_count)

    # 6. navigation — NavigateRequest to playground-2; Python observes URL change → NavigationEntry
    nav_resp = await query(sock, NavigateRequest(url=playground2_url))
    assert nav_resp.ok, f"NavigateRequest failed: {nav_resp}"
    expected_count += 1
    await _wait_for_entry_count(sock, recording_id, expected_count)

    await _stop_recording(sock, recording_id)

    # Restore navigation to playground-1 for subsequent tests
    await query(sock, NavigateRequest(url=playground1_url))

    # Fetch full recording and verify one of each kind
    rec_resp = await query(sock, GetRecordingRequest(recording_id=recording_id))
    assert rec_resp.ok
    entries = rec_resp.data["entries"]

    kinds_seen = {e["kind"] for e in entries}
    for required_kind in ("page_event", "pick_ref", "region_ref", "relation_ref", "navigation"):
        assert required_kind in kinds_seen, (
            f"Expected '{required_kind}' in timeline, but got: {kinds_seen}. "
            f"Entries: {[e['kind'] for e in entries]}"
        )

    # Assert navigation entry carries correct from_url / to_url
    nav_entries = [e for e in entries if e["kind"] == "navigation"]
    assert len(nav_entries) >= 1, "Expected at least one navigation entry"
    nav_entry = nav_entries[0]
    assert playground1_url in nav_entry["from_url"], (
        f"from_url {nav_entry['from_url']!r} doesn't contain {playground1_url!r}"
    )
    assert playground2_url in nav_entry["to_url"] or nav_entry["to_url"] == playground2_url, (
        f"to_url {nav_entry['to_url']!r} doesn't match {playground2_url!r}"
    )


# ---------------------------------------------------------------------------
# Scenario D — data-driven parametrized
# ---------------------------------------------------------------------------

@pytest.mark.anyio
@_SKIP
@pytest.mark.parametrize(
    "event_script,event_type,target_fragment",
    [
        (_CLICK_BTN_PRIMARY, "click", "btn-primary"),
        (_CLICK_BTN_SECONDARY, "click", "btn-secondary"),
        (_TYPE_A_INTO_INPUT_TEXT, "keydown", "input-text"),
    ],
    ids=["click-primary", "click-secondary", "type-a"],
)
async def test_data_driven_scenarios(
    anyio_backend: str,
    event_script: str,
    event_type: str,
    target_fragment: str,
) -> None:
    """Table-driven: each scenario triggers one event and asserts it's captured in the recording."""
    sock = await _get_socket()

    recording_id = await _start_recording(sock, name=f"data-driven-{event_type}")

    await query(sock, EvalJsRequest(expression=event_script, mutating=True))
    entries = await _wait_for_entry_count(sock, recording_id, 1)

    await _stop_recording(sock, recording_id)

    # Assert at least one page_event entry with the expected event_type
    page_events = [e for e in entries if e.get("kind") == "page_event"]
    assert any(e["event_type"] == event_type for e in page_events), (
        f"Expected event_type={event_type!r} in entries, got: "
        f"{[e.get('event_type') for e in page_events]}"
    )
    # Assert target contains the expected fragment
    matching = [e for e in page_events if e["event_type"] == event_type]
    assert any(target_fragment in e["target"] for e in matching), (
        f"Expected target containing {target_fragment!r}, got: {[e['target'] for e in matching]}"
    )
