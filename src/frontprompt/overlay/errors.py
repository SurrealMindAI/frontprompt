"""Typed Exception Hierarchy für OverlayInjector.

Keine raw playwright-Errors verlassen das ``overlay/``-Modul. Caller können
gegen die Hierarchie codieren ohne Playwright-Internals zu kennen.
"""

from __future__ import annotations


class OverlayError(Exception):
    """Base-Klasse für alle OverlayInjector-Fehler.

    ``cause`` ist die ursprüngliche Exception (für Audit-Log-Ketten).
    """

    def __init__(self, message: str, cause: BaseException | None = None) -> None:
        super().__init__(message)
        self.cause = cause


class OverlayInstallationError(OverlayError):
    """``install_init_script()`` ist fehlgeschlagen oder das injectede Script
    hat während Mount eine Exception geworfen.

    Symptome:
        - Playwright hat die Script-Registrierung rejected
        - Das Script hat im Browser eine Exception geworfen — der Ready-Flag
          ist auf ``false`` gesetzt
    """


class OverlayNotInstalledError(OverlayError):
    """``verify_mounted()`` wurde aufgerufen bevor ``install_init_script()``.

    Üblicher Bug-Pattern: vergessen ``install`` zu callen, oder ``install``
    nach ``navigate`` aufgerufen (greift erst beim nächsten document_load).
    """


class OverlayAlreadyInstalledError(OverlayError):
    """``install_init_script()`` wurde doppelt aufgerufen.

    Bewusst hart, weil Doppel-Install entweder ein Logik-Bug ist oder zu
    multiplen Mount-Pfaden führt (die idempotente Marker-Check würde es zwar
    abfangen, aber wir wollen das nicht silently swallowen).
    """


class OverlayNotMountedError(OverlayError):
    """``verify_mounted()`` hat den DOM-Marker innerhalb des Timeouts nicht gefunden.

    Symptome:
        - Navigation noch nicht abgeschlossen (verify zu früh aufgerufen)
        - Script-Mount geblockt (CSP, Iframe-Sandboxing, document_start-Race)
        - Marker-ID-Mismatch (Scaffold setzt anderen Marker als verify checkt)
    """
