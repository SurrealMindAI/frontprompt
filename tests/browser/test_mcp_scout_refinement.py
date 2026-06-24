"""End-to-end real-chromium tests for all 14 MCP Scout-Refinement tools (v0.4.0).

Uses LazyBrowserSessionProvider (production path) — spawns a real
`frontprompt show` subprocess, connects via unix socket, exercises all
14 new v0.4.0 tools via IPC query.

Grouped by concern: A-Outline, B-Finders, C-Context/Path, D-Relocate,
E-Inspect, F-Screenshot (return_mode), G-Low-level, H-Deprecation.

Marked anyio + skipif (no chromium binary).
"""

from __future__ import annotations

import shutil
import tempfile
import urllib.parse
from collections.abc import Iterator
from pathlib import Path

import pytest

from frontprompt.ipc import query
from frontprompt.ipc.protocol import (
    DomPatchRequest,
    EvalJsRequest,
    FindByRegexRequest,
    FindFirstRequest,
    FindOneRequest,
    FindSimilarRequest,
    GetElementContextRequest,
    GetPageOutlineRequest,
    InspectElementsRequest,
    PickBySelectorRequest,
    PickByTextRequest,
    PickByXpathRequest,
    PickFromRefRequest,
    PickPathRequest,
    RelocatePicksRequest,
    ScreenshotElementRequest,
    ScreenshotPageRequest,
)
from frontprompt.mcp_server import LazyBrowserSessionProvider, _build_tool_list

_TEST_HTML = """<!DOCTYPE html>
<html>
<head><title>Scout Refinement Test</title></head>
<body>
<h1>Example Domain</h1>
<p>This domain is for use in illustrative examples in documents.</p>
<p>You may use this domain in literature without prior coordination or asking for permission.</p>
<a href="https://www.iana.org/domains/example">More information...</a>
<form id="test-form">
  <input type="text" name="search" placeholder="Search" aria-label="Search input">
  <button type="submit" class="submit-btn">Search</button>
</form>
<div class="container">
  <div class="item" data-value="alpha">Alpha</div>
  <div class="item" data-value="beta">Beta item content</div>
  <div class="item" data-value="gamma">Gamma</div>
</div>
<input type="checkbox" id="agree" checked aria-label="I agree">
</body>
</html>"""

_DATA_URI = "data:text/html;charset=utf-8," + urllib.parse.quote(_TEST_HTML)

_TEST_HTML_REMOVE = """<!DOCTYPE html>
<html>
<head><title>Remove Test</title></head>
<body>
<div class="item">A</div>
<div class="item">B</div>
<div class="item">C</div>
</body>
</html>"""
_DATA_URI_REMOVE = "data:text/html;charset=utf-8," + urllib.parse.quote(_TEST_HTML_REMOVE)


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

# Module-level provider — shared across all tests, spawns browser once.
_provider: LazyBrowserSessionProvider | None = None
_tmp_dir: Path | None = None


@pytest.fixture(scope="module", autouse=True)
def _setup_provider() -> Iterator[None]:
    global _provider, _tmp_dir
    _tmp_dir = Path(tempfile.mkdtemp(prefix="fp-e2e-rfmt-", dir="/tmp"))
    _provider = LazyBrowserSessionProvider(_DATA_URI)
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
    """Resolve socket path from provider (spawns browser on first call)."""
    assert _provider is not None
    meta = await _provider.get()
    return Path(meta.socket_path)


# ── Group A — Outline tools ──────────────────────────────────────────────────


@pytest.mark.anyio
@_SKIP
async def test_get_page_outline_returns_expected_entries(anyio_backend: str) -> None:
    sock = await _get_socket()
    resp = await query(sock, GetPageOutlineRequest())
    assert resp.ok
    headings = resp.data.get("headings", [])
    links = resp.data.get("links", [])
    heading_texts = [h.get("text", "") for h in headings]
    assert any("Example Domain" in t for t in heading_texts), (
        f"Expected 'Example Domain' in headings, got: {heading_texts}"
    )
    link_texts = [lk.get("text", "") for lk in links]
    assert any("More information" in t for t in link_texts), f"Expected 'More information' in links, got: {link_texts}"


