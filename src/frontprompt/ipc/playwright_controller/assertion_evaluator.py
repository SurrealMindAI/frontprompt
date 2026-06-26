"""AssertionEvaluator — evaluates AssertionEntry checkpoints against the live DOM.

Dispatches on ``entry.assertion_type`` to private handler methods.
Always returns a dict — never raises. ``ok=False`` only on Playwright exceptions,
not on assertion failures.
"""

from __future__ import annotations

from typing import Any

import structlog
from playwright.async_api import Error as PlaywrightError, Page

from frontprompt.state.state import AssertionEntry

_LOG = structlog.get_logger(__name__)


class AssertionEvaluator:
    """Evaluates an AssertionEntry against the live Playwright page."""

    async def evaluate(self, page: Page, entry: AssertionEntry) -> dict[str, Any]:
        """Evaluate the assertion and return a result dict.

        Returns:
            ``{"ok": True, "assertion_passed": bool, "assertion_actual": str}``
            on successful evaluation (even if the assertion failed).
            ``{"ok": False, "error": str}`` if Playwright raised an exception.
        """
        _LOG.info(
            "assertion_evaluator.evaluate",
            assertion_type=entry.assertion_type,
            target=entry.target,
            assertion_id=entry.assertion_id,
        )
        try:
            return await self._dispatch(page, entry)
        except PlaywrightError as exc:
            _LOG.warning(
                "assertion_evaluator.evaluate.error",
                assertion_id=entry.assertion_id,
                error=str(exc),
            )
            return {"ok": False, "error": str(exc)}

    async def _dispatch(self, page: Page, entry: AssertionEntry) -> dict[str, Any]:
        """Dispatch to the appropriate assertion handler by type."""
        t = entry.assertion_type
        if t == "selector_exists":
            return await self._check_selector_exists(page, entry)
        elif t in ("text_equals", "text_contains"):
            return await self._check_text(page, entry)
        elif t == "visible":
            return await self._check_visible(page, entry)
        elif t == "url_equals":
            return self._check_url_equals(page, entry)
        else:
            # Unknown assertion type — fail gracefully
            return {
                "ok": False,
                "error": f"unknown assertion_type: {t!r}",
            }

    async def _check_selector_exists(self, page: Page, entry: AssertionEntry) -> dict[str, Any]:
        element = await page.query_selector(entry.target)
        if element is not None:
            return {"ok": True, "assertion_passed": True, "assertion_actual": "found"}
        return {"ok": True, "assertion_passed": False, "assertion_actual": "not found"}

    async def _check_text(self, page: Page, entry: AssertionEntry) -> dict[str, Any]:
        element = await page.query_selector(entry.target)
        if element is None:
            return {"ok": True, "assertion_passed": False, "assertion_actual": "not found"}

        actual = await element.text_content() or ""
        expected = entry.expected or ""

        if entry.assertion_type == "text_equals":
            passed = actual == expected
        else:
            # text_contains
            passed = expected in actual

        return {
            "ok": True,
            "assertion_passed": passed,
            "assertion_actual": actual if not passed else None,
        }

    async def _check_visible(self, page: Page, entry: AssertionEntry) -> dict[str, Any]:
        element = await page.query_selector(entry.target)
        if element is None:
            return {"ok": True, "assertion_passed": False, "assertion_actual": "not found"}

        is_visible = await element.is_visible()
        if is_visible:
            return {"ok": True, "assertion_passed": True, "assertion_actual": None}
        return {"ok": True, "assertion_passed": False, "assertion_actual": "not visible"}

    def _check_url_equals(self, page: Page, entry: AssertionEntry) -> dict[str, Any]:
        current_url: str = page.url  # type: ignore[attr-defined]
        expected = entry.expected or ""
        passed = current_url == expected
        return {
            "ok": True,
            "assertion_passed": passed,
            "assertion_actual": current_url if not passed else None,
        }


__all__ = ["AssertionEvaluator"]
