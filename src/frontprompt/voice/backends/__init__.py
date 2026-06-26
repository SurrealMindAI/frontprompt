"""Voice backends package — registers all available backends into the global registry.

Import this package to populate :data:`frontprompt.voice.transcription.REGISTERED_BACKENDS`
with all built-in backends. Done at import time so that iterating the registry after
``import frontprompt.voice.backends`` gives the full set.

Example (sub-plan 06 e2e test injection pattern):

    from frontprompt.voice import transcription
    import frontprompt.voice.backends  # registers built-in backends

    fake = MyMockBackend()
    transcription.REGISTERED_BACKENDS.insert(0, fake)  # highest priority
    try:
        ...
    finally:
        transcription.REGISTERED_BACKENDS.remove(fake)
"""

from __future__ import annotations

from frontprompt.voice import transcription
from frontprompt.voice.backends.mlx_whisper import MlxWhisperBackend

# Register the mlx-whisper backend (probe_status() will return "unavailable" on
# non-Apple-Silicon — safe to register unconditionally, CLI/UI filters by status)
transcription.REGISTERED_BACKENDS.append(MlxWhisperBackend())

__all__ = ["MlxWhisperBackend"]