@pytest.mark.anyio
@_SKIP
async def test_pick_from_ref_materializes_outline_link(anyio_backend: str) -> None:
    sock = await _get_socket()
    outline_resp = await query(sock, GetPageOutlineRequest())
    assert outline_resp.ok
    links = outline_resp.data.get("links", [])
    assert links, "No links in outline response"
    first_link = links[0]
    ref = first_link.get("ref", {})
    ref_id = ref.get("ref_id") or first_link.get("ref_id")
    snapshot_id = ref.get("snapshot_id") or outline_resp.data.get("snapshot_id")
    assert ref_id, f"No ref_id in link: {first_link}"
    assert snapshot_id, f"No snapshot_id in outline: {outline_resp.data}"

    ref_resp = await query(
        sock,
        PickFromRefRequest(ref_id=ref_id, snapshot_id=snapshot_id, comment="materialized link"),
    )
    assert ref_resp.ok
    assert ref_resp.data.get("pick_id"), f"Expected pick_id, got: {ref_resp.data}"


@pytest.mark.anyio
@_SKIP
async def test_pick_from_ref_expired_ref_returns_error(anyio_backend: str) -> None:
    sock = await _get_socket()
    resp = await query(
        sock,
        PickFromRefRequest(
            ref_id="out:link:nonexistent-xyz-abc123",
            snapshot_id="snap-ghost-0",
            comment="test expired",
        ),
    )
    assert resp.ok is True  # soft error
    assert resp.data.get("error") in ("ref_expired", "ref_not_found"), (
        f"Expected ref_expired or ref_not_found, got: {resp.data}"
    )


# ── Group B — Finders ────────────────────────────────────────────────────────


@pytest.mark.anyio
@_SKIP
async def test_find_one_happy(anyio_backend: str) -> None:
    sock = await _get_socket()
    resp = await query(
        sock,
        FindOneRequest(
            query={"kind": "text", "text": "More information", "exact": False},
            comment="find link",
        ),
    )
    assert resp.ok
    assert resp.data.get("pick_id"), f"Expected pick_id, got: {resp.data}"


@pytest.mark.anyio
@_SKIP
async def test_find_one_ambiguous(anyio_backend: str) -> None:
    sock = await _get_socket()
    resp = await query(
        sock,
        FindOneRequest(query={"kind": "css", "selector": "div.item"}, comment="items"),
    )
    assert resp.ok is True
    assert resp.data.get("error") == "ambiguous", f"Expected ambiguous, got: {resp.data}"
    assert resp.data.get("total_matches") == 3, f"Expected 3 matches, got: {resp.data}"


@pytest.mark.anyio
@_SKIP
async def test_find_one_not_found(anyio_backend: str) -> None:
    sock = await _get_socket()
    resp = await query(
        sock,
        FindOneRequest(
            query={"kind": "text", "text": "nonexistent-xyz-unique-string"},
            comment="absent",
        ),
    )
    assert resp.ok is True
    assert resp.data.get("error") == "not_found", f"Expected not_found, got: {resp.data}"


@pytest.mark.anyio
@_SKIP
async def test_find_first_with_total_matches(anyio_backend: str) -> None:
    sock = await _get_socket()
    resp = await query(
        sock,
        FindFirstRequest(query={"kind": "css", "selector": "div.item"}, comment="first item"),
    )
    assert resp.ok
    assert resp.data.get("pick_id"), f"Expected pick_id, got: {resp.data}"
    assert resp.data.get("total_matches") == 3, f"Expected 3 total_matches, got: {resp.data}"


@pytest.mark.anyio
@_SKIP
async def test_find_by_text_smoke_test_fix_verification(anyio_backend: str) -> None:
    """Critical: verifies the v0.4.0 pick_by_text smoke-test fix via both routes."""
    sock = await _get_socket()
    # New v0.4.0 route via FindByRegexRequest
    regex_resp = await query(
        sock,
        FindByRegexRequest(pattern="More information", field="text", comment="link-text", limit=5),
    )
    assert regex_resp.ok
    assert regex_resp.data.get("total_matches", 0) >= 1, (
        f"FindByRegex should find 'More information': {regex_resp.data}"
    )
    # Legacy PickByTextRequest route (rewired via PageAnalyzer.find_by_text in v0.4.0)
    text_resp = await query(
        sock,
        PickByTextRequest(text="More information", comment="legacy-find"),
    )
    assert text_resp.ok
    assert text_resp.data.get("captured", 0) >= 1, (
        f"PickByText should find 'More information' after v0.4.0 rewire: {text_resp.data}"
    )


