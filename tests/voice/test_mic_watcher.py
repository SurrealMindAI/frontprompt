"""Tests for MicrophoneWatcher — topology-hash-based anyio background task.

Sub-plan 03 (voice-over). All tests mock sounddevice — no real PortAudio needed.

Coverage:
    - COL-2: lazy import (sounddevice not at module level)
    - topology-hash stability and change detection
    - update_microphone_state called on change, NOT on no-change
    - exactly once on 3 cycles with stable topology
    - task can be cancelled cleanly
"""

from __future__ import annotations

import sys
import types
from unittest.mock import AsyncMock, MagicMock

import anyio
import pytest


# ---------------------------------------------------------------------------
# Helpers: fake sounddevice + fake state manager
# ---------------------------------------------------------------------------


def _make_fake_sd_with_topology(topologies: list[list[dict]]) -> types.ModuleType:
    """Create a fake sounddevice that cycles through device topologies on each query_devices call."""
    fake = types.ModuleType("sounddevice")
    call_iter = iter(topologies)

    def query_devices() -> list[dict]:
        try:
            return next(call_iter)
        except StopIteration:
            # Repeat last topology on subsequent calls
            return topologies[-1]

    fake.query_devices = query_devices  # type: ignore[attr-defined]
    return fake


def _make_fake_sm() -> MagicMock:
    sm = MagicMock()
    sm.update_microphone_state = AsyncMock()
    return sm


# Canonical device topologies for tests
_TOPOLOGY_1 = [
    {"index": 0, "name": "Built-in Microphone", "max_input_channels": 1, "max_output_channels": 0, "default_samplerate": 44100.0},
]
_TOPOLOGY_2 = [
    {"index": 0, "name": "Built-in Microphone", "max_input_channels": 1, "max_output_channels": 0, "default_samplerate": 44100.0},
    {"index": 1, "name": "USB Headset", "max_input_channels": 2, "max_output_channels": 2, "default_samplerate": 48000.0},
]
_TOPOLOGY_OUTPUT_ONLY = [
    {"index": 0, "name": "Speakers", "max_input_channels": 0, "max_output_channels": 2, "default_samplerate": 44100.0},
]


# ---------------------------------------------------------------------------
# COL-2: lazy import — sounddevice NOT at module level of mic_watcher.py
# ---------------------------------------------------------------------------


def test_mic_watcher_lazy_import_no_sounddevice_at_module_level() -> None:
    """Importing voice/mic_watcher.py must NOT trigger `import sounddevice` (COL-2)."""
    sd_backup = sys.modules.pop("sounddevice", None)
    sys.modules.pop("frontprompt.voice.mic_watcher", None)

    try:
        import frontprompt.voice.mic_watcher  # noqa: F401
        assert "sounddevice" not in sys.modules, (
            "sounddevice MUST NOT be imported at module level of voice/mic_watcher.py — "
            "it is a [voice] optional extra."
        )
    finally:
        if sd_backup is not None:
            sys.modules["sounddevice"] = sd_backup
        sys.modules.pop("frontprompt.voice.mic_watcher", None)


# ---------------------------------------------------------------------------
# Section 1: _compute_topology_hash stability
# ---------------------------------------------------------------------------


def test_topology_hash_stable_same_input() -> None:
    """_compute_topology_hash returns the same hex string for identical input."""
    from frontprompt.voice.mic_watcher import MicrophoneWatcher

    h1 = MicrophoneWatcher._compute_topology_hash(_TOPOLOGY_1)
    h2 = MicrophoneWatcher._compute_topology_hash(_TOPOLOGY_1)
    assert h1 == h2
    assert isinstance(h1, str)
    assert len(h1) > 0, "Hash must be a non-empty hex string"


def test_topology_hash_different_for_different_input() -> None:
    """_compute_topology_hash returns different hashes for different topologies."""
    from frontprompt.voice.mic_watcher import MicrophoneWatcher

    h1 = MicrophoneWatcher._compute_topology_hash(_TOPOLOGY_1)
    h2 = MicrophoneWatcher._compute_topology_hash(_TOPOLOGY_2)
    assert h1 != h2


def test_topology_hash_stable_order_independent() -> None:
    """_compute_topology_hash is order-independent (uses sorted comparison)."""
    from frontprompt.voice.mic_watcher import MicrophoneWatcher

    # Same devices in different order — hash must be identical
    topo_a = [
        {"index": 0, "name": "Mic A", "max_input_channels": 1, "max_output_channels": 0, "default_samplerate": 44100.0},
        {"index": 1, "name": "Mic B", "max_input_channels": 2, "max_output_channels": 0, "default_samplerate": 48000.0},
    ]
    topo_b = [
        {"index": 1, "name": "Mic B", "max_input_channels": 2, "max_output_channels": 0, "default_samplerate": 48000.0},
        {"index": 0, "name": "Mic A", "max_input_channels": 1, "max_output_channels": 0, "default_samplerate": 44100.0},
    ]
    assert MicrophoneWatcher._compute_topology_hash(topo_a) == MicrophoneWatcher._compute_topology_hash(topo_b)


