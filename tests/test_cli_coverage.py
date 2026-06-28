"""Additional CLI coverage tests — covers branches not hit by test_cli.py.

Targets: sessions_list, sessions_prune, state, picks_get, picks_list, ping,
recordings_replay (invalid JSON), doctor command paths, _ensure_voice_backends,
_resolve_session error branches, bootstrap with chromium.
"""

from __future__ import annotations

from unittest.mock import AsyncMock, MagicMock, patch

import pytest
from click.testing import CliRunner

from frontprompt.cli import main
from frontprompt.ipc.protocol import IpcResponse


# ── _resolve_session error paths ──────────────────────────────────────────────


def test_resolve_session_with_unknown_session_id_exits_2() -> None:
    """_resolve_session with explicit session_id that doesn't exist exits 2."""
    runner = CliRunner()
    with (
        patch("frontprompt.ipc.discover_sessions", return_value=[]),
        patch("frontprompt.ipc.pick_latest_session", return_value=None),
    ):
        result = runner.invoke(main, ["picks", "list", "--session", "nonexistent-id"])
    assert result.exit_code == 2
    assert "nonexistent-id" in result.output or "nicht gefunden" in result.output


def test_resolve_session_with_no_sessions_exits_2() -> None:
    """_resolve_session with no sessions (latest=None) exits 2."""
    runner = CliRunner()
    with (
        patch("frontprompt.ipc.pick_latest_session", return_value=None),
        patch("frontprompt.ipc.discover_sessions", return_value=[]),
    ):
        result = runner.invoke(main, ["page-info"])
    assert result.exit_code == 2


# ── sessions list ─────────────────────────────────────────────────────────────


def test_sessions_list_emits_empty_json() -> None:
    """sessions list emits [] when no sessions are running."""
    runner = CliRunner()
    with patch("frontprompt.ipc.discover_sessions", return_value=[]):
        result = runner.invoke(main, ["sessions", "list"])
    assert result.exit_code == 0
    assert "[]" in result.output


def test_sessions_list_emits_session_data() -> None:
    """sessions list emits JSON representation of running sessions."""
    fake_session = MagicMock()
    fake_session.model_dump.return_value = {"session_id": "abc", "url": "https://x.com"}
    runner = CliRunner()
    with patch("frontprompt.ipc.discover_sessions", return_value=[fake_session]):
        result = runner.invoke(main, ["sessions", "list"])
    assert result.exit_code == 0
    assert "abc" in result.output


# ── sessions prune ────────────────────────────────────────────────────────────


def test_sessions_prune_emits_pruned_list() -> None:
    """sessions prune calls prune_dead_sessions and emits result."""
    runner = CliRunner()
    with patch("frontprompt.ipc.prune_dead_sessions", return_value=["old-session-1"]):
        result = runner.invoke(main, ["sessions", "prune"])
    assert result.exit_code == 0
    assert "pruned" in result.output
    assert "old-session-1" in result.output


def test_sessions_prune_empty() -> None:
    """sessions prune with no dead sessions emits empty pruned list."""
    runner = CliRunner()
    with patch("frontprompt.ipc.prune_dead_sessions", return_value=[]):
        result = runner.invoke(main, ["sessions", "prune"])
    assert result.exit_code == 0
    assert "pruned" in result.output


# ── state command ─────────────────────────────────────────────────────────────


def test_state_command_emits_snapshot_json() -> None:
    """state command sends GetSnapshotRequest and emits JSON."""
    fake_sess = MagicMock(socket_path="/tmp/fp.sock", session_id="s1")
    data = {"picks": [], "regions": []}

    async def fake_query(socket_path: object, request: object, **_kw: object) -> IpcResponse:
        return IpcResponse(ok=True, data=data)

    runner = CliRunner()
    with (
        patch("frontprompt.cli._resolve_session", return_value=fake_sess),
        patch("frontprompt.ipc.query", new=fake_query),
    ):
        result = runner.invoke(main, ["state"])
    assert result.exit_code == 0
    assert "picks" in result.output


# ── picks list ────────────────────────────────────────────────────────────────


