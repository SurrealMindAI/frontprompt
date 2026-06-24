"""Typed Exception Hierarchy für BrowserSessionManager.

Keine rohe playwright.Error oder OSError verlässt das ``browser/``-Modul —
alles wird in ``BrowserError``-Subklassen gewrapped. Callers können gegen die
Hierarchie codieren ohne Playwright-Internals importieren zu müssen.
"""

from __future__ import annotations


class BrowserError(Exception):
    """Base-Klasse für alle BrowserSessionManager-Fehler.

    ``cause`` ist die ursprüngliche Exception (für Audit-Log-Ketten).
    """

    def __init__(self, message: str, cause: BaseException | None = None) -> None:
        super().__init__(message)
        self.cause = cause


class BrowserLaunchError(BrowserError):
    """Chromium konnte nicht starten.

    Typische Ursachen:
        - playwright-Binary fehlt (``playwright install chromium`` vergessen)
        - OSError (disk-full, permission denied, port conflict)
        - Singleton-Lock (zwei Browser-Sessions mit demselben user_data_dir)
    """


class NavigationError(BrowserError):
    """``page.goto(url)`` ist fehlgeschlagen.

    Typische Ursachen:
        - URL nicht erreichbar (DNS, Netzwerk, unreachable file://)
        - Server-Timeout
        - Chromium-Crash während Navigation (selten)
    """


class BrowserNotReadyError(BrowserError):
    """Operation wurde aufgerufen bevor ``__aenter__`` ausgeführt war.

    Üblicher Bug-Pattern: ``mgr = BrowserSessionManager(); await mgr.navigate(...)``
    statt ``async with BrowserSessionManager() as mgr: await mgr.navigate(...)``.
    """


class PageEvaluationError(BrowserError):
    """``page.evaluate(expression)`` ist fehlgeschlagen.

    Typische Ursachen:
        - JavaScript-Syntax-Fehler im Expression
        - Reference-Error (undefined global)
        - Cross-Origin-Boundary (sehr selten in Main World)
        - Page wurde während evaluation navigated/closed
    """