def test_topology_hash_ignores_output_only_devices() -> None:
    """_compute_topology_hash ignores devices with max_input_channels == 0."""
    from frontprompt.voice.mic_watcher import MicrophoneWatcher

    empty_hash = MicrophoneWatcher._compute_topology_hash([])
    output_only_hash = MicrophoneWatcher._compute_topology_hash(_TOPOLOGY_OUTPUT_ONLY)
    assert empty_hash == output_only_hash, (
        "Output-only devices (max_input_channels=0) must not affect the topology hash"
    )


# ---------------------------------------------------------------------------
# Section 2: watcher calls update_microphone_state on change, not on no-change
# ---------------------------------------------------------------------------


@pytest.mark.anyio
async def test_watcher_calls_update_on_topology_change() -> None:
    """Watcher calls update_microphone_state when topology changes between polls."""
    # Topology changes on second call
    fake_sd = _make_fake_sd_with_topology([_TOPOLOGY_1, _TOPOLOGY_2, _TOPOLOGY_2])
    fake_sm = _make_fake_sm()

    with __import__("unittest.mock", fromlist=["patch"]).patch.dict(sys.modules, {"sounddevice": fake_sd}):
        from frontprompt.voice.mic_watcher import MicrophoneWatcher

        watcher = MicrophoneWatcher()
        poll_count = 0
        original_sleep = anyio.sleep

        async def _fast_sleep(seconds: float) -> None:
            nonlocal poll_count
            poll_count += 1
            if poll_count >= 3:
                raise anyio.get_cancelled_exc_class()()
            await original_sleep(0)  # yield but don't wait

        with __import__("unittest.mock", fromlist=["patch"]).patch("anyio.sleep", _fast_sleep):
            try:
                await watcher.run(fake_sm, poll_interval_s=0.0)
            except BaseException:
                pass

    # Two topology changes observed → update called twice
    assert fake_sm.update_microphone_state.call_count == 2


@pytest.mark.anyio
async def test_watcher_no_update_on_same_topology() -> None:
    """Watcher does NOT call update_microphone_state when topology is unchanged."""
    # Same topology every call
    fake_sd = _make_fake_sd_with_topology([_TOPOLOGY_1, _TOPOLOGY_1, _TOPOLOGY_1])
    fake_sm = _make_fake_sm()

    with __import__("unittest.mock", fromlist=["patch"]).patch.dict(sys.modules, {"sounddevice": fake_sd}):
        from frontprompt.voice.mic_watcher import MicrophoneWatcher

        watcher = MicrophoneWatcher()
        poll_count = 0
        original_sleep = anyio.sleep

        async def _fast_sleep(seconds: float) -> None:
            nonlocal poll_count
            poll_count += 1
            if poll_count >= 4:
                raise anyio.get_cancelled_exc_class()()
            await original_sleep(0)

        with __import__("unittest.mock", fromlist=["patch"]).patch("anyio.sleep", _fast_sleep):
            try:
                await watcher.run(fake_sm, poll_interval_s=0.0)
            except BaseException:
                pass

    # Same topology across 3+ cycles → update called exactly once (first discovery)
    assert fake_sm.update_microphone_state.call_count == 1, (
        f"Expected exactly 1 update call (first cycle only), got {fake_sm.update_microphone_state.call_count}"
    )


@pytest.mark.anyio
async def test_watcher_called_exactly_once_on_stable_topology() -> None:
    """After 3 poll cycles with stable topology, update called exactly once (first cycle)."""
    fake_sd = _make_fake_sd_with_topology([_TOPOLOGY_2] * 10)
    fake_sm = _make_fake_sm()

    with __import__("unittest.mock", fromlist=["patch"]).patch.dict(sys.modules, {"sounddevice": fake_sd}):
        from frontprompt.voice.mic_watcher import MicrophoneWatcher

        watcher = MicrophoneWatcher()
        cycle = 0
        original_sleep = anyio.sleep

        async def _fast_sleep(seconds: float) -> None:
            nonlocal cycle
            cycle += 1
            if cycle >= 4:  # stop after 3 full poll cycles
                raise anyio.get_cancelled_exc_class()()
            await original_sleep(0)

        with __import__("unittest.mock", fromlist=["patch"]).patch("anyio.sleep", _fast_sleep):
            try:
                await watcher.run(fake_sm, poll_interval_s=0.0)
            except BaseException:
                pass

    assert fake_sm.update_microphone_state.call_count == 1