@pytest.mark.anyio
@_SKIP
async def test_find_similar_after_picking_container(anyio_backend: str) -> None:
    sock = await _get_socket()
    # Pick first item
    pick_resp = await query(
        sock,
        PickBySelectorRequest(selector="div.item", comment="anchor item", limit=1),
    )
    assert pick_resp.ok and pick_resp.data["captured"] == 1
    anchor_pick_id = pick_resp.data["pick_ids"][0]

    resp = await query(
        sock,
        FindSimilarRequest(
            anchor_pick_id=anchor_pick_id,
            comment="similar items",
            threshold=0.5,
            max_results=10,
        ),
    )
    assert resp.ok
    assert isinstance(resp.data.get("pick_ids"), list), f"Expected pick_ids list: {resp.data}"
    assert len(resp.data["pick_ids"]) >= 1, f"Expected at least 1 similar: {resp.data}"


@pytest.mark.anyio
@_SKIP
async def test_find_by_regex_pattern(anyio_backend: str) -> None:
    sock = await _get_socket()
    resp = await query(
        sock,
        FindByRegexRequest(
            pattern=r"[Aa]lpha|[Bb]eta",
            field="text",
            comment="greek letters",
            limit=5,
        ),
    )
    assert resp.ok
    assert resp.data.get("total_matches", 0) >= 2, f"Expected >= 2 matches for Alpha|Beta: {resp.data}"


# ── Group C — Context and path ───────────────────────────────────────────────


@pytest.mark.anyio
@_SKIP
async def test_get_element_context(anyio_backend: str) -> None:
    sock = await _get_socket()
    pick_resp = await query(
        sock,
        PickBySelectorRequest(selector="a", comment="link for context", limit=1),
    )
    assert pick_resp.ok and pick_resp.data["captured"] == 1
    pick_id = pick_resp.data["pick_ids"][0]

    resp = await query(
        sock,
        GetElementContextRequest(pick_id=pick_id, levels_up=2, sibling_radius=2),
    )
    assert resp.ok
    assert "ancestors" in resp.data, f"Expected ancestors key: {resp.data}"


@pytest.mark.anyio
@_SKIP
async def test_pick_path(anyio_backend: str) -> None:
    sock = await _get_socket()
    pick_resp = await query(
        sock,
        PickBySelectorRequest(selector="a", comment="link for path", limit=1),
    )
    assert pick_resp.ok and pick_resp.data["captured"] == 1
    pick_id = pick_resp.data["pick_ids"][0]

    resp = await query(sock, PickPathRequest(pick_id=pick_id))
    assert resp.ok
    path = resp.data.get("path", [])
    assert isinstance(path, list), f"Expected path list: {resp.data}"
    assert len(path) > 0, f"Expected non-empty path: {resp.data}"
    tags = [entry.get("tag", "") for entry in path]
    assert any(t in ("body", "html") for t in tags), f"Expected body or html in path tags: {tags}"


# ── Group D — Relocate ───────────────────────────────────────────────────────


@pytest.mark.anyio
@_SKIP
async def test_relocate_picks_all(anyio_backend: str) -> None:
    sock = await _get_socket()
    # Create at least 2 picks
    pick_resp = await query(
        sock,
        PickBySelectorRequest(selector="div.item", comment="items for relocate", limit=2),
    )
    assert pick_resp.ok
    assert pick_resp.data["captured"] >= 2

    resp = await query(sock, RelocatePicksRequest())  # no pick_ids = relocate all
    assert resp.ok
    assert isinstance(resp.data, list), f"Expected list result: {resp.data}"
    assert len(resp.data) >= 2
    for entry in resp.data:
        assert "pick_id" in entry, f"Entry missing pick_id: {entry}"
        assert "status" in entry, f"Entry missing status: {entry}"


# ── Group E — Inspect ────────────────────────────────────────────────────────


