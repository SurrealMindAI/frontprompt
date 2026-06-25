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
