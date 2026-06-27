"""Subprocess bootstrap for voice-over e2e tests.

Auto-imported by Python at interpreter startup when this directory is on PYTHONPATH
(via Python's ``sitecustomize`` mechanism — see https://docs.python.org/3/library/site.html).

Activates ONLY when the ``FRONTPROMPT_E2E_VOICE_INJECT`` env var is set.
The test conftest (``tests/browser/test_voice_over_e2e.py``) sets this marker
before spawning the child ``frontprompt show`` subprocess, which inherits it.

When active, injects two things into the child process:
    1. ``MockTranscriptionBackend`` appended to ``REGISTERED_BACKENDS`` — so
       ``select_backend()`` returns the deterministic mock instead of looking
       for mlx_whisper.
    2. ``audio_capture.capture_source_override`` set to an async callable that
       copies the fixture WAV to ``wav_path`` instead of opening sounddevice.

Optionally (``FRONTPROMPT_E2E_MIC_INJECT=1``):
    3. Injects a fake sounddevice module so ``MicrophoneWatcher.run()`` returns
       at least one fake input device — enables V7 mic-dropdown e2e test without
       real audio hardware.

Nothing here runs in the parent pytest process (PYTHONPATH is set AFTER pytest
starts, and sitecustomize runs only at interpreter startup).
"""

from __future__ import annotations

import os

_fixture_wav_str = os.environ.get("FRONTPROMPT_E2E_VOICE_INJECT")

if _fixture_wav_str:
    import shutil
    from pathlib import Path

    _fixture_wav = Path(_fixture_wav_str)

    # ------------------------------------------------------------------
    # 1. Register mock transcription backend into the global registry.
    #    At this point REGISTERED_BACKENDS is the live list object —
    #    Python's module cache guarantees all later imports share it.
    # ------------------------------------------------------------------
    from frontprompt.voice.transcription import REGISTERED_BACKENDS
    from mock_transcription import MockTranscriptionBackend  # on PYTHONPATH (this dir)

    if not any(b.backend_id == "mock" for b in REGISTERED_BACKENDS):
        REGISTERED_BACKENDS.append(MockTranscriptionBackend())

    # ------------------------------------------------------------------
    # 2. Override AudioCaptureManager's capture source.
    #    Sets the module-level hook so start() copies the fixture WAV
    #    instead of opening a real sounddevice stream.
    # ------------------------------------------------------------------
    from frontprompt.voice import audio_capture as _ac

    async def _fixture_capture_start(
        recording_id: str,
        device_id: object,
        wav_path: Path,
    ) -> bool:
        """Copy fixture WAV to wav_path — no sounddevice required."""
        wav_path.parent.mkdir(parents=True, exist_ok=True)
        shutil.copy2(_fixture_wav, wav_path)
        return True

    _ac.capture_source_override = _fixture_capture_start

    # ------------------------------------------------------------------
    # 3. Fake microphone devices (FRONTPROMPT_E2E_MIC_INJECT=1).
    #    Injects a fake sounddevice module so MicrophoneWatcher.run()
    #    returns at least one fake input device on every poll cycle —
    #    ensures the mic dropdown test (V7) works without real hardware.
    # ------------------------------------------------------------------
    if os.environ.get("FRONTPROMPT_E2E_MIC_INJECT") == "1":
        import sys
        import types

        # Build a minimal fake sounddevice module that replaces the real one.
        # MicrophoneWatcher.run() only uses sd.query_devices() and sd.default.device.
        _fake_sd = types.ModuleType("sounddevice")

        class _FakePortAudioError(Exception):
            pass

        _FAKE_DEVICES = [
            {
                "index": 0,
                "name": "Fake Microphone (e2e-test)",
                "max_input_channels": 2,
                "max_output_channels": 0,
                "default_samplerate": 44100.0,
            },
        ]

        _fake_sd.PortAudioError = _FakePortAudioError  # type: ignore[attr-defined]
        _fake_sd.query_devices = lambda: _FAKE_DEVICES  # type: ignore[attr-defined]

        class _FakeDefault:
            device = (0, -1)  # (input_index, output_index)

        _fake_sd.default = _FakeDefault()  # type: ignore[attr-defined]

        sys.modules["sounddevice"] = _fake_sd
