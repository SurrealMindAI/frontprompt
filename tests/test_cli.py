"""CLI integration tests — synchronous (no async required).

Tests use Click's CliRunner for isolation: no real stdin/stdout, no side-effects.
"""

from __future__ import annotations

from unittest.mock import AsyncMock, MagicMock, patch

from click.testing import CliRunner

from frontprompt.cli import main


def test_cli_help_exits_zero() -> None:
    """``frontprompt --help`` produziert Hilfe-Text und exit 0."""
    runner = CliRunner()
    result = runner.invoke(main, ["--help"])
    assert result.exit_code == 0
    assert "mcp" in result.output


def test_mcp_help_exits_zero() -> None:
    """``frontprompt mcp --help`` zeigt den mcp-Subcommand-Hilfetext."""
    runner = CliRunner()
    result = runner.invoke(main, ["mcp", "--help"])
    assert result.exit_code == 0
    assert "mcp" in result.output.lower()


def test_daemon_alias_still_works() -> None:
    """``daemon`` bleibt als hidden Backward-Compat-Alias für ``mcp`` aufrufbar."""
    runner = CliRunner()
    result = runner.invoke(main, ["daemon", "--help"])
    assert result.exit_code == 0


def test_unknown_subcommand_exits_nonzero() -> None:
    """Unbekannter Subcommand → exit 2 (Click-Standard für usage error)."""
    runner = CliRunner()
    result = runner.invoke(main, ["bogus-subcommand"])
    assert result.exit_code == 2


def test_show_command_delegates_to_show_session() -> None:
    """show_command delegates to ShowSession — regression guard for the cli.py extraction."""
    show_session_call_args: list[str] = []

    # Mock ShowSession to return immediately without spawning a browser
    mock_session = MagicMock()
    mock_session.__aenter__ = AsyncMock(return_value=mock_session)
    mock_session.__aexit__ = AsyncMock(return_value=None)
    mock_session.run = AsyncMock(return_value=None)

    def mock_show_session_factory(url: str, **kwargs: object) -> MagicMock:
        show_session_call_args.append(url)
        return mock_session

    runner = CliRunner()
    with patch("frontprompt.show_session.ShowSession", side_effect=mock_show_session_factory):
        result = runner.invoke(main, ["show", "https://example.com"])

    assert result.exit_code == 0, f"Expected exit 0, got {result.exit_code}: {result.output}"
    assert show_session_call_args == ["https://example.com"], (
        f"ShowSession not called with correct URL — got {show_session_call_args}"
    )


def test_show_command_help_exits_zero() -> None:
    """``frontprompt show --help`` exits 0 and output contains 'url' argument."""
    runner = CliRunner()
    result = runner.invoke(main, ["show", "--help"])
    assert result.exit_code == 0
    assert "url" in result.output.lower()


def test_bootstrap_verifies_overlay_and_skips_chromium() -> None:
    """``frontprompt bootstrap --no-chromium`` verifies the embedded overlay, exit 0.

    With ``--no-chromium`` no playwright subprocess runs, so this is hermetic.
    """
    fake_manifest = MagicMock(schema_version="0.7.0", bundle_size_bytes=123)
    runner = CliRunner()
    with patch("frontprompt.overlay.loader.load_build_manifest", return_value=fake_manifest):
        result = runner.invoke(main, ["bootstrap", "--no-chromium"])

    assert result.exit_code == 0, f"Expected exit 0, got {result.exit_code}: {result.output}"
    assert "overlay bundle" in result.output
    assert "embedded" in result.output


def test_bootstrap_fails_when_overlay_missing() -> None:
    """Missing embedded overlay → bootstrap exits non-zero with the build hint."""
    runner = CliRunner()
    with patch(
        "frontprompt.overlay.loader.load_build_manifest",
        side_effect=FileNotFoundError("nope.\nRun `python -m frontprompt.build`"),
    ):
        result = runner.invoke(main, ["bootstrap", "--no-chromium"])

    assert result.exit_code == 1
    assert "MISSING" in result.output


def test_bootstrap_help_exits_zero() -> None:
    """``frontprompt bootstrap --help`` exits 0 and mentions chromium."""
    runner = CliRunner()
    result = runner.invoke(main, ["bootstrap", "--help"])
    assert result.exit_code == 0
    assert "chromium" in result.output.lower()


# ── Debug / write subcommands over the IPC socket ───────────────────────────
#
# These mock the two seams: `frontprompt.cli._resolve_session` (session lookup)
# and `frontprompt.ipc.query` (the socket round-trip). No real socket / browser.

from frontprompt.ipc.protocol import IpcResponse  # noqa: E402


def _fake_session() -> MagicMock:
    return MagicMock(socket_path="/tmp/fp-test.sock", session_id="dev")


def _capture(response: IpcResponse) -> tuple[dict, object]:
    """Return (captured, fake_query) — fake_query records the request and returns `response`."""
    captured: dict = {}

    async def fake_query(socket_path: object, request: object, **_kw: object) -> IpcResponse:
        captured["socket_path"] = socket_path
        captured["request"] = request
        return response

    return captured, fake_query