@pytest.mark.anyio
@_SKIP
async def test_inspect_elements_default_fields(anyio_backend: str) -> None:
    sock = await _get_socket()
    pick_resp = await query(
        sock,
        PickBySelectorRequest(selector="h1", comment="h1 for inspect", limit=1),
    )
    assert pick_resp.ok and pick_resp.data["captured"] == 1
    pick_id = pick_resp.data["pick_ids"][0]

    resp = await query(sock, InspectElementsRequest(pick_ids=[pick_id]))
    assert resp.ok
    assert isinstance(resp.data, list)
    result = resp.data[0]
    assert "text" in result, f"Expected text: {result}"
    assert "role" in result, f"Expected role: {result}"
    assert "visible" in result, f"Expected visible: {result}"
    assert "enabled" in result, f"Expected enabled: {result}"
    assert result.get("visible") is True


@pytest.mark.anyio
@_SKIP
async def test_inspect_elements_only_static_fields(anyio_backend: str) -> None:
    sock = await _get_socket()
    pick_resp = await query(
        sock,
        PickBySelectorRequest(selector="h1", comment="h1 for inspect static", limit=1),
    )
    assert pick_resp.ok and pick_resp.data["captured"] == 1
    pick_id = pick_resp.data["pick_ids"][0]

    resp = await query(
        sock,
        InspectElementsRequest(pick_ids=[pick_id], fields=["text", "accessible_name"]),
    )
    assert resp.ok
    result = resp.data[0]
    assert "text" in result, f"Expected text: {result}"
    assert "visible" not in result, f"Unexpected visible with only static fields: {result}"


@pytest.mark.anyio
@_SKIP
async def test_inspect_elements_all_fields(anyio_backend: str) -> None:
    sock = await _get_socket()
    pick_resp = await query(
        sock,
        PickBySelectorRequest(selector="h1", comment="h1 all fields", limit=1),
    )
    assert pick_resp.ok and pick_resp.data["captured"] == 1
    pick_id = pick_resp.data["pick_ids"][0]

    fields = [
        "text",
        "role",
        "visible",
        "enabled",
        "checked",
        "focused",
        "in_viewport",
        "accessible_name",
        "attributes",
    ]
    resp = await query(
        sock,
        InspectElementsRequest(pick_ids=[pick_id], fields=fields),
    )
    assert resp.ok
    result = resp.data[0]
    for field in fields:
        assert field in result, f"Expected field {field!r}: {result}"


# ── Group F — Screenshot path-mode ──────────────────────────────────────────


@pytest.mark.anyio
@_SKIP
async def test_screenshot_element_default_is_path_mode(anyio_backend: str) -> None:
    sock = await _get_socket()
    pick_resp = await query(
        sock,
        PickBySelectorRequest(selector="h1", comment="h1 for screenshot", limit=1),
    )
    assert pick_resp.ok and pick_resp.data["captured"] == 1
    pick_id = pick_resp.data["pick_ids"][0]

    resp = await query(sock, ScreenshotElementRequest(pick_ids=[pick_id]))
    assert resp.ok
    r = resp.data[0]
    assert "path" in r, f"Expected path key (default path mode): {r}"
    assert r["path"].endswith(".png"), f"Expected .png path: {r['path']}"
    assert Path(r["path"]).exists(), f"Screenshot file does not exist: {r['path']}"
    assert "directive" in r, f"Expected directive key: {r}"
    assert "Read tool" in r["directive"], f"Expected 'Read tool' in directive: {r['directive']}"


@pytest.mark.anyio
@_SKIP
async def test_screenshot_page_default_is_path_mode(anyio_backend: str) -> None:
    sock = await _get_socket()
    resp = await query(sock, ScreenshotPageRequest())
    assert resp.ok
    r = resp.data
    assert "path" in r, f"Expected path key (default path mode): {r}"
    assert Path(r["path"]).exists(), f"Screenshot file does not exist: {r['path']}"


# ── Group G — Low-level tools ────────────────────────────────────────────────


@pytest.mark.anyio
@_SKIP
async def test_eval_js_scalar_return(anyio_backend: str) -> None:
    sock = await _get_socket()
    resp = await query(sock, EvalJsRequest(expression="1 + 1", mutating=False))
    assert resp.ok
    assert resp.data.get("ok") is True
    assert resp.data.get("result") == 2, f"Expected result=2: {resp.data}"


