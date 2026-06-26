# Playground Assets

Served HTML assets for `tests/browser/` real-Chromium e2e tests. All files are
pure HTML/CSS/JS — **no Python** — so the playground server can safely root here.

## Why a Served Origin (not data: URIs)?

A `http://127.0.0.1` origin is a real web origin. The frontprompt overlay's
cross-origin survival is exercised properly. Navigation between two pages on the
same port is same-origin; pages on different ports are distinct origins — the
e2e recorder suite uses both to verify cross-origin survival.

## Files

| File | Purpose | Stable hooks | Consumed by |
|------|---------|--------------|-------------|
| `scout-elements.html` | Primary MCP scout-tool surface | `h1#title`, `button.btn[aria-label="Click me"]`, `p.content`, `div.outer > div.inner`, `input#cb`, `div#far` | `test_mcp_tool_surface.py` |
| `simple-paragraph.html` | Stale-pick / navigation target | `p` (first), no `h1#title` | `test_mcp_tool_surface.py` |
| `scout-refinement.html` | MCP scout-refinement tools | `h1`, `a`, `form#test-form`, `div.item` ×3, `input#agree` | `test_mcp_scout_refinement.py` |
| `remove-test.html` | DOM removal tests | `div.item` ×3 (A/B/C) | `test_mcp_scout_refinement.py` (future) |
| `overlay-test.html` | Screenshot / overlay hide-restore | `h1#hdr`, `button#btn` | `test_screenshot_overlay_hidden.py` |
| `recorder-playground.html` | Recorder e2e: click, type, drag | `button#btn-primary`, `button#btn-secondary`, `input#input-text`, `input#input-number`, `div#drag-source`, `div#drop-zone` | `test_recorder_playground_e2e.py` |
| `recorder-playground-2.html` | Recorder e2e: navigation target | `h1#page2-title`, `p#page2-info`, `button#page2-btn` | `test_recorder_playground_e2e.py` |

## Server Fixture

The `playground_server` session-scoped pytest fixture (in `tests/browser/conftest.py`)
starts a stdlib `http.server.HTTPServer` bound to `127.0.0.1:0` (random port),
rooted exclusively at this directory. `playground_url(name)` returns
`http://127.0.0.1:<port>/<name>.html`.

```python
# In a test:
def test_example(playground_url: Callable[[str], str]) -> None:
    url = playground_url("scout-elements")  # http://127.0.0.1:<port>/scout-elements.html
```

## Stability Contract

IDs and classes listed in the "Stable hooks" column are **immutable** — tests
depend on them. Adding new elements is always OK. Renaming/removing an ID or
class requires updating all consumers (check `tests/browser/` for usages).
