"""Tests for the Chromium self-heal helper (``ensure_chromium``)."""

from __future__ import annotations

import anyio
import pytest

from frontprompt.browser import manager as _mgr
from frontprompt.browser.errors import BrowserLaunchError


def test_ensure_chromium_noop_when_present(monkeypatch: pytest.MonkeyPatch) -> None:
    """If chromium is already present, no install subprocess runs."""
    monkeypatch.setattr(_mgr, "_chromium_present", lambda: True)

    async def _fake_run_process(*_args: object, **_kwargs: object) -> object:
        raise AssertionError("run_process must not be called when chromium is present")

    monkeypatch.setattr(_mgr.anyio, "run_process", _fake_run_process)
    anyio.run(_mgr.ensure_chromium)


def test_ensure_chromium_installs_when_missing(monkeypatch: pytest.MonkeyPatch) -> None:
    """If chromium is missing, the playwright install subprocess is invoked once."""
    monkeypatch.setattr(_mgr, "_chromium_present", lambda: False)
    calls: list[list[str]] = []

    class _Result:
        returncode = 0

    async def _fake_run_process(command: list[str], **_kwargs: object) -> _Result:
        calls.append(command)
        return _Result()

    monkeypatch.setattr(_mgr.anyio, "run_process", _fake_run_process)
    anyio.run(_mgr.ensure_chromium)

    assert len(calls) == 1
    assert {"playwright", "install", "chromium"} <= set(calls[0])


def test_ensure_chromium_raises_on_install_failure(monkeypatch: pytest.MonkeyPatch) -> None:
    """A non-zero install exit surfaces as BrowserLaunchError."""
    monkeypatch.setattr(_mgr, "_chromium_present", lambda: False)

    class _Result:
        returncode = 1

    async def _fake_run_process(_command: list[str], **_kwargs: object) -> _Result:
        return _Result()

    monkeypatch.setattr(_mgr.anyio, "run_process", _fake_run_process)
    with pytest.raises(BrowserLaunchError):
        anyio.run(_mgr.ensure_chromium)