@pytest.mark.anyio
@_SKIP
async def test_eval_js_pick_id_arg_binding(anyio_backend: str) -> None:
    sock = await _get_socket()
    pick_resp = await query(
        sock,
        PickBySelectorRequest(selector="h1", comment="h1 for eval_js", limit=1),
    )
    assert pick_resp.ok and pick_resp.data["captured"] == 1
    pick_id = pick_resp.data["pick_ids"][0]

    resp = await query(
        sock,
        EvalJsRequest(expression="el.tagName", pick_id_arg=pick_id, mutating=False),
    )
    assert resp.ok
    assert resp.data.get("result") == "H1", f"Expected H1: {resp.data}"


@pytest.mark.anyio
@_SKIP
async def test_eval_js_js_error(anyio_backend: str) -> None:
    sock = await _get_socket()
    resp = await query(
        sock,
        EvalJsRequest(expression="throw new Error('test-error')", mutating=False),
    )
    assert resp.ok  # IPC level is ok
    assert resp.data.get("ok") is False, f"Expected ok=False: {resp.data}"
    assert resp.data.get("error"), f"Expected error field: {resp.data}"


@pytest.mark.anyio
@_SKIP
async def test_eval_js_mutating_invalidates_snapshot(anyio_backend: str) -> None:
    """After mutating eval_js, the snapshot_id changes on next outline call."""
    sock = await _get_socket()
    outline1 = await query(sock, GetPageOutlineRequest())
    assert outline1.ok
    snap_id_1 = outline1.data.get("snapshot_id")

    await query(
        sock,
        EvalJsRequest(
            expression="document.body.setAttribute('data-test-mut', '1')",
            mutating=True,
        ),
    )

    outline2 = await query(sock, GetPageOutlineRequest())
    assert outline2.ok
    snap_id_2 = outline2.data.get("snapshot_id")

    assert snap_id_1 != snap_id_2, f"Snapshot IDs should differ after mutating eval_js: {snap_id_1} vs {snap_id_2}"


@pytest.mark.anyio
@_SKIP
async def test_dom_patch_set_attribute(anyio_backend: str) -> None:
    sock = await _get_socket()
    # Use a unique-ID element so the CSS selector `input#agree` resolves precisely.
    pick_resp = await query(
        sock,
        PickBySelectorRequest(selector="#agree", comment="checkbox for dom_patch", limit=1),
    )
    assert pick_resp.ok and pick_resp.data["captured"] == 1
    pick_id = pick_resp.data["pick_ids"][0]

    patch_resp = await query(
        sock,
        DomPatchRequest(
            pick_id=pick_id,
            operations=[{"op": "set_attribute", "name": "data-patched", "value": "yes"}],
        ),
    )
    assert patch_resp.ok
    assert patch_resp.data.get("ok") is True
    assert patch_resp.data.get("results", [{}])[0].get("ok") is True


@pytest.mark.anyio
@_SKIP
async def test_pick_by_xpath_happy(anyio_backend: str) -> None:
    sock = await _get_socket()
    resp = await query(
        sock,
        PickByXpathRequest(
            xpath="//div[@class='item']",
            comment="xpath items",
            limit=10,
        ),
    )
    assert resp.ok
    assert len(resp.data.get("pick_ids", [])) == 3, f"Expected 3 pick_ids: {resp.data}"
    assert resp.data.get("total_matches") == 3, f"Expected total_matches=3: {resp.data}"


# ── Group H — Removed deprecated tools absent from surface ────────────────────


@pytest.mark.anyio
@_SKIP
async def test_deprecated_tools_absent_from_tool_surface(anyio_backend: str) -> None:
    """The 5 deprecated v0.3.0 element-readers are removed from the MCP tool surface (IPC 0.6.0)."""
    names = {t.name for t in _build_tool_list()}
    removed = [
        "frontprompt_get_text",
        "frontprompt_get_attributes",
        "frontprompt_get_state",
        "frontprompt_get_html",
        "frontprompt_get_outline",
    ]
    for name in removed:
        assert name not in names, f"Removed tool {name!r} still present in tool surface"