def test_picks_list_emits_picks() -> None:
    """picks list sends GetPicksRequest and emits JSON."""
    from pathlib import Path

    fake_sess = MagicMock(socket_path="/tmp/fp.sock", session_id="s1")
    data = [{"pick_id": "p1", "url": "https://example.com"}]

    async def fake_query(socket_path: object, request: object, **_kw: object) -> IpcResponse:
        return IpcResponse(ok=True, data=data)

    runner = CliRunner()
    with (
        patch("frontprompt.cli._resolve_session", return_value=fake_sess),
        patch("frontprompt.ipc.query", new=fake_query),
    ):
        result = runner.invoke(main, ["picks", "list"])
    assert result.exit_code == 0
    assert "p1" in result.output


# ── picks get ────────────────────────────────────────────────────────────────


def test_picks_get_exits_4_on_pick_not_found() -> None:
    """picks get exits 4 when server returns ok=False (pick not found)."""
    fake_sess = MagicMock(socket_path="/tmp/fp.sock", session_id="s1")

    async def fake_query(socket_path: object, request: object, **_kw: object) -> IpcResponse:
        return IpcResponse(ok=False, error="pick_not_found: p99")

    runner = CliRunner()
    with (
        patch("frontprompt.cli._resolve_session", return_value=fake_sess),
        patch("frontprompt.ipc.query", new=fake_query),
    ):
        result = runner.invoke(main, ["picks", "get", "p99"])
    assert result.exit_code == 4


def test_picks_get_exits_3_on_connection_error() -> None:
    """picks get exits 3 when IPC connection fails."""
    from frontprompt.ipc import IpcConnectError

    fake_sess = MagicMock(socket_path="/tmp/fp.sock", session_id="s1")

    async def boom_query(socket_path: object, request: object, **_kw: object) -> object:
        raise IpcConnectError("no socket")

    runner = CliRunner()
    with (
        patch("frontprompt.cli._resolve_session", return_value=fake_sess),
        patch("frontprompt.ipc.query", new=boom_query),
    ):
        result = runner.invoke(main, ["picks", "get", "p1"])
    assert result.exit_code == 3
    assert "no socket" in result.output


def test_picks_get_success() -> None:
    """picks get emits pick data on ok=True response."""
    fake_sess = MagicMock(socket_path="/tmp/fp.sock", session_id="s1")

    async def fake_query(socket_path: object, request: object, **_kw: object) -> IpcResponse:
        return IpcResponse(ok=True, data={"pick_id": "p1", "url": "https://x.com"})

    runner = CliRunner()
    with (
        patch("frontprompt.cli._resolve_session", return_value=fake_sess),
        patch("frontprompt.ipc.query", new=fake_query),
    ):
        result = runner.invoke(main, ["picks", "get", "p1"])
    assert result.exit_code == 0
    assert "p1" in result.output


# ── ping command ──────────────────────────────────────────────────────────────


def test_ping_command_success() -> None:
    """ping command reports session_id on successful pong."""
    fake_sess = MagicMock(socket_path="/tmp/fp.sock", session_id="my-session")

    async def fake_query(socket_path: object, request: object, **_kw: object) -> IpcResponse:
        return IpcResponse(ok=True, data={"pong": True})

    runner = CliRunner()
    with (
        patch("frontprompt.cli._resolve_session", return_value=fake_sess),
        patch("frontprompt.ipc.query", new=fake_query),
    ):
        result = runner.invoke(main, ["ping"])
    assert result.exit_code == 0
    assert "my-session" in result.output


def test_ping_command_exits_3_on_connection_error() -> None:
    """ping exits 3 when IPC connection fails."""
    from frontprompt.ipc import IpcConnectError

    fake_sess = MagicMock(socket_path="/tmp/fp.sock", session_id="s1")

    async def boom_query(socket_path: object, request: object, **_kw: object) -> object:
        raise IpcConnectError("connection refused")

    runner = CliRunner()
    with (
        patch("frontprompt.cli._resolve_session", return_value=fake_sess),
        patch("frontprompt.ipc.query", new=boom_query),
    ):
        result = runner.invoke(main, ["ping"])
    assert result.exit_code == 3
    assert "connection refused" in result.output