# ---------------------------------------------------------------------------
# Section 3: task can be cancelled cleanly
# ---------------------------------------------------------------------------


@pytest.mark.anyio
async def test_watcher_task_can_be_cancelled_cleanly() -> None:
    """MicrophoneWatcher task can be cancelled without raising to the caller."""
    fake_sd = _make_fake_sd_with_topology([_TOPOLOGY_1] * 100)
    fake_sm = _make_fake_sm()

    with __import__("unittest.mock", fromlist=["patch"]).patch.dict(sys.modules, {"sounddevice": fake_sd}):
        from frontprompt.voice.mic_watcher import MicrophoneWatcher

        watcher = MicrophoneWatcher()

        with anyio.fail_after(2.0):
            async with anyio.create_task_group() as tg:
                tg.start_soon(watcher.run, fake_sm, 0.001)
                await anyio.sleep(0.01)
                tg.cancel_scope.cancel()
        # No exception propagated — test passes if we reach here


# ---------------------------------------------------------------------------
# Section 4 (sub-plan 05): Regression tests — Candidate A + B + C fixes
# ---------------------------------------------------------------------------

# Helper topology constants for this section
_TOPOLOGY_TWO_INPUTS = [
    {"index": 0, "name": "Built-in Mic", "max_input_channels": 1, "max_output_channels": 0, "default_samplerate": 44100.0},
    {"index": 1, "name": "USB Headset", "max_input_channels": 2, "max_output_channels": 2, "default_samplerate": 48000.0},
]
_TOPOLOGY_OUTPUT_ONLY_ONLY = [
    {"index": 0, "name": "Speakers", "max_input_channels": 0, "max_output_channels": 2, "default_samplerate": 44100.0},
]


def _stop_after_one_poll() -> types.CoroutineType:
    """Return a patch target that cancels the watcher after the first sleep call."""
    import asyncio

    async def _one_shot_sleep(seconds: float) -> None:
        raise anyio.get_cancelled_exc_class()()

    return _one_shot_sleep  # type: ignore[return-value]


@pytest.mark.anyio
async def test_watcher_broadcasts_devices_on_first_poll() -> None:
    """First poll with 2 input devices broadcasts to real StateManager (Candidate A integration).

    Uses a real StateManager to exercise the production update_microphone_state
    early-exit sentinel — _make_fake_sm does not reproduce the sentinel bug (COL-4).
    """
    from unittest.mock import MagicMock, patch

    from frontprompt.state import StateManager

    fake_sd = _make_fake_sd_with_topology([_TOPOLOGY_TWO_INPUTS])
    fake_sd.default = MagicMock()
    fake_sd.default.device = (-1, -1)

    with patch.dict(sys.modules, {"sounddevice": fake_sd}):
        from frontprompt.voice.mic_watcher import MicrophoneWatcher

        sm = StateManager(session_id="test-05-a-two")
        watcher = MicrophoneWatcher()

        with patch("anyio.sleep", _stop_after_one_poll()):
            try:
                await watcher.run(sm, poll_interval_s=0.0)
            except BaseException:
                pass

    snap = sm.snapshot()
    assert len(snap.microphone_state.devices) == 2, (
        f"Expected 2 devices after first poll, got {len(snap.microphone_state.devices)}"
    )


@pytest.mark.anyio
async def test_watcher_broadcasts_empty_devices_on_first_poll() -> None:
    """First poll with only output devices must still broadcast (Candidate A regression).

    Before fix: frozenset() == frozenset() sentinel → early-exit fires → no broadcast.
    After fix:  None != frozenset() → update goes through → listener called with empty list.
    """
    from unittest.mock import MagicMock, patch

    from frontprompt.state import StateManager

    fake_sd = _make_fake_sd_with_topology([_TOPOLOGY_OUTPUT_ONLY_ONLY])
    fake_sd.default = MagicMock()
    fake_sd.default.device = (-1, -1)

    broadcast_calls: list[int] = []

    with patch.dict(sys.modules, {"sounddevice": fake_sd}):
        from frontprompt.voice.mic_watcher import MicrophoneWatcher

        sm = StateManager(session_id="test-05-a-empty")
        sm.add_snapshot_listener(lambda _snap: broadcast_calls.append(1))
        watcher = MicrophoneWatcher()

        with patch("anyio.sleep", _stop_after_one_poll()):
            try:
                await watcher.run(sm, poll_interval_s=0.0)
            except BaseException:
                pass

    snap = sm.snapshot()
    assert len(snap.microphone_state.devices) == 0, (
        "Expected 0 devices (all output-only), "
        f"got {len(snap.microphone_state.devices)}"
    )
    assert len(broadcast_calls) >= 1, (
        "Expected at least one broadcast to listeners after first poll with empty device list, "
        "but listener was never called — Candidate A early-exit sentinel bug."
    )


