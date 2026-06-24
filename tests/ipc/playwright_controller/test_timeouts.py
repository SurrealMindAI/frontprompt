"""Tests for the shared page-op timeout helper.

A wedged page (JS thread pinned during bulk operations) makes ``page.evaluate``
never resolve. The helper bounds every page op so the show-child can recover and
the IPC dispatcher always returns instead of hanging the daemon forever.
"""

from __future__ import annotations

import anyio
import pytest
import structlog.testing

from frontprompt.ipc.playwright_controller.timeouts import (
    PAGE_OP_TIMEOUT_S,
    PageOpTimeoutError,
    with_page_op_timeout,
)


def test_default_page_op_timeout_is_finite() -> None:
    assert PAGE_OP_TIMEOUT_S > 0
    assert PAGE_OP_TIMEOUT_S != float("inf")


@pytest.mark.anyio
async def test_with_page_op_timeout_passes_through_result() -> None:
    async def _op() -> str:
        return "ok"

    result = await with_page_op_timeout("test_op", _op, timeout=1.0)
    assert result == "ok"


@pytest.mark.anyio
async def test_with_page_op_timeout_raises_typed_error_on_hang() -> None:
    async def _never() -> None:
        await anyio.sleep_forever()

    with pytest.raises(PageOpTimeoutError) as exc_info:
        await with_page_op_timeout("page_info", _never, timeout=0.05)

    # The op name is carried on the typed error so the dispatcher can surface it.
    assert exc_info.value.op == "page_info"
    assert "page_info" in str(exc_info.value)


@pytest.mark.anyio
async def test_with_page_op_timeout_logs_structured_event_on_timeout() -> None:
    async def _never() -> None:
        await anyio.sleep_forever()

    with structlog.testing.capture_logs() as logs:
        with pytest.raises(PageOpTimeoutError):
            await with_page_op_timeout("page_info", _never, timeout=0.05)

    timeout_events = [e for e in logs if "timeout" in str(e.get("event", ""))]
    assert timeout_events, f"expected a timeout log event, got: {logs}"
    assert any(e.get("op") == "page_info" for e in timeout_events)
