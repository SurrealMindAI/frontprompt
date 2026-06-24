"""End-to-end real-chromium tests for all 11 MCP Scout-Tools (v0.3.0).

Uses LazyBrowserSessionProvider (production path) — spawns a real
`frontprompt show` subprocess, connects via unix socket, exercises all
11 tools via IPC query.

Each test group creates its own picks via pick_by_selector/pick_by_text
before calling reader tools — no assumptions about pre-existing picks.

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
    GetAttributesRequest,
    GetHtmlRequest,
    GetOutlineRequest,
    GetPageInfoRequest,
    GetStateRequest,
    GetTextRequest,
    PickBySelectorRequest,
    PickByTextRequest,
    ScreenshotElementRequest,
    ScreenshotPageRequest,
    ScrollToRequest,
)
from frontprompt.mcp_server import LazyBrowserSessionProvider

_TEST_HTML = """<!DOCTYPE html>
<html>
<head><title>Scout Test Page</title></head>
<body>
<h1 id="title">Hello Scout</h1>
<button class="btn" aria-label="Click me">Click</button>
<p class="content">Some paragraph text</p>
<div class="outer"><div class="inner">nested</div></div>
<input type="checkbox" checked id="cb">
<div style="margin-top:2000px;" id="far">Far element</div>
</body>
</html>"""

_DATA_URI = "data:text/html;charset=utf-8," + urllib.parse.quote(_TEST_HTML)

_TEST_HTML_2 = """<!DOCTYPE html><html><head><title>Page 2</title></head>
<body><p>Different content — no h1#title here</p></body></html>"""
_DATA_URI_2 = "data:text/html;charset=utf-8," + urllib.parse.quote(_TEST_HTML_2)


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
    _tmp_dir = Path(tempfile.mkdtemp(prefix="fp-e2e-", dir="/tmp"))
    _provider = LazyBrowserSessionProvider(_DATA_URI)
    yield
    # Teardown: close the browser child process.
    # anyio.run() is unavailable here (event-loop attached to test run differs).
    # Use asyncio directly to avoid "Future attached to a different loop" error.
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


# ---- Pick-Creators ---------------------------------------------------------


@pytest.mark.anyio
@_SKIP
async def test_pick_by_selector_happy(anyio_backend: str) -> None:
    sock = await _get_socket()
    resp = await query(sock, PickBySelectorRequest(selector="h1#title", comment="title pick", limit=10))
    assert resp.ok
    data = resp.data
    assert isinstance(data["pick_ids"], list)
    assert len(data["pick_ids"]) == 1
    assert data["total_matches"] == 1
    assert data["captured"] == 1


@pytest.mark.anyio
@_SKIP
async def test_pick_by_selector_zero_matches(anyio_backend: str) -> None:
    sock = await _get_socket()
    resp = await query(sock, PickBySelectorRequest(selector=".nonexistent-xyz-element", comment="zero", limit=10))
    assert resp.ok
    assert resp.data["pick_ids"] == []
    assert resp.data["total_matches"] == 0
    assert resp.data["captured"] == 0


@pytest.mark.anyio
@_SKIP
async def test_pick_by_selector_over_limit(anyio_backend: str) -> None:
    sock = await _get_socket()
    resp = await query(sock, PickBySelectorRequest(selector="*", comment="all", limit=2))
    assert resp.ok
    assert resp.data["captured"] == 2
    assert resp.data["total_matches"] > 2


@pytest.mark.anyio
@_SKIP
async def test_pick_by_selector_parent_scope(anyio_backend: str) -> None:
    sock = await _get_socket()
    # First pick the outer div
    outer_resp = await query(sock, PickBySelectorRequest(selector="div.outer", comment="outer", limit=1))
    assert outer_resp.ok and outer_resp.data["captured"] == 1
    outer_pick_id = outer_resp.data["pick_ids"][0]

    # Now pick .inner scoped to outer
    inner_resp = await query(
        sock,
        PickBySelectorRequest(
            selector="div.inner",
            comment="inner scoped",
            parent_pick_id=outer_pick_id,
            limit=10,
        ),
    )
    assert inner_resp.ok
    assert inner_resp.data["captured"] == 1
    assert inner_resp.data["total_matches"] == 1


