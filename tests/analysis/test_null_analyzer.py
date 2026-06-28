"""NullPageAnalyzer coverage tests.

NullPageAnalyzer is the null-object for boot paths without a live browser.
All async methods raise NotImplementedError; invalidate_snapshot is a no-op.
"""

from __future__ import annotations

import pytest

from frontprompt.analysis.analyzer import NullPageAnalyzer


@pytest.fixture
def null_analyzer() -> NullPageAnalyzer:
    return NullPageAnalyzer()


def test_invalidate_snapshot_is_noop(null_analyzer: NullPageAnalyzer) -> None:
    """invalidate_snapshot() is a no-op for the null object."""
    null_analyzer.invalidate_snapshot()  # must not raise


@pytest.mark.anyio
async def test_snapshot_raises_not_implemented(null_analyzer: NullPageAnalyzer) -> None:
    with pytest.raises(NotImplementedError):
        await null_analyzer.snapshot()


@pytest.mark.anyio
async def test_snapshot_fresh_raises_not_implemented(null_analyzer: NullPageAnalyzer) -> None:
    with pytest.raises(NotImplementedError):
        await null_analyzer.snapshot(fresh=True)


@pytest.mark.anyio
async def test_outline_raises_not_implemented(null_analyzer: NullPageAnalyzer) -> None:
    with pytest.raises(NotImplementedError):
        await null_analyzer.outline()


@pytest.mark.anyio
async def test_condensed_html_raises_not_implemented(null_analyzer: NullPageAnalyzer) -> None:
    with pytest.raises(NotImplementedError):
        await null_analyzer.condensed_html()


@pytest.mark.anyio
async def test_find_one_raises_not_implemented(null_analyzer: NullPageAnalyzer) -> None:
    with pytest.raises(NotImplementedError):
        await null_analyzer.find_one(query=None, comment="x")  # type: ignore[arg-type]


@pytest.mark.anyio
async def test_find_first_raises_not_implemented(null_analyzer: NullPageAnalyzer) -> None:
    with pytest.raises(NotImplementedError):
        await null_analyzer.find_first(query=None, comment="x")  # type: ignore[arg-type]


@pytest.mark.anyio
async def test_find_by_text_raises_not_implemented(null_analyzer: NullPageAnalyzer) -> None:
    with pytest.raises(NotImplementedError):
        await null_analyzer.find_by_text("text", None, None, "c", 5)


@pytest.mark.anyio
async def test_find_by_regex_raises_not_implemented(null_analyzer: NullPageAnalyzer) -> None:
    with pytest.raises(NotImplementedError):
        await null_analyzer.find_by_regex(".*", "text", None, "c", 5)
