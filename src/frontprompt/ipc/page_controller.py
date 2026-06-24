"""PageController protocol — bridge between IPC and the live Playwright Page.

The show-process owns a live Playwright ``Page`` object inside its
``BrowserSessionManager``. Write-side IPC requests (Schema 0.2.0+:
:class:`~frontprompt.ipc.protocol.NavigateRequest`, future click/type/screenshot)
need to reach that Page without dragging Playwright types into the
:mod:`frontprompt.ipc` package.

The protocol below is the seam. The show-command instantiates the concrete
:class:`PlaywrightPageController` (declared inline in :mod:`frontprompt.cli`)
and hands it to :func:`frontprompt.ipc.run_socket_server`. Tests can swap in
the :class:`NullPageController` (read-only sockets that reject write-side ops)
or a custom fake.

Sub-plan 03 (IPC Schema 0.4.0): adds 3 low-level escape-hatch methods —
``eval_js``, ``dom_patch``, ``pick_by_xpath_raw``.
"""

from __future__ import annotations

from typing import Any, Protocol

from frontprompt.state.state import Pick


class PageController(Protocol):
    """Abstracts the subset of Playwright Page actions exposed over IPC."""

    async def navigate(self, url: str) -> dict[str, Any]:
        """Navigate the live page to ``url``. Returns ``{navigated_to, title}``."""
        ...

    # ── Element-Readers (Schema 0.3.0) ─────────────────────────────────────

    async def get_text(self, picks: list[Pick]) -> list[dict[str, Any]]:
        """Read text + accessible name + role + enabled/visible/focused per pick."""
        ...

    async def get_html(self, picks: list[Pick], max_chars: int) -> list[dict[str, Any]]:
        """Read outerHTML (truncated to max_chars) per pick."""
        ...

    async def get_attributes(self, picks: list[Pick]) -> list[dict[str, Any]]:
        """Read all HTML attributes per pick."""
        ...

    async def get_state(self, picks: list[Pick]) -> list[dict[str, Any]]:
        """Read visibility/enabled/checked/focused/in_viewport per pick."""
        ...

    async def get_outline(self, picks: list[Pick], max_depth: int, max_nodes: int) -> list[dict[str, Any]]:
        """Read recursive child-tag outline (depth- and node-capped) per pick."""
        ...

    async def screenshot_element(self, picks: list[Pick], padding: int) -> list[dict[str, Any]]:
        """Element-cropped PNG per pick. Returns error dict on stale or too_large."""
        ...

    async def screenshot_page(self, full_page: bool) -> dict[str, Any]:
        """Full-viewport or full-page PNG. Returns error dict on too_large."""
        ...

    async def get_page_info(self) -> dict[str, Any]:
        """Read URL, title, viewport, scroll, readyState."""
        ...

    async def scroll_to(self, pick: Pick) -> dict[str, Any]:
        """Scroll single pick into viewport. Returns is_in_viewport + scroll pos."""
        ...

    async def query_selector_all(
        self,
        selector: str,
        parent_pick: Pick | None,
        limit: int,
    ) -> dict[str, Any]:
        """Query DOM for selector matches (scoped to parent Pick if given).

        Returns::

            {
                "total_matches": int,
                "elements": list[{
                    "selector": str,
                    "fingerprint": dict,
                    "rect": dict,
                    "text_snippet": str,
                    "url": str,
                    "timestamp_ms": int,
                    "color_index": int,
                }]
            }

        Takes a pre-resolved ``Pick`` object (not pick_id-string).
        The string-to-Pick resolution lives in socket_server.py dispatch.
        Stale parent (fingerprint mismatch) → raises StalePickError.
        Elements capped to limit.
        Used exclusively by ProgrammaticPickService.
        """
        ...

    # ── Low-level escape-hatch (Schema 0.4.0) ──────────────────────────────

    async def eval_js(
        self,
        expression: str,
        pick_id_arg: Pick | None,
        mutating: bool,
    ) -> dict[str, Any]:
        """Evaluate arbitrary JS expression in the live page context.

        If ``pick_id_arg`` is given, the live ElementHandle for that pick is
        bound as ``el`` in the JS expression.  ``mutating=True`` signals that
        the expression may modify the DOM — callers (PlaywrightPageController)
        must invalidate the PageAnalyzer snapshot after a successful call.

        Returns ``{result: Any, ok: bool}`` on success, ``{ok: false, error: str}``
        on JS exception.
        """
        ...

    async def dom_patch(
        self,
        pick: Pick,
        operations: list[dict[str, Any]],
    ) -> dict[str, Any]:
        """Apply a list of DOM patch operations to the element identified by ``pick``.

        Each operation dict has an ``op`` discriminator (set_attribute,
        remove_attribute, set_text, add_class, remove_class, remove_element).
        Always invalidates the PageAnalyzer snapshot after execution.

        Returns ``{ok: bool, results: list[{op: str, ok: bool, error?: str}]}``.
        Stale pick → ``{ok: false, error: "stale_pick"}``.
        """
        ...

    async def pick_by_xpath_raw(
        self,
        xpath: str,
        parent_pick: Pick | None,
        limit: int,
    ) -> dict[str, Any]:
        """Query DOM by XPath expression, scoped to parent_pick element if given.

        Returns the same element-descriptor dict shape as ``query_selector_all``
        (``{total_matches, elements}``), enabling ``ProgrammaticPickService`` to
        build Picks from the results.
        """
        ...

    async def evaluate_pick_dynamic_fields(
        self,
        pick: Pick,
        fields: list[str],
    ) -> dict[str, Any]:
        """Evaluate live dynamic fields for a single pick.

        Requested fields are a subset of:
          visible, enabled, focused, checked, in_viewport

        Returns a dict with the requested fields, or ``{'error': 'stale_pick'}``
        if the element handle can no longer be resolved.

        Used by Inspector.inspect_dynamic (analysis/inspect.py).
        """
        ...


