"""AssertionEvaluator — unit tests using AsyncMock for Playwright Page.

Tests all assertion types and error handling. No real Chromium needed.
"""

from __future__ import annotations

from unittest.mock import AsyncMock, MagicMock, PropertyMock

import pytest

from frontprompt.state.state import AssertionEntry


def _make_entry(
    assertion_type: str,
    target: str = "h1",
    expected: str | None = None,
    comparator: str = "none",
    seq: int = 0,
    timestamp_ms: int = 1000,
    assertion_id: str = "assert-001",
    target_kind: str = "selector",
    description: str = "test assertion",
) -> AssertionEntry:
    return AssertionEntry(
        seq=seq,
        timestamp_ms=timestamp_ms,
        assertion_id=assertion_id,
        assertion_type=assertion_type,  # type: ignore[arg-type]
        target=target,
        target_kind=target_kind,  # type: ignore[arg-type]
        expected=expected,
        comparator=comparator,  # type: ignore[arg-type]
        description=description,
    )


# ---------------------------------------------------------------------------
# selector_exists
# ---------------------------------------------------------------------------


@pytest.mark.anyio
async def test_selector_exists_passes_when_element_present() -> None:
    """selector_exists → assertion_passed=True when element is found."""
    from frontprompt.ipc.playwright_controller.assertion_evaluator import AssertionEvaluator

    page = AsyncMock()
    page.query_selector = AsyncMock(return_value=MagicMock())  # element found

    entry = _make_entry(assertion_type="selector_exists", target="h1")
    result = await AssertionEvaluator().evaluate(page, entry)

    assert result["ok"] is True
    assert result["assertion_passed"] is True
    assert result["assertion_actual"] == "found"


@pytest.mark.anyio
async def test_selector_exists_fails_when_element_absent() -> None:
    """selector_exists → assertion_passed=False when element is not found."""
    from frontprompt.ipc.playwright_controller.assertion_evaluator import AssertionEvaluator

    page = AsyncMock()
    page.query_selector = AsyncMock(return_value=None)  # element absent

    entry = _make_entry(assertion_type="selector_exists", target="h2.missing")
    result = await AssertionEvaluator().evaluate(page, entry)

    assert result["ok"] is True
    assert result["assertion_passed"] is False
    assert result["assertion_actual"] == "not found"


# ---------------------------------------------------------------------------
# text_equals
# ---------------------------------------------------------------------------


@pytest.mark.anyio
async def test_text_equals_passes_when_text_matches() -> None:
    """text_equals → assertion_passed=True when element text equals expected."""
    from frontprompt.ipc.playwright_controller.assertion_evaluator import AssertionEvaluator

    mock_element = AsyncMock()
    mock_element.text_content = AsyncMock(return_value="Hello World")

    page = AsyncMock()
    page.query_selector = AsyncMock(return_value=mock_element)

    entry = _make_entry(
        assertion_type="text_equals",
        target="h1",
        expected="Hello World",
        comparator="equals",
    )
    result = await AssertionEvaluator().evaluate(page, entry)

    assert result["ok"] is True
    assert result["assertion_passed"] is True


@pytest.mark.anyio
async def test_text_equals_fails_when_text_mismatches() -> None:
    """text_equals → assertion_passed=False with assertion_actual containing actual text."""
    from frontprompt.ipc.playwright_controller.assertion_evaluator import AssertionEvaluator

    mock_element = AsyncMock()
    mock_element.text_content = AsyncMock(return_value="Actual Text")

    page = AsyncMock()
    page.query_selector = AsyncMock(return_value=mock_element)

    entry = _make_entry(
        assertion_type="text_equals",
        target="h1",
        expected="Expected Text",
        comparator="equals",
    )
    result = await AssertionEvaluator().evaluate(page, entry)

    assert result["ok"] is True
    assert result["assertion_passed"] is False
    assert result["assertion_actual"] == "Actual Text"


@pytest.mark.anyio
async def test_text_equals_fails_when_element_absent() -> None:
    """text_equals → assertion_passed=False (not crash) when element gone."""
    from frontprompt.ipc.playwright_controller.assertion_evaluator import AssertionEvaluator

    page = AsyncMock()
    page.query_selector = AsyncMock(return_value=None)

    entry = _make_entry(
        assertion_type="text_equals",
        target="h1",
        expected="Hello",
        comparator="equals",
    )
    result = await AssertionEvaluator().evaluate(page, entry)

    assert result["ok"] is True
    assert result["assertion_passed"] is False
    assert result["assertion_actual"] == "not found"


# ---------------------------------------------------------------------------
# text_contains
# ---------------------------------------------------------------------------


