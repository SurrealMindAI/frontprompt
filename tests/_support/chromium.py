"""Shared test helper: detect a usable Chromium binary.

Single source of truth for the ``skipif`` guard used by every real-Chromium
integration test under ``tests/browser/`` and ``tests/overlay/``. Playwright
caches its browsers in ``~/Library/Caches/ms-playwright/`` (macOS) or
``~/.cache/ms-playwright/`` (Linux); a system ``chromium`` on ``PATH`` is the
fallback. If neither is present, those tests skip instead of erroring.
"""

from __future__ import annotations

import shutil
from pathlib import Path


def chromium_binary_available() -> bool:
    """Return True if a Playwright (or system) Chromium binary is installed."""
    for cache in (
        Path.home() / "Library" / "Caches" / "ms-playwright",
        Path.home() / ".cache" / "ms-playwright",
    ):
        if cache.is_dir() and any(p.name.startswith("chromium-") for p in cache.iterdir()):
            return True
    return shutil.which("chromium") is not None


__all__ = ["chromium_binary_available"]
