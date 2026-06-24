"""Typed error hierarchy für die Bridge.

Keine raw playwright-Errors oder pydantic-ValidationErrors verlassen das
``bridge/``-Modul — alles wird in :class:`BridgeError`-Subklassen gewrapped.
"""

from __future__ import annotations


class BridgeError(Exception):
    """Base-Klasse für alle BridgeManager-Fehler.

    ``cause`` ist die ursprüngliche Exception (für Audit-Log-Ketten).
    """

    def __init__(self, message: str, cause: BaseException | None = None) -> None:
        super().__init__(message)
        self.cause = cause


class BridgeNotReadyError(BridgeError):
    """Operation wurde aufgerufen bevor BridgeManager im ``async with``-Scope war.

    Üblicher Bug-Pattern: ``bridge.send(...)`` ohne vorheriges ``__aenter__``.
    """


class OverlayValidationError(BridgeError):
    """Eine vom Overlay gesendete Message konnte nicht gegen ihr Pydantic-Schema
    validiert werden.

    Symptome:
        - Overlay sendet veraltetes Schema (codegen-drift, ts side nicht rebuilt)
        - Overlay sendet malformed JSON (bug im overlay-bridge.ts)
        - Discriminator-Field fehlt oder unbekannt
    """