@pytest.mark.anyio
async def test_text_contains_passes_when_expected_is_substring() -> None:
    """text_contains → assertion_passed=True when expected is substring of element text."""
    from frontprompt.ipc.playwright_controller.assertion_evaluator import AssertionEvaluator

    mock_element = AsyncMock()
    mock_element.text_content = AsyncMock(return_value="Welcome to Hello World")

    page = AsyncMock()
    page.query_selector = AsyncMock(return_value=mock_element)

    entry = _make_entry(
        assertion_type="text_contains",
        target="h1",
        expected="Hello",
        comparator="contains",
    )
    result = await AssertionEvaluator().evaluate(page, entry)

    assert result["ok"] is True
    assert result["assertion_passed"] is True


@pytest.mark.anyio
async def test_text_contains_fails_when_expected_not_substring() -> None:
    """text_contains → assertion_passed=False when expected is not in element text."""
    from frontprompt.ipc.playwright_controller.assertion_evaluator import AssertionEvaluator

    mock_element = AsyncMock()
    mock_element.text_content = AsyncMock(return_value="Some other content")

    page = AsyncMock()
    page.query_selector = AsyncMock(return_value=mock_element)

    entry = _make_entry(
        assertion_type="text_contains",
        target="p",
        expected="Hello",
        comparator="contains",
    )
    result = await AssertionEvaluator().evaluate(page, entry)

    assert result["ok"] is True
    assert result["assertion_passed"] is False
    assert result["assertion_actual"] == "Some other content"


# ---------------------------------------------------------------------------
# visible
# ---------------------------------------------------------------------------


@pytest.mark.anyio
async def test_visible_passes_when_element_is_visible() -> None:
    """visible → assertion_passed=True when element is visible."""
    from frontprompt.ipc.playwright_controller.assertion_evaluator import AssertionEvaluator

    mock_element = AsyncMock()
    mock_element.is_visible = AsyncMock(return_value=True)

    page = AsyncMock()
    page.query_selector = AsyncMock(return_value=mock_element)

    entry = _make_entry(assertion_type="visible", target="button#submit")
    result = await AssertionEvaluator().evaluate(page, entry)

    assert result["ok"] is True
    assert result["assertion_passed"] is True


@pytest.mark.anyio
async def test_visible_fails_when_element_is_hidden() -> None:
    """visible → assertion_passed=False with assertion_actual='not visible' when hidden."""
    from frontprompt.ipc.playwright_controller.assertion_evaluator import AssertionEvaluator

    mock_element = AsyncMock()
    mock_element.is_visible = AsyncMock(return_value=False)

    page = AsyncMock()
    page.query_selector = AsyncMock(return_value=mock_element)

    entry = _make_entry(assertion_type="visible", target="div#hidden")
    result = await AssertionEvaluator().evaluate(page, entry)

    assert result["ok"] is True
    assert result["assertion_passed"] is False
    assert result["assertion_actual"] == "not visible"


# ---------------------------------------------------------------------------
# url_equals
# ---------------------------------------------------------------------------


@pytest.mark.anyio
async def test_url_equals_passes_when_url_matches() -> None:
    """url_equals → assertion_passed=True when current URL equals expected."""
    from frontprompt.ipc.playwright_controller.assertion_evaluator import AssertionEvaluator

    page = MagicMock()
    page.url = "https://example.com/page"
    page.query_selector = AsyncMock()

    entry = _make_entry(
        assertion_type="url_equals",
        target="",
        expected="https://example.com/page",
        target_kind="url",
        comparator="equals",
    )
    result = await AssertionEvaluator().evaluate(page, entry)

    assert result["ok"] is True
    assert result["assertion_passed"] is True


@pytest.mark.anyio
async def test_url_equals_fails_when_url_differs() -> None:
    """url_equals → assertion_passed=False with assertion_actual=current URL."""
    from frontprompt.ipc.playwright_controller.assertion_evaluator import AssertionEvaluator

    page = MagicMock()
    page.url = "https://example.com/other"

    entry = _make_entry(
        assertion_type="url_equals",
        target="",
        expected="https://example.com/page",
        target_kind="url",
        comparator="equals",
    )
    result = await AssertionEvaluator().evaluate(page, entry)

    assert result["ok"] is True
    assert result["assertion_passed"] is False
    assert result["assertion_actual"] == "https://example.com/other"


# ---------------------------------------------------------------------------
# Error handling — Playwright exception → ok=False
# ---------------------------------------------------------------------------


@pytest.mark.anyio
async def test_evaluate_returns_error_on_playwright_exception() -> None:
    """evaluate returns {ok: False, error: ...} if Playwright raises."""
    from playwright.async_api import Error as PlaywrightError

    from frontprompt.ipc.playwright_controller.assertion_evaluator import AssertionEvaluator

    page = AsyncMock()
    page.query_selector = AsyncMock(side_effect=PlaywrightError("browser crashed"))

    entry = _make_entry(assertion_type="selector_exists", target="h1")
    result = await AssertionEvaluator().evaluate(page, entry)

    assert result["ok"] is False
    assert "error" in result
    assert "browser crashed" in result["error"]
