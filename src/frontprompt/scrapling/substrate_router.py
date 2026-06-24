"""SubstrateRouter — Stub-Implementierung der Substrate-Wahl.

Volle Routing-Policy mit TOML + Hot-Reload ist explizit OUT-OF-SCOPE für
diese Iteration — siehe ARCHITECTURE.md.

Dieser Stub: explicit ``substrate_hint`` wins, kein Hint → DYNAMIC.

Naming-Konvention: ``dns_domain`` (nie bare ``domain``),
``substrate_hint`` (nie bare ``hint`` / ``mode``).
"""

from __future__ import annotations

from typing import Literal

SubstrateName = Literal["dynamic", "stealthy", "fetcher"]
"""Kanonische Substrat-Namen (drei Modi)."""

SubstrateHint = Literal["dynamic", "stealthy", "fetcher"]
"""Caller-Hint-Typ für ``ScraplingAdapter.navigate()`` und ``SubstrateRouter.choose()``.

Gleiche Werte-Menge wie ``SubstrateName`` — eigener Typ für Dokumentations-Klarheit:
Hint ist optionaler Caller-Input, Name ist Router-Output.
"""

# Modul-Level-Konstanten für typsichere Vergleiche ohne string-Literals
SUBSTRATE_DYNAMIC: SubstrateName = "dynamic"
SUBSTRATE_STEALTHY: SubstrateName = "stealthy"
SUBSTRATE_FETCHER: SubstrateName = "fetcher"

_DEFAULT_SUBSTRATE: SubstrateName = SUBSTRATE_DYNAMIC


class SubstrateRouter:
    """Stub-Router: explicit substrate_hint wins, default DYNAMIC.

    Die Signatur von ``choose()`` ist stabil — Downstream-Konsumenten und das MCP-tools-Bundle
    codieren gegen diese Klasse. Die TOML-basierte Routing-Policy kommt in
    einem späteren Bundle; sie wird ``choose()`` überschreiben ohne die
    Signatur zu ändern.
    """

    def choose(
        self,
        *,
        dns_domain: str,
        substrate_hint: SubstrateHint | None,
    ) -> SubstrateName:
        """Wähle das Scrapling-Substrate für diese Anfrage.

        Args:
            dns_domain: DNS-Hostname des Scraping-Targets.
                Z.B. ``"nowsecure.nl"``, ``"google.com"``. Im Stub nicht
                ausgewertet — zukünftige TOML-Policy nutzt ihn für Pattern-Matching.
            substrate_hint: Optionaler expliziter Substrate-Wunsch des Callers.
                ``None`` → Default (``SUBSTRATE_DYNAMIC``).

        Returns:
            SubstrateName des gewählten Substrats.
        """
        if substrate_hint is not None:
            return substrate_hint
        return _DEFAULT_SUBSTRATE
