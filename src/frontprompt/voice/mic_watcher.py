"""MicrophoneWatcher — topology-hash-based anyio background task.

Enumerates available input devices via sounddevice and pushes updates to
StateManager only when the device topology changes (state-based change detection,
not TTL-based polling — atlas convention).

Design constraints:
    - COL-2: ``import sounddevice`` is LAZY — inside ``run()`` only, never at module
      top (avoids PortAudio initialization at import time; consistent with the lazy
      pattern used elsewhere in the voice module).
    - State-based detection: ``_compute_topology_hash()`` computes a stable hash from
      the sorted list of (index, name) pairs for input devices. An update is pushed to
      StateManager only when the hash changes — avoids lock acquisition and snapshot
      broadcast on every no-change poll cycle.
    - The ``query_devices()`` call is synchronous (sounddevice wraps PortAudio), wrapped
      in ``anyio.to_thread.run_sync()`` to keep the event loop unblocked.
    - The watcher is a long-running anyio task — it is started via ``tg.start_soon()``
      in ``ShowSession.run()`` and lives until the task group is cancelled (browser close /
      SIGTERM).

sounddevice is a core dependency (promoted from [voice] optional extra in 0.0.6).
"""

from __future__ import annotations

import hashlib
from typing import TYPE_CHECKING, Any

import anyio
import structlog

if TYPE_CHECKING:
    from frontprompt.state import StateManager

_LOG = structlog.get_logger("frontprompt.voice.mic_watcher")


class MicrophoneWatcher:
    """Background task that watches for microphone topology changes.

    Usage::

        watcher = MicrophoneWatcher()
        tg.start_soon(watcher.run, state_manager)

    Change detection:
        ``_compute_topology_hash(devices)`` hashes the sorted list of
        ``(device['index'], device['name'])`` pairs from input devices
        (``max_input_channels > 0``). ``StateManager.update_microphone_state()``
        is called ONLY when the hash changes from the previous cycle — no
        no-op lock acquisitions on stable topologies.
    """

    @staticmethod
    def _compute_topology_hash(devices: list[Any]) -> str:
        """Compute a stable hex hash from a sounddevice device list.

        Considers only input devices (``max_input_channels > 0``). Result is
        order-independent (sorted before hashing) so device re-ordering between
        calls does not trigger a false-change event.

        Args:
            devices: List of sounddevice DeviceInfo (dict-like) objects or plain
                dicts with keys ``index``, ``name``, ``max_input_channels``.

        Returns:
            64-character SHA-256 hex digest.
        """
        input_items = sorted(
            (d["index"], d["name"])
            for d in devices
            if d["max_input_channels"] > 0
        )
        return hashlib.sha256(str(input_items).encode()).hexdigest()

    async def run(
        self,
        state_manager: StateManager,
        poll_interval_s: float = 2.0,
    ) -> None:
        """Anyio task body — runs until cancelled.

        Args:
            state_manager: StateManager instance to push topology updates to.
            poll_interval_s: Seconds between polls. Default 2.0 s.

        Note:
            ``import sounddevice`` is lazy — executed on the first call to ``run()``
            (COL-2). Subsequent iterations reuse the already-imported module.
            sounddevice is a core dependency; the lazy import is kept to defer PortAudio
            initialization until the watcher task actually runs.
        """
        import sounddevice as sd  # COL-2: lazy import inside run() — defer PortAudio init

        from frontprompt.state.state import MicrophoneDevice  # also lazy — avoids circular

        last_hash: str | None = None

        while True:
            try:
                raw_devices: list[Any] = await anyio.to_thread.run_sync(sd.query_devices)
            except Exception as exc:
                _LOG.warning("voice.mic_watcher.query_failed", error=str(exc))
                await anyio.sleep(poll_interval_s)
                continue

            current_hash = self._compute_topology_hash(raw_devices)

            if current_hash != last_hash:
                last_hash = current_hash

                # Build MicrophoneDevice list for the state manager
                input_devices = [
                    MicrophoneDevice(
                        device_id=d["index"],
                        name=d["name"],
                        channels=d["max_input_channels"],
                        default_sample_rate=d["default_samplerate"],
                    )
                    for d in raw_devices
                    if d["max_input_channels"] > 0
                ]

                # Candidate C fix: detect system default input device.
                # sd.default.device is a (input_index, output_index) tuple; input_index is
                # -1 when unset. Wrapped in try/except for environments where sd.default is
                # absent (headless CI, custom sounddevice stubs).
                system_default_device_id: int | None = None
                try:
                    default = sd.default.device
                    if isinstance(default, (list, tuple)) and len(default) >= 1:
                        idx = int(default[0])
                        system_default_device_id = idx if idx >= 0 else None
                    elif isinstance(default, int) and default >= 0:
                        system_default_device_id = default
                except Exception:
                    pass

                _LOG.info(
                    "voice.mic_watcher.topology_changed",
                    device_count=len(input_devices),
                    system_default=system_default_device_id,
                )
                await state_manager.update_microphone_state(input_devices, system_default_device_id=system_default_device_id)

            await anyio.sleep(poll_interval_s)


__all__ = ["MicrophoneWatcher"]
