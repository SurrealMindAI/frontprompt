# Phase-2: Two-BC nursery code, dormant since the architecture reset (see ARCHITECTURE.md).
"""ProgrammaticReferenceValidator — ACL-Interface für cross-BC-Identifier-Validierung.

Wenn eine ``Annotation`` optionale Programmatic-Executor-Identifier
(``page_session_id``, ``interaction_flow_step_id``) trägt, werden diese zur
Construction-Zeit gegen die Programmatic-BC validiert — durch diesen ACL-Adapter,
der **innerhalb** der Interactive-Surface-BC lebt.

Queries gehen über die ``IntentRequest``-Queue (Wire-Boundary) als typed
Read-Messages. Diese Klasse ist ein ``typing.Protocol`` — die Implementierung
kommt in einem späteren Bundle.

Dieses Modul liefert nur die Interface-Definition. Keine Konstruktions-Logik,
kein Queue-Zugriff, keine Netzwerk-Calls in diesem Sub-Plan.
"""

from __future__ import annotations

from typing import Protocol

from frontprompt.types import InteractionFlowStepId, PageSessionId


class ProgrammaticReferenceValidator(Protocol):
    """ACL-Adapter: validiert dehydrierte Programmatic-Executor-Identifier.

    Implementierungen nutzen die IntentRequest-Queue (Wire-Boundary) für
    read-only Queries gegen die Programmatic-Executor-BC:
    - ``QueryPageSessionExists(PageSessionId) -> bool``
    - ``QueryInteractionFlowStepValid(InteractionFlowStepId) -> bool``

    Raises:
        ValueError: wenn ein Identifier ungültig ist (Phantom-Referenz).
        TimeoutError: wenn die IntentRequest-Queue nicht antwortet (HTTP 503
            auf Caller-Seite — Idempotency-Key bleibt erhalten).
    """

    async def validate(
        self,
        page_session_id: PageSessionId | None,
        interaction_flow_step_id: InteractionFlowStepId | None,
    ) -> None:
        """Validiert die optionalen Cross-BC-Identifier einer Annotation.

        ``None``-Werte werden nicht validiert (sie sind semantisch "kein Kontext").
        Bei ``False``-Antwort auf eine Query: wirft ``ValueError``.
        Bei Timeout: wirft ``TimeoutError``.

        Gibt ``None`` zurück wenn alle nicht-None Identifier valide sind.
        """
        ...