@pytest.mark.anyio
@_SKIP
async def test_pick_by_text_no_role(anyio_backend: str) -> None:
    sock = await _get_socket()
    resp = await query(sock, PickByTextRequest(text="Hello Scout", comment="by text"))
    assert resp.ok
    assert resp.data["captured"] >= 1


@pytest.mark.anyio
@_SKIP
async def test_pick_by_text_with_role(anyio_backend: str) -> None:
    sock = await _get_socket()
    # Button's accessible name is "Click me" (from aria-label), text content is "Click"
    # get_by_role uses accessible name — use "Click me" to match exactly
    resp = await query(sock, PickByTextRequest(text="Click me", role="button", comment="button by text"))
    assert resp.ok
    assert resp.data["captured"] == 1


@pytest.mark.anyio
@_SKIP
async def test_pick_by_text_role_mismatch_zero(anyio_backend: str) -> None:
    sock = await _get_socket()
    # "Click me" is a button, not a heading — role mismatch yields 0 results
    resp = await query(sock, PickByTextRequest(text="Click me", role="heading", comment="mismatch"))
    assert resp.ok
    assert resp.data["total_matches"] == 0
    assert resp.data["captured"] == 0


# ---- Element-Readers -------------------------------------------------------


@pytest.mark.anyio
@_SKIP
async def test_get_text_single_pick(anyio_backend: str) -> None:
    sock = await _get_socket()
    pick_resp = await query(sock, PickBySelectorRequest(selector="h1#title", comment="for get_text", limit=1))
    assert pick_resp.ok and pick_resp.data["captured"] == 1
    pick_id = pick_resp.data["pick_ids"][0]

    resp = await query(sock, GetTextRequest(pick_ids=[pick_id]))
    assert resp.ok
    results = resp.data
    assert len(results) == 1
    r = results[0]
    assert "Hello Scout" in r["text"]
    assert r["is_visible"] is True


@pytest.mark.anyio
@_SKIP
async def test_get_html_truncated(anyio_backend: str) -> None:
    sock = await _get_socket()
    # Use body — its HTML is ~300+ chars (contains all page elements)
    # min max_chars is 100 per GetHtmlRequest constraint
    pick_resp = await query(sock, PickBySelectorRequest(selector="body", comment="for get_html", limit=1))
    assert pick_resp.ok and pick_resp.data["captured"] == 1
    pick_id = pick_resp.data["pick_ids"][0]

    resp = await query(sock, GetHtmlRequest(pick_ids=[pick_id], max_chars=100))
    assert resp.ok
    r = resp.data[0]
    assert len(r["html"]) <= 100
    assert r["truncated"] is True


@pytest.mark.anyio
@_SKIP
async def test_get_attributes_button(anyio_backend: str) -> None:
    sock = await _get_socket()
    pick_resp = await query(sock, PickBySelectorRequest(selector="button.btn", comment="for get_attributes", limit=1))
    assert pick_resp.ok and pick_resp.data["captured"] == 1
    pick_id = pick_resp.data["pick_ids"][0]

    resp = await query(sock, GetAttributesRequest(pick_ids=[pick_id]))
    assert resp.ok
    attrs = resp.data[0]["attributes"]
    assert "class" in attrs
    assert "aria-label" in attrs


@pytest.mark.anyio
@_SKIP
async def test_get_state_checked_input(anyio_backend: str) -> None:
    sock = await _get_socket()
    pick_resp = await query(sock, PickBySelectorRequest(selector="input#cb", comment="for get_state", limit=1))
    assert pick_resp.ok and pick_resp.data["captured"] == 1
    pick_id = pick_resp.data["pick_ids"][0]

    resp = await query(sock, GetStateRequest(pick_ids=[pick_id]))
    assert resp.ok
    state = resp.data[0]
    assert state["checked"] is True
    assert state["visible"] is True


@pytest.mark.anyio
@_SKIP
async def test_get_outline_nested(anyio_backend: str) -> None:
    sock = await _get_socket()
    pick_resp = await query(sock, PickBySelectorRequest(selector="div.outer", comment="for get_outline", limit=1))
    assert pick_resp.ok and pick_resp.data["captured"] == 1
    pick_id = pick_resp.data["pick_ids"][0]

    resp = await query(sock, GetOutlineRequest(pick_ids=[pick_id], max_depth=3, max_nodes=100))
    assert resp.ok
    # Outline has nested structure: outer div → inner div (text: "nested")
    import json

    outline_str = json.dumps(resp.data[0])
    # The inner div contains text "nested" — verifies depth traversal worked
    assert "nested" in outline_str