@pytest.mark.anyio
async def test_watcher_does_not_broadcast_on_unchanged_topology() -> None:
    """Two consecutive polls with the same topology call update_microphone_state exactly once.

    Validates watcher-level deduplication via last_hash. The second poll must not
    re-call update_microphone_state when device topology is stable.
    """
    from unittest.mock import patch

    # Same topology provided for both poll calls
    fake_sd = _make_fake_sd_with_topology([_TOPOLOGY_TWO_INPUTS, _TOPOLOGY_TWO_INPUTS])
    fake_sm = _make_fake_sm()

    poll_count = 0
    original_sleep = anyio.sleep

    async def _two_polls_then_cancel(seconds: float) -> None:
        nonlocal poll_count
        poll_count += 1
        if poll_count >= 2:
            raise anyio.get_cancelled_exc_class()()
        await original_sleep(0)

    with patch.dict(sys.modules, {"sounddevice": fake_sd}):
        from frontprompt.voice.mic_watcher import MicrophoneWatcher

        watcher = MicrophoneWatcher()

        with patch("anyio.sleep", _two_polls_then_cancel):
            try:
                await watcher.run(fake_sm, poll_interval_s=0.0)
            except BaseException:
                pass

    assert fake_sm.update_microphone_state.call_count == 1, (
        f"Expected exactly 1 update call for 2 stable-topology polls, "
        f"got {fake_sm.update_microphone_state.call_count}"
    )


@pytest.mark.anyio
async def test_watcher_recovers_after_exception() -> None:
    """Watcher recovers after a transient sd.query_devices OSError (Candidate B regression).

    First poll: OSError — watcher logs warning and continues.
    Second poll: returns 2 devices — state is updated successfully.
    """
    import types as _types
    from unittest.mock import MagicMock, patch

    from frontprompt.state import StateManager

    two_devices = _TOPOLOGY_TWO_INPUTS
    call_count = [0]

    def _query_devices_with_error() -> list[dict]:
        call_count[0] += 1
        if call_count[0] == 1:
            raise OSError("PortAudio: No audio device found")
        return two_devices

    fake_sd = _types.ModuleType("sounddevice")
    fake_sd.query_devices = _query_devices_with_error  # type: ignore[attr-defined]
    fake_sd.default = MagicMock()
    fake_sd.default.device = (-1, -1)

    poll_count = [0]
    original_sleep = anyio.sleep

    async def _two_polls_then_cancel(seconds: float) -> None:
        poll_count[0] += 1
        if poll_count[0] >= 2:
            raise anyio.get_cancelled_exc_class()()
        await original_sleep(0)

    with patch.dict(sys.modules, {"sounddevice": fake_sd}):
        from frontprompt.voice.mic_watcher import MicrophoneWatcher

        sm = StateManager(session_id="test-05-b-recovery")
        watcher = MicrophoneWatcher()

        with patch("anyio.sleep", _two_polls_then_cancel):
            try:
                await watcher.run(sm, poll_interval_s=0.0)
            except BaseException:
                pass

    snap = sm.snapshot()
    assert len(snap.microphone_state.devices) == 2, (
        f"Expected 2 devices after recovery, got {len(snap.microphone_state.devices)}"
    )


@pytest.mark.anyio
async def test_watcher_populates_system_default_device_id() -> None:
    """Watcher threads system_default_device_id through to StateManager (Candidate C regression).

    sd.default.device = (1, 2) → input index is 1 → snapshot.system_default_device_id == 1.
    Before fix: update_microphone_state never receives system_default → stays None.
    After fix:  watcher reads sd.default.device[0] and passes it through.
    """
    from unittest.mock import MagicMock, patch

    from frontprompt.state import StateManager

    fake_sd = _make_fake_sd_with_topology([_TOPOLOGY_TWO_INPUTS])
    fake_sd.default = MagicMock()
    fake_sd.default.device = (1, 2)  # input index = 1

    with patch.dict(sys.modules, {"sounddevice": fake_sd}):
        from frontprompt.voice.mic_watcher import MicrophoneWatcher

        sm = StateManager(session_id="test-05-c-default")
        watcher = MicrophoneWatcher()

        with patch("anyio.sleep", _stop_after_one_poll()):
            try:
                await watcher.run(sm, poll_interval_s=0.0)
            except BaseException:
                pass

    snap = sm.snapshot()
    assert snap.microphone_state.system_default_device_id == 1, (
        f"Expected system_default_device_id=1 from sd.default.device=(1, 2), "
        f"got {snap.microphone_state.system_default_device_id}"
    )