def test_navigate_sends_navigate_request() -> None:
    captured, fake_query = _capture(IpcResponse(ok=True, data={"navigated_to": "https://x", "title": "X"}))
    runner = CliRunner()
    with (
        patch("frontprompt.cli._resolve_session", return_value=_fake_session()),
        patch("frontprompt.ipc.query", new=fake_query),
    ):
        result = runner.invoke(main, ["navigate", "https://x"])
    assert result.exit_code == 0, result.output
    assert captured["request"].kind == "navigate"
    assert captured["request"].url == "https://x"
    assert "navigated_to" in result.output


def test_eval_sends_eval_request_with_pick_and_mutating() -> None:
    captured, fake_query = _capture(IpcResponse(ok=True, data={"result": "42", "ok": True}))
    runner = CliRunner()
    with (
        patch("frontprompt.cli._resolve_session", return_value=_fake_session()),
        patch("frontprompt.ipc.query", new=fake_query),
    ):
        result = runner.invoke(main, ["eval", "6*7", "--pick", "p1", "--mutating"])
    assert result.exit_code == 0, result.output
    req = captured["request"]
    assert req.kind == "eval_js"
    assert req.expression == "6*7"
    assert req.pick_id_arg == "p1"
    assert req.mutating is True


def test_page_info_sends_request() -> None:
    captured, fake_query = _capture(IpcResponse(ok=True, data={"url": "https://x", "title": "X"}))
    runner = CliRunner()
    with (
        patch("frontprompt.cli._resolve_session", return_value=_fake_session()),
        patch("frontprompt.ipc.query", new=fake_query),
    ):
        result = runner.invoke(main, ["page-info"])
    assert result.exit_code == 0, result.output
    assert captured["request"].kind == "get_page_info"


def test_screenshot_without_path_emits_server_path() -> None:
    _captured, fake_query = _capture(IpcResponse(ok=True, data={"path": "/tmp/server.png", "width": 1}))
    runner = CliRunner()
    with (
        patch("frontprompt.cli._resolve_session", return_value=_fake_session()),
        patch("frontprompt.ipc.query", new=fake_query),
    ):
        result = runner.invoke(main, ["screenshot"])
    assert result.exit_code == 0, result.output
    assert "/tmp/server.png" in result.output


def test_screenshot_with_path_copies_png(tmp_path: object) -> None:
    src = tmp_path / "server.png"  # type: ignore[operator]
    src.write_bytes(b"\x89PNG-data")
    dest = tmp_path / "out.png"  # type: ignore[operator]
    _captured, fake_query = _capture(IpcResponse(ok=True, data={"path": str(src), "width": 1}))
    runner = CliRunner()
    with (
        patch("frontprompt.cli._resolve_session", return_value=_fake_session()),
        patch("frontprompt.ipc.query", new=fake_query),
    ):
        result = runner.invoke(main, ["screenshot", str(dest)])
    assert result.exit_code == 0, result.output
    assert dest.read_bytes() == b"\x89PNG-data"
    assert str(dest) in result.output


def test_pick_selector_sends_request() -> None:
    captured, fake_query = _capture(IpcResponse(ok=True, data=[]))
    runner = CliRunner()
    with (
        patch("frontprompt.cli._resolve_session", return_value=_fake_session()),
        patch("frontprompt.ipc.query", new=fake_query),
    ):
        result = runner.invoke(main, ["pick", "selector", "h1", "--comment", "heading", "--limit", "3"])
    assert result.exit_code == 0, result.output
    req = captured["request"]
    assert req.kind == "pick_by_selector"
    assert req.selector == "h1"
    assert req.comment == "heading"
    assert req.limit == 3


def test_pick_text_sends_request() -> None:
    captured, fake_query = _capture(IpcResponse(ok=True, data=[]))
    runner = CliRunner()
    with (
        patch("frontprompt.cli._resolve_session", return_value=_fake_session()),
        patch("frontprompt.ipc.query", new=fake_query),
    ):
        result = runner.invoke(main, ["pick", "text", "Read", "--comment", "c", "--role", "link"])
    assert result.exit_code == 0, result.output
    req = captured["request"]
    assert req.kind == "pick_by_text"
    assert req.text == "Read"
    assert req.role == "link"


def test_socket_command_exits_3_on_error_response() -> None:
    _captured, fake_query = _capture(IpcResponse(ok=False, error="boom"))
    runner = CliRunner()
    with (
        patch("frontprompt.cli._resolve_session", return_value=_fake_session()),
        patch("frontprompt.ipc.query", new=fake_query),
    ):
        result = runner.invoke(main, ["page-info"])
    assert result.exit_code == 3
    assert "boom" in result.output


def test_socket_command_exits_3_on_connection_error() -> None:
    from frontprompt.ipc import IpcConnectError

    async def boom_query(socket_path: object, request: object, **_kw: object) -> object:
        raise IpcConnectError("no socket")

    runner = CliRunner()
    with (
        patch("frontprompt.cli._resolve_session", return_value=_fake_session()),
        patch("frontprompt.ipc.query", new=boom_query),
    ):
        result = runner.invoke(main, ["navigate", "https://x"])
    assert result.exit_code == 3
    assert "no socket" in result.output


def test_new_debug_subcommands_appear_in_help() -> None:
    runner = CliRunner()
    result = runner.invoke(main, ["--help"])
    assert result.exit_code == 0
    for cmd in ("navigate", "eval", "page-info", "screenshot", "pick"):
        assert cmd in result.output