@pytest.mark.anyio
@_SKIP
async def test_screenshot_element_happy(anyio_backend: str) -> None:
    sock = await _get_socket()
    pick_resp = await query(sock, PickBySelectorRequest(selector="h1#title", comment="for screenshot_element", limit=1))
    assert pick_resp.ok and pick_resp.data["captured"] == 1
    pick_id = pick_resp.data["pick_ids"][0]

    resp = await query(sock, ScreenshotElementRequest(pick_ids=[pick_id], padding=8))
    assert resp.ok
    r = resp.data[0]
    # default return_mode="path" — result has path + directive, not image_base64
    assert "path" in r
    assert "directive" in r
    assert isinstance(r["width"], int) and r["width"] > 0
    assert isinstance(r["height"], int) and r["height"] > 0


@pytest.mark.anyio
@_SKIP
async def test_get_text_stale_pick_after_navigate(anyio_backend: str) -> None:
    """After navigating to a page without h1#title, get_text returns stale_pick marker."""
    sock = await _get_socket()
    # Pick the h1 on page 1
    pick_resp = await query(sock, PickBySelectorRequest(selector="h1#title", comment="stale test", limit=1))
    assert pick_resp.ok and pick_resp.data["captured"] == 1
    pick_id = pick_resp.data["pick_ids"][0]

    # Navigate away (page 2 has no h1#title)
    from frontprompt.ipc.protocol import NavigateRequest

    nav_resp = await query(sock, NavigateRequest(url=_DATA_URI_2))
    assert nav_resp.ok

    # Now get_text on the stale pick
    resp = await query(sock, GetTextRequest(pick_ids=[pick_id]))
    assert resp.ok
    r = resp.data[0]
    assert r.get("error") == "stale_pick"
    assert r.get("pick_id") == pick_id

    # Navigate back to restore state for subsequent tests
    await query(sock, NavigateRequest(url=_DATA_URI))


# ---- Page-Level ------------------------------------------------------------


@pytest.mark.anyio
@_SKIP
async def test_screenshot_page_viewport(anyio_backend: str) -> None:
    sock = await _get_socket()
    resp = await query(sock, ScreenshotPageRequest(full_page=False))
    assert resp.ok
    r = resp.data
    # default return_mode="path" — result has path + directive, not image_base64
    assert "path" in r
    assert "directive" in r
    assert isinstance(r["width"], int) and r["width"] > 0
    assert isinstance(r["height"], int) and r["height"] > 0


@pytest.mark.anyio
@_SKIP
async def test_screenshot_page_full(anyio_backend: str) -> None:
    sock = await _get_socket()
    vp_resp = await query(sock, ScreenshotPageRequest(full_page=False))
    full_resp = await query(sock, ScreenshotPageRequest(full_page=True))
    assert full_resp.ok
    # full page should be taller than viewport screenshot
    assert full_resp.data["height"] > vp_resp.data["height"]


@pytest.mark.anyio
@_SKIP
async def test_scroll_to_far_element(anyio_backend: str) -> None:
    sock = await _get_socket()
    pick_resp = await query(sock, PickBySelectorRequest(selector="div#far", comment="far for scroll", limit=1))
    assert pick_resp.ok and pick_resp.data["captured"] == 1
    pick_id = pick_resp.data["pick_ids"][0]

    resp = await query(sock, ScrollToRequest(pick_id=pick_id))
    assert resp.ok
    assert resp.data["is_in_viewport"] is True
    # ScrollToResult returns flat scroll_x/scroll_y, not nested scroll_position
    assert resp.data["scroll_y"] > 0


@pytest.mark.anyio
@_SKIP
async def test_get_page_info_after_navigate(anyio_backend: str) -> None:
    sock = await _get_socket()
    resp = await query(sock, GetPageInfoRequest())
    assert resp.ok
    data = resp.data
    assert "url" in data
    assert data["title"] == "Scout Test Page"
    # PageInfoResult has flat viewport_w/viewport_h, not nested viewport
    assert data["viewport_w"] > 0
    assert data["viewport_h"] > 0