def test_ping_command_exits_3_on_error_response() -> None:
    """ping exits 3 on ok=False response."""
    fake_sess = MagicMock(socket_path="/tmp/fp.sock", session_id="s1")

    async def fake_query(socket_path: object, request: object, **_kw: object) -> IpcResponse:
        return IpcResponse(ok=False, error="daemon_error")

    runner = CliRunner()
    with (
        patch("frontprompt.cli._resolve_session", return_value=fake_sess),
        patch("frontprompt.ipc.query", new=fake_query),
    ):
        result = runner.invoke(main, ["ping"])
    assert result.exit_code == 3


# ── recordings replay invalid JSON ────────────────────────────────────────────


def test_recordings_replay_invalid_json_exits_2() -> None:
    """recordings replay --parameters with invalid JSON exits 2."""
    fake_sess = MagicMock(socket_path="/tmp/fp.sock", session_id="s1")
    runner = CliRunner()
    with patch("frontprompt.cli._resolve_session", return_value=fake_sess):
        result = runner.invoke(main, ["recordings", "replay", "r1", "--parameters", "{invalid json}"])
    assert result.exit_code == 2
    assert "JSON" in result.output


def test_recordings_replay_valid_json_sends_request() -> None:
    """recordings replay --parameters with valid JSON sends RunReplayRequest."""
    fake_sess = MagicMock(socket_path="/tmp/fp.sock", session_id="s1")
    captured: dict = {}

    async def fake_query(socket_path: object, request: object, **_kw: object) -> IpcResponse:
        captured["req"] = request
        return IpcResponse(ok=True, data={"replay_id": "rp1", "status": "complete"})

    runner = CliRunner()
    with (
        patch("frontprompt.cli._resolve_session", return_value=fake_sess),
        patch("frontprompt.ipc.query", new=fake_query),
    ):
        result = runner.invoke(main, ["recordings", "replay", "r1", "--parameters", '{"x": "y"}'])
    assert result.exit_code == 0
    assert captured["req"].parameters == {"x": "y"}


# ── doctor command ────────────────────────────────────────────────────────────


def test_doctor_all_checks_pass() -> None:
    """doctor exits 0 when overlay, chromium, and voice are all OK."""
    import types

    fake_manifest = MagicMock(schema_version="0.7.0", bundle_size_bytes=1000)
    fake_backend = MagicMock()
    fake_backend.probe_status.return_value = "ready"
    fake_backend.backend_id = "mlx_whisper"
    fake_backend.display_name = "MLX Whisper"

    fake_transcription = types.SimpleNamespace(REGISTERED_BACKENDS=[fake_backend])

    runner = CliRunner()
    with (
        patch("frontprompt.overlay.loader.load_build_manifest", return_value=fake_manifest),
        patch("frontprompt.browser.manager._chromium_present", return_value=True),
        patch("frontprompt.voice.transcription", fake_transcription),
    ):
        result = runner.invoke(main, ["doctor"])
    assert result.exit_code == 0
    assert "all checks passed" in result.output


def test_doctor_missing_overlay_exits_1() -> None:
    """doctor exits 1 when overlay bundle is missing."""
    import types

    fake_transcription = types.SimpleNamespace(REGISTERED_BACKENDS=[])

    runner = CliRunner()
    with (
        patch("frontprompt.overlay.loader.load_build_manifest", side_effect=FileNotFoundError("no overlay")),
        patch("frontprompt.browser.manager._chromium_present", return_value=True),
        patch("frontprompt.voice.transcription", fake_transcription),
    ):
        result = runner.invoke(main, ["doctor"])
    assert result.exit_code == 1
    assert "MISSING" in result.output


def test_doctor_missing_chromium_exits_1() -> None:
    """doctor exits 1 when chromium is not installed."""
    import types

    fake_manifest = MagicMock(schema_version="0.7.0", bundle_size_bytes=1000)
    fake_transcription = types.SimpleNamespace(REGISTERED_BACKENDS=[])

    runner = CliRunner()
    with (
        patch("frontprompt.overlay.loader.load_build_manifest", return_value=fake_manifest),
        patch("frontprompt.browser.manager._chromium_present", return_value=False),
        patch("frontprompt.voice.transcription", fake_transcription),
    ):
        result = runner.invoke(main, ["doctor"])
    assert result.exit_code == 1
    assert "MISSING" in result.output


