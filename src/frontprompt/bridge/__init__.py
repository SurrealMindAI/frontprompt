"""Bridge — typed bidirectional channel zwischen Python und dem injected Overlay.

Two-way bridge design (see ARCHITECTURE.md):

  - Overlay → Python via Playwright ``page.expose_function``
  - Python → Overlay via ``page.evaluate('window.__fp.dispatch(...)')``
  - Single ``window.__fp`` object als sichtbarer overlay-side API-surface
  - End-to-end-typed via :mod:`frontprompt.bridge.messages` (Pydantic SSoT)
  - Zod-Schemas auto-generiert via :mod:`frontprompt.bridge.codegen`

Verantwortlichkeiten:

  - :class:`frontprompt.bridge.BridgeManager` — Lifecycle, ``expose_function`` Setup, dispatch
  - :mod:`frontprompt.bridge.messages` — Pydantic Wire-Schemas (SSoT)
  - :mod:`frontprompt.bridge.codegen` — Codegen-Subprocess-Wrapper (Pydantic → Zod)
  - :mod:`frontprompt.bridge.errors` — Typed error hierarchy
"""

from __future__ import annotations

from frontprompt.bridge.errors import (
    BridgeError,
    BridgeNotReadyError,
    OverlayValidationError,
)
from frontprompt.bridge.manager import BridgeManager

__all__ = [
    "BridgeError",
    "BridgeManager",
    "BridgeNotReadyError",
    "OverlayValidationError",
]
