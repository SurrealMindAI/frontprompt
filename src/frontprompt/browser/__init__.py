"""Browser-Lifecycle für Phase 1 — headful Chromium via Playwright.

Owner: das interaktive UI-Tool (frontprompt show <url>). Phase 1 nutzt
Playwright direkt statt der scrapling-Library, weil Scrapling's Public API ein
Scraper-Pattern ist (fetch → extract → close) ohne page-keep-open-Semantik.
Die scrapling-Library wird nur noch für DOM-Analyse via
``analysis/_impl/scrapling_bridge.py`` genutzt.

Design notes:
    - Naming — ``browser_session_id`` als ID-Term, nicht bare ``id``.
"""

from __future__ import annotations

from frontprompt.browser.errors import (
    BrowserError,
    BrowserLaunchError,
    BrowserNotReadyError,
    NavigationError,
)
from frontprompt.browser.manager import BrowserSessionManager

__all__ = [
    "BrowserError",
    "BrowserLaunchError",
    "BrowserNotReadyError",
    "BrowserSessionManager",
    "NavigationError",
]