def test_doctor_voice_backend_unavailable() -> None:
    """doctor reports unavailable backend without failing (optional feature)."""
    import types

    fake_manifest = MagicMock(schema_version="0.7.0", bundle_size_bytes=1000)
    fake_backend = MagicMock()
    fake_backend.probe_status.return_value = "unavailable"
    fake_backend.backend_id = "mlx_whisper"
    fake_backend.display_name = "MLX Whisper"

    fake_transcription = types.SimpleNamespace(REGISTERED_BACKENDS=[fake_backend])

    runner = CliRunner()
    with (
        patch("frontprompt.overlay.loader.load_build_manifest", return_value=fake_manifest),
        patch("frontprompt.browser.manager._chromium_present", return_value=True),
        patch("frontprompt.voice.transcription", fake_transcription),
    ):
        result = runner.invoke(main, ["doctor"])
    assert result.exit_code == 0
    assert "unavailable" in result.output


def test_doctor_voice_backend_missing_dep() -> None:
    """doctor reports missing_dep backend status."""
    import types

    fake_manifest = MagicMock(schema_version="0.7.0", bundle_size_bytes=1000)
    fake_backend = MagicMock()
    fake_backend.probe_status.return_value = "missing_dep"
    fake_backend.backend_id = "mlx_whisper"

    fake_transcription = types.SimpleNamespace(REGISTERED_BACKENDS=[fake_backend])

    runner = CliRunner()
    with (
        patch("frontprompt.overlay.loader.load_build_manifest", return_value=fake_manifest),
        patch("frontprompt.browser.manager._chromium_present", return_value=True),
        patch("frontprompt.voice.transcription", fake_transcription),
    ):
        result = runner.invoke(main, ["doctor"])
    assert result.exit_code == 0  # voice is optional, doesn't affect exit_code
    assert "mlx-whisper" in result.output.lower() or "missing" in result.output.lower()


def test_doctor_voice_backend_needs_download() -> None:
    """doctor reports needs_download backend status."""
    import types

    fake_manifest = MagicMock(schema_version="0.7.0", bundle_size_bytes=1000)
    fake_backend = MagicMock()
    fake_backend.probe_status.return_value = "needs_download"
    fake_backend.backend_id = "mlx_whisper"

    fake_transcription = types.SimpleNamespace(REGISTERED_BACKENDS=[fake_backend])

    runner = CliRunner()
    with (
        patch("frontprompt.overlay.loader.load_build_manifest", return_value=fake_manifest),
        patch("frontprompt.browser.manager._chromium_present", return_value=True),
        patch("frontprompt.voice.transcription", fake_transcription),
    ):
        result = runner.invoke(main, ["doctor"])
    assert result.exit_code == 0
    assert "bootstrap" in result.output


def test_doctor_voice_backend_unknown_status() -> None:
    """doctor handles unknown voice backend status gracefully."""
    import types

    fake_manifest = MagicMock(schema_version="0.7.0", bundle_size_bytes=1000)
    fake_backend = MagicMock()
    fake_backend.probe_status.return_value = "some_unknown_status"
    fake_backend.backend_id = "test_backend"

    fake_transcription = types.SimpleNamespace(REGISTERED_BACKENDS=[fake_backend])

    runner = CliRunner()
    with (
        patch("frontprompt.overlay.loader.load_build_manifest", return_value=fake_manifest),
        patch("frontprompt.browser.manager._chromium_present", return_value=True),
        patch("frontprompt.voice.transcription", fake_transcription),
    ):
        result = runner.invoke(main, ["doctor"])
    assert result.exit_code == 0


def test_doctor_no_backends() -> None:
    """doctor reports 'none registered' when no voice backends exist."""
    import types

    fake_manifest = MagicMock(schema_version="0.7.0", bundle_size_bytes=1000)
    fake_transcription = types.SimpleNamespace(REGISTERED_BACKENDS=[])

    runner = CliRunner()
    with (
        patch("frontprompt.overlay.loader.load_build_manifest", return_value=fake_manifest),
        patch("frontprompt.browser.manager._chromium_present", return_value=True),
        patch("frontprompt.voice.transcription", fake_transcription),
    ):
        result = runner.invoke(main, ["doctor"])
    assert result.exit_code == 0
    assert "none registered" in result.output


# ── _ensure_voice_backends (bootstrap --voice) ────────────────────────────────


