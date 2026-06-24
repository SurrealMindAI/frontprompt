"""CLI integration tests — synchronous (no async required).

Tests use Click's CliRunner for isolation: no real stdin/stdout, no side-effects.
"""

from __future__ import annotations

import json
from unittest.mock import AsyncMock, MagicMock, patch

from click.testing import CliRunner

from frontprompt.cli import main


def test_cli_help_exits_zero() -> None:
    """``frontprompt --help`` produziert Hilfe-Text und exit 0."""
    runner = CliRunner()
    result = runner.invoke(main, ["--help"])
    assert result.exit_code == 0
    assert "daemon" in result.output


def test_daemon_help_exits_zero() -> None:
    """``frontprompt daemon --help`` zeigt den daemon-Subcommand-Hilfetext."""
    runner = CliRunner()
    result = runner.invoke(main, ["daemon", "--help"])
    assert result.exit_code == 0
    assert "daemon" in result.output.lower()


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


# ── MCP setup step (sub-plan 03) ─────────────────────────────────────────────


def _bootstrap_with_mcp(tmp_path: object, monkeypatch: object, *, write_mcp_json: bool = False) -> object:
    """Helper: invoke ``frontprompt bootstrap --no-chromium`` with a fake sentinel.

    Monkeypatches Path.home() to *tmp_path* so the sentinel is read from
    ``<tmp_path>/.frontprompt/install.path`` and writes (if any) land in
    ``<tmp_path>/.mcp.json``.
    """
    import pathlib

    from click.testing import CliRunner as _CliRunner

    sentinel_dir = tmp_path / ".frontprompt"  # type: ignore[operator]
    sentinel_dir.mkdir()
    sentinel_file = sentinel_dir / "install.path"
    sentinel_file.write_text(str(tmp_path))

    # Place a fake run-mcp.sh in the tmp root so the path is resolvable.
    fake_run_mcp = tmp_path / "run-mcp.sh"  # type: ignore[operator]
    fake_run_mcp.write_text("#!/bin/sh\nexec uv run frontprompt daemon\n")

    monkeypatch.setattr(pathlib.Path, "home", staticmethod(lambda: tmp_path))  # type: ignore[arg-type]

    fake_manifest = MagicMock(schema_version="0.7.0", bundle_size_bytes=123)
    runner = _CliRunner()
    args = ["bootstrap", "--no-chromium"]
    if write_mcp_json:
        args.append("--write-mcp-json")

    with patch("frontprompt.overlay.loader.load_build_manifest", return_value=fake_manifest):
        return runner.invoke(main, args)


def test_bootstrap_prints_mcp_snippet(tmp_path: object, monkeypatch: object) -> None:
    """bootstrap --no-chromium prints the JSON snippet and claude mcp add command."""
    result = _bootstrap_with_mcp(tmp_path, monkeypatch)
    assert result.exit_code == 0, f"Expected exit 0, got {result.exit_code}: {result.output}"
    assert '"mcpServers"' in result.output
    assert '"frontprompt"' in result.output
    assert '"command"' in result.output
    assert "claude mcp add" in result.output


def test_bootstrap_mcp_snippet_contains_run_mcp_path(tmp_path: object, monkeypatch: object) -> None:
    """The snippet command path points to run-mcp.sh resolved from the sentinel."""
    result = _bootstrap_with_mcp(tmp_path, monkeypatch)
    assert result.exit_code == 0
    assert "run-mcp.sh" in result.output


def test_bootstrap_write_mcp_json(tmp_path: object, monkeypatch: object) -> None:
    """bootstrap --write-mcp-json creates ~/.mcp.json with the frontprompt entry."""
    import pathlib

    result = _bootstrap_with_mcp(tmp_path, monkeypatch, write_mcp_json=True)
    assert result.exit_code == 0, f"Expected exit 0, got {result.exit_code}: {result.output}"
    mcp_json_path = pathlib.Path(str(tmp_path)) / ".mcp.json"
    assert mcp_json_path.exists(), "~/.mcp.json was not written"
    data = json.loads(mcp_json_path.read_text())
    assert "frontprompt" in data["mcpServers"]
    assert "command" in data["mcpServers"]["frontprompt"]


def test_bootstrap_write_mcp_json_merges(tmp_path: object, monkeypatch: object) -> None:
    """bootstrap --write-mcp-json merges into an existing ~/.mcp.json."""
    import pathlib

    mcp_json_path = pathlib.Path(str(tmp_path)) / ".mcp.json"
    existing = {"mcpServers": {"other-server": {"command": "/bin/other"}}}
    mcp_json_path.write_text(json.dumps(existing))

    result = _bootstrap_with_mcp(tmp_path, monkeypatch, write_mcp_json=True)
    assert result.exit_code == 0, f"Expected exit 0, got {result.exit_code}: {result.output}"
    data = json.loads(mcp_json_path.read_text())
    assert "other-server" in data["mcpServers"], "existing entry must be preserved"
    assert "frontprompt" in data["mcpServers"], "new entry must be added"


def test_bootstrap_write_mcp_json_already_up_to_date(tmp_path: object, monkeypatch: object) -> None:
    """bootstrap --write-mcp-json prints 'already up-to-date' when path unchanged."""
    import pathlib

    # Pre-populate with the exact same path that will be resolved.
    run_mcp = str(pathlib.Path(str(tmp_path)) / "run-mcp.sh")
    mcp_json_path = pathlib.Path(str(tmp_path)) / ".mcp.json"
    existing = {"mcpServers": {"frontprompt": {"command": run_mcp, "args": []}}}
    mcp_json_path.write_text(json.dumps(existing))

    result = _bootstrap_with_mcp(tmp_path, monkeypatch, write_mcp_json=True)
    assert result.exit_code == 0
    assert "already up-to-date" in result.output


def test_bootstrap_no_sentinel_shows_placeholder(tmp_path: object, monkeypatch: object) -> None:
    """bootstrap without sentinel (and no package-fallback) prints placeholder/hint."""
    import pathlib

    monkeypatch.setattr(pathlib.Path, "home", staticmethod(lambda: tmp_path))  # type: ignore[arg-type]

    # Also patch _resolve_run_mcp_path to return None — simulates a wheel install
    # where neither the sentinel nor a local clone can be found.
    fake_manifest = MagicMock(schema_version="0.7.0", bundle_size_bytes=123)
    runner = CliRunner()
    with (
        patch("frontprompt.overlay.loader.load_build_manifest", return_value=fake_manifest),
        patch("frontprompt.cli._resolve_run_mcp_path", return_value=None),
    ):
        result = runner.invoke(main, ["bootstrap", "--no-chromium"])

    assert result.exit_code == 0, f"Expected exit 0, got {result.exit_code}: {result.output}"
    # Either shows placeholder or setup hint
    assert "<path-to-run-mcp.sh>" in result.output or "run frontprompt setup" in result.output


def test_bootstrap_write_mcp_json_flag_mentioned_in_help() -> None:
    """--write-mcp-json flag is visible in bootstrap --help output."""
    runner = CliRunner()
    result = runner.invoke(main, ["bootstrap", "--help"])
    assert result.exit_code == 0
    assert "write-mcp-json" in result.output
