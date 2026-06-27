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


def register_builtin_backends() -> None:
    """Idempotently register all built-in backends into ``REGISTERED_BACKENDS``.

    Idempotent by ``backend_id`` so it is safe to call multiple times: importing
    this package runs it once, and callers (e.g. the daemon-start path
    :func:`frontprompt.show_session.build_initial_transcription_state`) may call it
    again defensively. The defensiveness matters because ``REGISTERED_BACKENDS`` is
    rebound to a fresh empty list whenever ``frontprompt.voice.transcription`` is
    reloaded (e.g. by tests) — the cached package import would otherwise never
    repopulate it. ``transcription.REGISTERED_BACKENDS`` is read through the module
    object so it always resolves the live list.

    probe_status() returns "unavailable" on non-Apple-Silicon, so registering the
    mlx-whisper backend unconditionally is safe — the CLI/UI filters by status.
    """
    existing_ids = {getattr(b, "backend_id", None) for b in transcription.REGISTERED_BACKENDS}
    if MlxWhisperBackend.backend_id not in existing_ids:
        transcription.REGISTERED_BACKENDS.append(MlxWhisperBackend())


# Register on import (the historic contract: `import frontprompt.voice.backends`
# populates the registry).
register_builtin_backends()

__all__ = ["MlxWhisperBackend", "register_builtin_backends"]
