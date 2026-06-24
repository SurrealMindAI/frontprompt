"""Backend-authoritative state für das Overlay.

State classification: zwei state-kategorien.
    - localState lebt im overlay (Svelte runes, ephemeral, page-scoped)
    - backendState lebt hier — Python ist single source of truth

Cross-origin navigation killt den browser-renderer-context komplett. Dieser
Python-process überlebt navigations und re-hydratet das overlay via
StateSnapshot bei jedem OverlayReady.

Single-writer: nur :class:`StateManager` mutiert state.
"""

from __future__ import annotations

from frontprompt.state.manager import StateManager
from frontprompt.state.persistence import StatePersistence
from frontprompt.state.state import (
    PANEL_IDS,
    ElementFingerprint,
    ElementRect,
    InspectorState,
    PanelId,
    PanelStateView,
    Pick,
    PickElement,
    StateSnapshot,
)

__all__ = [
    "PANEL_IDS",
    "ElementFingerprint",
    "ElementRect",
    "InspectorState",
    "PanelId",
    "PanelStateView",
    "Pick",
    "PickElement",
    "StateManager",
    "StatePersistence",
    "StateSnapshot",
]
