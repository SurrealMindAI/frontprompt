"""OverlayInjector — unit + integration tests.

Unit tests: mocked BrowserSessionManager (no Chromium needed).
Integration tests: real Chromium (headless=True). Skipped if no Playwright binary.
"""

from __future__ import annotations

import shutil
from pathlib import Path
from unittest.mock import AsyncMock, MagicMock

import pytest

from frontprompt.overlay import (
    OverlayAlreadyInstalledError,
    OverlayInjector,
    OverlayInstallationError,
    OverlayNotInstalledError,
    OverlayNotMountedError,
    load_overlay_bundle,
)

# ---- Unit tests (mocked browser) --------------------------------------------


def _mock_browser() -> MagicMock:
    """Build a MagicMock that looks like BrowserSessionManager."""
    browser = MagicMock()
    browser.add_init_script = AsyncMock(return_value=None)
    browser.evaluate = AsyncMock(return_value=False)
    return browser


def test_injector_id_is_uuid_string() -> None:
    inj = OverlayInjector(_mock_browser(), scaffold_script="// noop")
    assert isinstance(inj.injector_id, str)
    assert len(inj.injector_id) == 36


def test_two_injectors_have_distinct_ids() -> None:
    a = OverlayInjector(_mock_browser(), scaffold_script="// a")
    b = OverlayInjector(_mock_browser(), scaffold_script="// b")
    assert a.injector_id != b.injector_id


def test_initial_state_not_installed() -> None:
    inj = OverlayInjector(_mock_browser(), scaffold_script="// noop")
    assert inj.is_installed is False


def test_default_marker_and_ready_flag() -> None:
    inj = OverlayInjector(_mock_browser(), scaffold_script="// noop")
    assert inj.marker_id == "__frontprompt_overlay_host__"
    assert inj.ready_flag == "__frontprompt_overlay_ready__"


def test_custom_marker_and_ready_flag() -> None:
    inj = OverlayInjector(
        _mock_browser(),
        scaffold_script="// noop",
        marker_id="custom_marker",
        ready_flag="custom_ready",
    )
    assert inj.marker_id == "custom_marker"
    assert inj.ready_flag == "custom_ready"


@pytest.mark.anyio
async def test_install_calls_browser_add_init_script() -> None:
    browser = _mock_browser()
    inj = OverlayInjector(browser, scaffold_script="// my-scaffold")
    await inj.install_init_script()
    browser.add_init_script.assert_awaited_once_with("// my-scaffold")
    assert inj.is_installed is True


@pytest.mark.anyio
async def test_install_twice_raises_already_installed() -> None:
    inj = OverlayInjector(_mock_browser(), scaffold_script="// noop")
    await inj.install_init_script()
    with pytest.raises(OverlayAlreadyInstalledError):
        await inj.install_init_script()


@pytest.mark.anyio
async def test_install_browser_failure_wraps_in_installation_error() -> None:
    browser = _mock_browser()
    browser.add_init_script = AsyncMock(side_effect=RuntimeError("playwright rejected"))
    inj = OverlayInjector(browser, scaffold_script="// noop")
    with pytest.raises(OverlayInstallationError) as exc_info:
        await inj.install_init_script()
    assert exc_info.value.cause is not None
    assert isinstance(exc_info.value.cause, RuntimeError)
    assert inj.is_installed is False  # rolled back


@pytest.mark.anyio
async def test_verify_before_install_raises_not_installed() -> None:
    inj = OverlayInjector(_mock_browser(), scaffold_script="// noop")
    with pytest.raises(OverlayNotInstalledError):
        await inj.verify_mounted(timeout_seconds=0.1)


@pytest.mark.anyio
async def test_verify_polls_until_marker_appears() -> None:
    # First two polls: marker not there. Third poll: marker there. Then ready_flag check.
    browser = _mock_browser()
    browser.evaluate = AsyncMock(side_effect=[False, False, True, True])
    inj = OverlayInjector(browser, scaffold_script="// noop")
    await inj.install_init_script()
    await inj.verify_mounted(timeout_seconds=2.0, poll_interval_seconds=0.01)
    # 3 marker polls + 1 ready_flag check
    assert browser.evaluate.await_count == 4


