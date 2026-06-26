"""CLI bootstrap --voice integration tests.

Section 4 of sub-plan 04 — write tests first (TDD).

Tests verify:
    - ``frontprompt bootstrap --voice`` triggers backend ensure() (mocked)
    - ``frontprompt bootstrap`` (no --voice flag) still works — backward compat
    - ``frontprompt doctor`` output mentions voice backend status (mocked probe)
    - ``frontprompt bootstrap --help`` mentions --voice flag
"""

from __future__ import annotations

from pathlib import Path
from unittest.mock import AsyncMock, MagicMock, patch

import pytest
from click.testing import CliRunner

from frontprompt.cli import main


# ---------------------------------------------------------------------------
# Shared helpers
# ---------------------------------------------------------------------------


def _fake_manifest() -> MagicMock:
    return MagicMock(schema_version="0.10.0", bundle_size_bytes=999)


def _fake_backend(status: str = "ready") -> MagicMock:
    """Return a minimal fake backend mock."""
    b = MagicMock()
    b.backend_id = "fake_backend"
    b.display_name = "Fake Backend"
    b.probe_status = MagicMock(return_value=status)
    b.ensure = AsyncMock(return_value=None)
    return b


# ---------------------------------------------------------------------------
# Section 4a: bootstrap --voice calls ensure() on needs_download backends
# ---------------------------------------------------------------------------


def test_bootstrap_voice_triggers_ensure_on_needs_download_backend() -> None:
    """bootstrap --voice calls backend.ensure() when probe_status() == 'needs_download'."""
    backend = _fake_backend(status="needs_download")

    runner = CliRunner()
    with (
        patch("frontprompt.overlay.loader.load_build_manifest", return_value=_fake_manifest()),
        patch("frontprompt.voice.transcription.REGISTERED_BACKENDS", [backend]),
    ):
        result = runner.invoke(main, ["bootstrap", "--no-chromium", "--voice"])

    assert result.exit_code == 0, f"Expected exit 0, got {result.exit_code}: {result.output}"
    backend.ensure.assert_called_once()


def test_bootstrap_voice_skips_ensure_when_backend_is_ready() -> None:
    """bootstrap --voice does NOT call ensure() when backend is already ready."""
    backend = _fake_backend(status="ready")

    runner = CliRunner()
    with (
        patch("frontprompt.overlay.loader.load_build_manifest", return_value=_fake_manifest()),
        patch("frontprompt.voice.transcription.REGISTERED_BACKENDS", [backend]),
    ):
        result = runner.invoke(main, ["bootstrap", "--no-chromium", "--voice"])

    assert result.exit_code == 0, result.output
    backend.ensure.assert_not_called()


def test_bootstrap_voice_skips_ensure_when_backend_is_unavailable() -> None:
    """bootstrap --voice does NOT call ensure() when backend is unavailable (wrong platform)."""
    backend = _fake_backend(status="unavailable")

    runner = CliRunner()
    with (
        patch("frontprompt.overlay.loader.load_build_manifest", return_value=_fake_manifest()),
        patch("frontprompt.voice.transcription.REGISTERED_BACKENDS", [backend]),
    ):
        result = runner.invoke(main, ["bootstrap", "--no-chromium", "--voice"])

    assert result.exit_code == 0, result.output
    backend.ensure.assert_not_called()


# ---------------------------------------------------------------------------
# Section 4b: bootstrap (no --voice) is backward-compatible
# ---------------------------------------------------------------------------


def test_bootstrap_without_voice_flag_exits_zero() -> None:
    """bootstrap (no --voice flag) works as before — backward compatible."""
    runner = CliRunner()
    with patch("frontprompt.overlay.loader.load_build_manifest", return_value=_fake_manifest()):
        result = runner.invoke(main, ["bootstrap", "--no-chromium"])

    assert result.exit_code == 0, f"Expected exit 0, got {result.exit_code}: {result.output}"
    # Overlay verification should still appear
    assert "overlay bundle" in result.output
    assert "embedded" in result.output


def test_bootstrap_without_voice_flag_does_not_call_ensure() -> None:
    """bootstrap without --voice does NOT call any backend ensure()."""
    backend = _fake_backend(status="needs_download")

    runner = CliRunner()
    with (
        patch("frontprompt.overlay.loader.load_build_manifest", return_value=_fake_manifest()),
        patch("frontprompt.voice.transcription.REGISTERED_BACKENDS", [backend]),
    ):
        result = runner.invoke(main, ["bootstrap", "--no-chromium"])

    assert result.exit_code == 0, result.output
    backend.ensure.assert_not_called()


# ---------------------------------------------------------------------------
# Section 4c: bootstrap --help mentions --voice
# ---------------------------------------------------------------------------


def test_bootstrap_help_mentions_voice_flag() -> None:
    """bootstrap --help shows the --voice flag."""
    runner = CliRunner()
    result = runner.invoke(main, ["bootstrap", "--help"])
    assert result.exit_code == 0
    assert "voice" in result.output.lower()


# ---------------------------------------------------------------------------
# Section 4d: doctor mentions voice backend status
# ---------------------------------------------------------------------------


def test_doctor_mentions_voice_backend_status() -> None:
    """doctor output includes voice backend status line(s)."""
    backend = _fake_backend(status="unavailable")

    runner = CliRunner()
    with (
        patch("frontprompt.overlay.loader.load_build_manifest", return_value=_fake_manifest()),
        patch("frontprompt.voice.transcription.REGISTERED_BACKENDS", [backend]),
    ):
        result = runner.invoke(main, ["doctor"])

    assert result.exit_code == 0, f"Expected exit 0, got {result.exit_code}: {result.output}"
    # Doctor should mention voice backend(s)
    assert "fake_backend" in result.output or "voice" in result.output.lower()


def test_doctor_shows_ready_backend() -> None:
    """doctor output shows 'ready' when backend is ready."""
    backend = _fake_backend(status="ready")

    runner = CliRunner()
    with (
        patch("frontprompt.overlay.loader.load_build_manifest", return_value=_fake_manifest()),
        patch("frontprompt.voice.transcription.REGISTERED_BACKENDS", [backend]),
    ):
        result = runner.invoke(main, ["doctor"])

    assert result.exit_code == 0, result.output
    assert "ready" in result.output
