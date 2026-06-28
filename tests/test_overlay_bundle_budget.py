"""Performance budget for the injected overlay bundle.

The overlay is shipped as a single IIFE bundle injected into every page via
Playwright ``add_init_script``; its transfer + parse cost is paid on every
navigation. A size budget is the performance signal that actually fits an
injected widget (classic Lighthouse scores whole host pages, not a component),
so we guard the gzipped bundle size here. Raises early if a dependency or a
careless import balloons the bundle.

Budgets are set with ~12% headroom over the current size (gzip ≈ 573 KB,
raw ≈ 2.1 MB at the time of writing). Bumping them should be a conscious,
reviewed decision — not a silent ratchet.

Skipped if the bundle is not built. Build it with:
``cd frontend && FRONTPROMPT_BUILD_SESSION=1 bunx vite build`` (or
``uv run python -m frontprompt.build``).
"""

from __future__ import annotations

import gzip
from pathlib import Path

import pytest

_BUNDLE = Path(__file__).parents[1] / "frontend" / "dist" / "overlay.iife.js"

_GZIP_BUDGET_BYTES = 640 * 1024  # 640 KB gzipped
_RAW_BUDGET_BYTES = 2_400 * 1024  # 2.4 MB raw

pytestmark = pytest.mark.skipif(
    not _BUNDLE.is_file(),
    reason="overlay bundle not built — run `cd frontend && FRONTPROMPT_BUILD_SESSION=1 bunx vite build`.",
)


def test_overlay_bundle_within_gzip_budget() -> None:
    raw = _BUNDLE.read_bytes()
    gz = len(gzip.compress(raw, 9))
    assert gz <= _GZIP_BUDGET_BYTES, (
        f"overlay bundle gzip size {gz / 1024:.1f} KB exceeds budget "
        f"{_GZIP_BUDGET_BYTES / 1024:.0f} KB. Investigate a new/updated dependency "
        f"or an accidental heavy import before raising the budget."
    )


def test_overlay_bundle_within_raw_budget() -> None:
    raw = len(_BUNDLE.read_bytes())
    assert raw <= _RAW_BUDGET_BYTES, (
        f"overlay bundle raw size {raw / 1024:.1f} KB exceeds budget {_RAW_BUDGET_BYTES / 1024:.0f} KB."
    )