@pytest.mark.anyio
async def test_verify_timeout_raises_not_mounted() -> None:
    # Marker never appears — every poll returns False
    browser = _mock_browser()
    browser.evaluate = AsyncMock(return_value=False)
    inj = OverlayInjector(browser, scaffold_script="// noop")
    await inj.install_init_script()
    with pytest.raises(OverlayNotMountedError) as exc_info:
        await inj.verify_mounted(timeout_seconds=0.3, poll_interval_seconds=0.05)
    assert "not im DOM" in str(exc_info.value) or "nicht im DOM" in str(exc_info.value)


@pytest.mark.anyio
async def test_verify_ready_flag_false_raises_installation_error() -> None:
    # Marker exists, but ready_flag is explicit False (scaffold threw)
    browser = _mock_browser()
    browser.evaluate = AsyncMock(side_effect=[True, False])  # marker=True, ready=False
    inj = OverlayInjector(browser, scaffold_script="// noop")
    await inj.install_init_script()
    with pytest.raises(OverlayInstallationError) as exc_info:
        await inj.verify_mounted(timeout_seconds=1.0)
    assert "Ready-Flag" in str(exc_info.value) or "scaffold" in str(exc_info.value).lower()


@pytest.mark.anyio
async def test_verify_uses_marker_id_in_expression() -> None:
    browser = _mock_browser()
    browser.evaluate = AsyncMock(side_effect=[True, True])
    inj = OverlayInjector(
        browser,
        scaffold_script="// noop",
        marker_id="my_custom_marker",
    )
    await inj.install_init_script()
    await inj.verify_mounted(timeout_seconds=1.0)
    # First eval call should contain the custom marker id
    first_call_expr = browser.evaluate.await_args_list[0].args[0]
    assert "my_custom_marker" in first_call_expr


def test_repr_indicates_install_state() -> None:
    inj = OverlayInjector(_mock_browser(), scaffold_script="// noop")
    assert "not-installed" in repr(inj)


# ---- Integration tests (real Chromium) --------------------------------------


def _chromium_binary_available() -> bool:
    candidates = [
        Path.home() / "Library" / "Caches" / "ms-playwright",
        Path.home() / ".cache" / "ms-playwright",
    ]
    for cache in candidates:
        if cache.is_dir() and any(p.name.startswith("chromium-") for p in cache.iterdir()):
            return True
    return shutil.which("chromium") is not None


@pytest.mark.anyio
@pytest.mark.skipif(
    not _chromium_binary_available(),
    reason="Playwright Chromium binary not installed.",
)
async def test_real_chromium_inject_and_verify_svelte_bundle() -> None:
    """End-to-end: launch Chromium, install built Svelte bundle, navigate, verify mount.

    Validiert die kritische Race-Sequenz: install vor navigate, dann verify
    pollt bis der DOM-Marker erscheint.
    """
    from frontprompt.browser import BrowserSessionManager

    bundle = load_overlay_bundle()

    async with BrowserSessionManager(headless=True) as mgr:
        inj = OverlayInjector(mgr, scaffold_script=bundle)
        await inj.install_init_script()
        await mgr.navigate("data:text/html,<html><body><h1>test</h1></body></html>")
        await inj.verify_mounted(timeout_seconds=10.0)

        marker_exists = await mgr.evaluate(
            "!!document.querySelector('#__frontprompt_overlay_host__[data-frontprompt=\"overlay\"]')"
        )
        assert marker_exists is True

        ready_value = await mgr.evaluate("window.__frontprompt_overlay_ready__")
        assert ready_value is True


@pytest.mark.anyio
@pytest.mark.skipif(
    not _chromium_binary_available(),
    reason="Playwright Chromium binary not installed.",
)
async def test_real_chromium_svelte_bundle_idempotent_on_navigate() -> None:
    """Validiert dass nach Navigation das Svelte-Bundle nicht doppelt mounted."""
    from frontprompt.browser import BrowserSessionManager

    bundle = load_overlay_bundle()

    async with BrowserSessionManager(headless=True) as mgr:
        inj = OverlayInjector(mgr, scaffold_script=bundle)
        await inj.install_init_script()

        await mgr.navigate("data:text/html,<html><body>page1</body></html>")
        await inj.verify_mounted(timeout_seconds=10.0)
        count_after_first = await mgr.evaluate("document.querySelectorAll('#__frontprompt_overlay_host__').length")
        assert count_after_first == 1

        await mgr.navigate("data:text/html,<html><body>page2</body></html>")
        await inj.verify_mounted(timeout_seconds=10.0)
        count_after_second = await mgr.evaluate("document.querySelectorAll('#__frontprompt_overlay_host__').length")
        assert count_after_second == 1, "bundle mounted twice after navigation"