def test_bootstrap_no_voice_skips_backends() -> None:
    """bootstrap without --voice skips backends."""
    fake_manifest = MagicMock(schema_version="0.7.0", bundle_size_bytes=1000)
    runner = CliRunner()
    with (
        patch("frontprompt.overlay.loader.load_build_manifest", return_value=fake_manifest),
    ):
        result = runner.invoke(main, ["bootstrap", "--no-chromium", "--no-voice"])
    assert result.exit_code == 0
    assert "skipped" in result.output


def test_bootstrap_voice_with_ready_backend() -> None:
    """bootstrap --voice with already-ready backend reports ready."""
    import types

    fake_manifest = MagicMock(schema_version="0.7.0", bundle_size_bytes=1000)
    fake_backend = MagicMock()
    fake_backend.probe_status.return_value = "ready"
    fake_backend.backend_id = "mlx_whisper"
    fake_backend.display_name = "MLX Whisper"
    fake_backend.ensure = AsyncMock()

    fake_transcription = types.SimpleNamespace(REGISTERED_BACKENDS=[fake_backend])

    runner = CliRunner()
    with (
        patch("frontprompt.overlay.loader.load_build_manifest", return_value=fake_manifest),
        patch("frontprompt.voice.transcription", fake_transcription),
    ):
        result = runner.invoke(main, ["bootstrap", "--no-chromium", "--voice"])
    assert result.exit_code == 0
    assert "already ready" in result.output


def test_bootstrap_voice_with_unavailable_backend() -> None:
    """bootstrap --voice with unavailable backend reports unavailable."""
    import types

    fake_manifest = MagicMock(schema_version="0.7.0", bundle_size_bytes=1000)
    fake_backend = MagicMock()
    fake_backend.probe_status.return_value = "unavailable"
    fake_backend.backend_id = "mlx_whisper"

    fake_transcription = types.SimpleNamespace(REGISTERED_BACKENDS=[fake_backend])

    runner = CliRunner()
    with (
        patch("frontprompt.overlay.loader.load_build_manifest", return_value=fake_manifest),
        patch("frontprompt.voice.transcription", fake_transcription),
    ):
        result = runner.invoke(main, ["bootstrap", "--no-chromium", "--voice"])
    assert result.exit_code == 0
    assert "unavailable" in result.output


def test_bootstrap_voice_with_missing_dep_backend() -> None:
    """bootstrap --voice with missing_dep backend reports missing dep."""
    import types

    fake_manifest = MagicMock(schema_version="0.7.0", bundle_size_bytes=1000)
    fake_backend = MagicMock()
    fake_backend.probe_status.return_value = "missing_dep"
    fake_backend.backend_id = "mlx_whisper"

    fake_transcription = types.SimpleNamespace(REGISTERED_BACKENDS=[fake_backend])

    runner = CliRunner()
    with (
        patch("frontprompt.overlay.loader.load_build_manifest", return_value=fake_manifest),
        patch("frontprompt.voice.transcription", fake_transcription),
    ):
        result = runner.invoke(main, ["bootstrap", "--no-chromium", "--voice"])
    assert result.exit_code == 0
    assert "missing dep" in result.output


def test_bootstrap_voice_with_needs_download_backend() -> None:
    """bootstrap --voice with needs_download backend downloads model."""
    import types

    fake_manifest = MagicMock(schema_version="0.7.0", bundle_size_bytes=1000)
    fake_backend = MagicMock()
    fake_backend.probe_status.return_value = "needs_download"
    fake_backend.backend_id = "mlx_whisper"
    fake_backend.display_name = "MLX Whisper"
    fake_backend.ensure = AsyncMock()

    fake_transcription = types.SimpleNamespace(REGISTERED_BACKENDS=[fake_backend])

    runner = CliRunner()
    with (
        patch("frontprompt.overlay.loader.load_build_manifest", return_value=fake_manifest),
        patch("frontprompt.voice.transcription", fake_transcription),
    ):
        result = runner.invoke(main, ["bootstrap", "--no-chromium", "--voice"])
    assert result.exit_code == 0
    assert "model downloaded" in result.output
    fake_backend.ensure.assert_called_once()


