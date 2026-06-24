"""Overlay-Injection für Phase 1 — verwaltet Inject + Verify in der Main World.

Trennung von Concerns gegenüber :mod:`frontprompt.browser`:
    - :class:`frontprompt.browser.BrowserSessionManager` besitzt Browser-/Page-Lifecycle
    - :class:`frontprompt.overlay.OverlayInjector` besitzt Inject + Verify gegen
      eine schon-laufende ``BrowserSessionManager``-Instance

Design notes:
    - Overlay lebt in der Main World, via ``page.add_init_script`` injected
    - Naming — ``injector_id`` als Term
"""

from __future__ import annotations

from frontprompt.overlay.errors import (
    OverlayAlreadyInstalledError,
    OverlayError,
    OverlayInstallationError,
    OverlayNotInstalledError,
    OverlayNotMountedError,
)
from frontprompt.overlay.injector import OverlayInjector
from frontprompt.overlay.loader import (
    BuildManifest,
    load_build_manifest,
    load_overlay_bundle,
)

__all__ = [
    "BuildManifest",
    "OverlayAlreadyInstalledError",
    "OverlayError",
    "OverlayInjector",
    "OverlayInstallationError",
    "OverlayNotInstalledError",
    "OverlayNotMountedError",
    "load_build_manifest",
    "load_overlay_bundle",
]