class NullPageController:
    """No-op controller — every action raises NotImplementedError."""

    async def navigate(self, url: str) -> dict[str, Any]:
        raise NotImplementedError("NullPageController has no live browser; navigate is unavailable")

    async def get_text(self, picks: list[Pick]) -> list[dict[str, Any]]:
        raise NotImplementedError("NullPageController has no live browser")

    async def get_html(self, picks: list[Pick], max_chars: int) -> list[dict[str, Any]]:
        raise NotImplementedError("NullPageController has no live browser")

    async def get_attributes(self, picks: list[Pick]) -> list[dict[str, Any]]:
        raise NotImplementedError("NullPageController has no live browser")

    async def get_state(self, picks: list[Pick]) -> list[dict[str, Any]]:
        raise NotImplementedError("NullPageController has no live browser")

    async def get_outline(self, picks: list[Pick], max_depth: int, max_nodes: int) -> list[dict[str, Any]]:
        raise NotImplementedError("NullPageController has no live browser")

    async def screenshot_element(self, picks: list[Pick], padding: int) -> list[dict[str, Any]]:
        raise NotImplementedError("NullPageController has no live browser")

    async def screenshot_page(self, full_page: bool) -> dict[str, Any]:
        raise NotImplementedError("NullPageController has no live browser")

    async def get_page_info(self) -> dict[str, Any]:
        raise NotImplementedError("NullPageController has no live browser")

    async def scroll_to(self, pick: Pick) -> dict[str, Any]:
        raise NotImplementedError("NullPageController has no live browser")

    async def query_selector_all(
        self,
        selector: str,
        parent_pick: Pick | None,
        limit: int,
    ) -> dict[str, Any]:
        raise NotImplementedError("NullPageController has no live browser")

    async def eval_js(
        self,
        expression: str,
        pick_id_arg: Pick | None,
        mutating: bool,
    ) -> dict[str, Any]:
        raise NotImplementedError("NullPageController has no live browser")

    async def dom_patch(
        self,
        pick: Pick,
        operations: list[dict[str, Any]],
    ) -> dict[str, Any]:
        raise NotImplementedError("NullPageController has no live browser")

    async def pick_by_xpath_raw(
        self,
        xpath: str,
        parent_pick: Pick | None,
        limit: int,
    ) -> dict[str, Any]:
        raise NotImplementedError("NullPageController has no live browser")

    async def evaluate_pick_dynamic_fields(
        self,
        pick: Pick,
        fields: list[str],
    ) -> dict[str, Any]:
        raise NotImplementedError("NullPageController has no live browser")


__all__ = ["NullPageController", "PageController"]