def test_bootstrap_voice_with_no_backends() -> None:
    """bootstrap --voice with no registered backends reports 'none registered'."""
    import types

    fake_manifest = MagicMock(schema_version="0.7.0", bundle_size_bytes=1000)
    fake_transcription = types.SimpleNamespace(REGISTERED_BACKENDS=[])

    runner = CliRunner()
    with (
        patch("frontprompt.overlay.loader.load_build_manifest", return_value=fake_manifest),
        patch("frontprompt.voice.transcription", fake_transcription),
    ):
        result = runner.invoke(main, ["bootstrap", "--no-chromium", "--voice"])
    assert result.exit_code == 0
    assert "none registered" in result.output


def test_bootstrap_voice_unknown_backend_status() -> None:
    """bootstrap --voice with unknown status reports unknown."""
    import types

    fake_manifest = MagicMock(schema_version="0.7.0", bundle_size_bytes=1000)
    fake_backend = MagicMock()
    fake_backend.probe_status.return_value = "cosmic_ray_flipped_a_bit"
    fake_backend.backend_id = "weird_backend"

    fake_transcription = types.SimpleNamespace(REGISTERED_BACKENDS=[fake_backend])

    runner = CliRunner()
    with (
        patch("frontprompt.overlay.loader.load_build_manifest", return_value=fake_manifest),
        patch("frontprompt.voice.transcription", fake_transcription),
    ):
        result = runner.invoke(main, ["bootstrap", "--no-chromium", "--voice"])
    assert result.exit_code == 0


# ── bootstrap with chromium ───────────────────────────────────────────────────


def test_bootstrap_with_chromium_success() -> None:
    """bootstrap with chromium (default) calls playwright install."""
    import subprocess

    fake_manifest = MagicMock(schema_version="0.7.0", bundle_size_bytes=1000)
    fake_result = MagicMock(returncode=0)

    runner = CliRunner()
    with (
        patch("frontprompt.overlay.loader.load_build_manifest", return_value=fake_manifest),
        patch("subprocess.run", return_value=fake_result) as mock_run,
    ):
        result = runner.invoke(main, ["bootstrap"])
    assert result.exit_code == 0
    assert mock_run.called
    assert "chromium" in result.output
    assert "installed" in result.output


def test_bootstrap_with_chromium_install_failure() -> None:
    """bootstrap exits non-zero when playwright install fails."""
    fake_manifest = MagicMock(schema_version="0.7.0", bundle_size_bytes=1000)
    fake_result = MagicMock(returncode=1)

    runner = CliRunner()
    with (
        patch("frontprompt.overlay.loader.load_build_manifest", return_value=fake_manifest),
        patch("subprocess.run", return_value=fake_result),
    ):
        result = runner.invoke(main, ["bootstrap"])
    assert result.exit_code == 1


# ── _resolve_session found by session_id ─────────────────────────────────────


def test_resolve_session_finds_by_exact_id() -> None:
    """_resolve_session returns the session when its session_id matches."""
    matching = MagicMock(socket_path="/tmp/s.sock", session_id="target-id")
    other = MagicMock(socket_path="/tmp/o.sock", session_id="other-id")

    async def fake_query(socket_path: object, request: object, **_kw: object) -> IpcResponse:
        return IpcResponse(ok=True, data={"picks": []})

    runner = CliRunner()
    with (
        patch("frontprompt.ipc.discover_sessions", return_value=[other, matching]),
        patch("frontprompt.ipc.query", new=fake_query),
    ):
        result = runner.invoke(main, ["picks", "list", "--session", "target-id"])
    assert result.exit_code == 0


# ── _emit_json ────────────────────────────────────────────────────────────────


def test_emit_json_handles_unicode() -> None:
    """_emit_json emits non-ASCII JSON without escaping (ensure_ascii=False)."""
    fake_sess = MagicMock(socket_path="/tmp/fp.sock", session_id="s1")
    data = {"name": "Ärger mit Öl"}

    async def fake_query(socket_path: object, request: object, **_kw: object) -> IpcResponse:
        return IpcResponse(ok=True, data=data)

    runner = CliRunner()
    with (
        patch("frontprompt.cli._resolve_session", return_value=fake_sess),
        patch("frontprompt.ipc.query", new=fake_query),
    ):
        result = runner.invoke(main, ["state"])
    assert result.exit_code == 0
    assert "Ärger" in result.output
