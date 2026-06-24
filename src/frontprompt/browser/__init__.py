"""Browser-Lifecycle für Phase 1 — headful Chromium via Playwright.

Owner: das interaktive UI-Tool (frontprompt show <url>). Lebt parallel zu
``frontprompt.scrapling`` — Scrapling bleibt für Phase 2+ Scraper-Workflows
(Stealth, CF-Bypass, AsyncFetcher). Phase 1 nutzt Playwright direkt, weil
Scrapling's Public API ein Scraper-Pattern ist (fetch → extract → close)
ohne page-keep-open-Semantik.

Design notes:
    - Scrapling-only-Substrate gilt für Scraper-Workflows, nicht für das
      interaktive UI-Tool.
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
