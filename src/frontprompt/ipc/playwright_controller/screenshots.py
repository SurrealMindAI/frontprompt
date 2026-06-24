"""Screenshot funcs — element + page with 2MB cap (PNG) + return_mode (path|inline)."""

from __future__ import annotations

import base64
import os
import shutil
from datetime import UTC, datetime
from pathlib import Path
from typing import Any, Literal

import structlog
from playwright.async_api import ElementHandle, FloatRect, Page

from frontprompt.overlay.injector import DEFAULT_MARKER_ID

_LOG = structlog.get_logger(__name__)

MAX_SCREENSHOT_BYTES: int = 2 * 1024 * 1024  # 2 MB


class ScreenshotTooLargeError(Exception):
    """Raised when a screenshot exceeds MAX_SCREENSHOT_BYTES."""

    def __init__(self, size_bytes: int) -> None:
        super().__init__(f"screenshot exceeds {MAX_SCREENSHOT_BYTES} bytes (was {size_bytes})")
        self.size_bytes = size_bytes


_HIDE_OVERLAY_JS = """(id) => {
    const el = document.getElementById(id);
    if (!el) return false;
    el.dataset._fpDisplay = el.style.display || '';
    el.style.display = 'none';
    return true;
}"""

_RESTORE_OVERLAY_JS = """(id) => {
    const el = document.getElementById(id);
    if (!el) return;
    el.style.display = el.dataset._fpDisplay ?? '';
    delete el.dataset._fpDisplay;
}"""


async def _hide_overlay(page: Page) -> bool:
    """Set display:none on the frontprompt overlay-host element if present.

    Idempotent: stashes the pre-hide display value in dataset so _restore_overlay
    can put it back exactly as it was. Returns True if the element existed.
    No-op (returns False) if the overlay was never injected in this page.
    """
    return bool(await page.evaluate(_HIDE_OVERLAY_JS, DEFAULT_MARKER_ID))


async def _restore_overlay(page: Page) -> None:
    """Restore display style of the overlay-host element to its pre-hide value."""
    await page.evaluate(_RESTORE_OVERLAY_JS, DEFAULT_MARKER_ID)


def _screenshot_dir(session_id: str) -> Path:
    """Return (and create) /tmp/frontprompt/<session_id>/."""
    d = Path("/tmp/frontprompt") / session_id
    d.mkdir(parents=True, exist_ok=True)
    return d


def cleanup_screenshot_session(session_id: str) -> None:
    """Remove /tmp/frontprompt/<session_id>/ on daemon shutdown."""
    target = Path("/tmp/frontprompt") / session_id
    shutil.rmtree(target, ignore_errors=True)


async def shoot_element(
    handle: ElementHandle,
    padding: int,
    return_mode: Literal["path", "inline"] = "path",
    session_id: str = "default",
) -> dict[str, Any]:
    """Element-cropped PNG (+ optional padding), capped at MAX_SCREENSHOT_BYTES."""
    _LOG.info("screenshot_element.start", return_mode=return_mode)
    box = await handle.bounding_box()
    if box is None:
        raise RuntimeError("element has no bounding box (display:none?)")

    clip: FloatRect = {
        "x": max(0.0, box["x"] - padding),
        "y": max(0.0, box["y"] - padding),
        "width": box["width"] + 2 * padding,
        "height": box["height"] + 2 * padding,
    }

    frame = await handle.owner_frame()
    if frame is None:
        raise RuntimeError("handle has no owning frame")
    page_obj: Page = frame.page

    await _hide_overlay(page_obj)
    try:
        png = await page_obj.screenshot(type="png", clip=clip)
    finally:
        await _restore_overlay(page_obj)
    if len(png) > MAX_SCREENSHOT_BYTES:
        raise ScreenshotTooLargeError(len(png))

    if return_mode == "inline":
        _LOG.info("screenshot_element.done", return_mode="inline", bytes=len(png))
        return {
            "image_base64": base64.b64encode(png).decode("ascii"),
            "format": "png",
            "width": int(clip["width"]),
            "height": int(clip["height"]),
        }
    # path mode (default)
    ts = datetime.now(UTC).strftime("%Y%m%dT%H%M%S%f")
    pid8 = str(os.getpid())[-8:].zfill(8)
    path = _screenshot_dir(session_id) / f"{ts}-elem-{pid8}.png"
    path.write_bytes(png)
    _LOG.info("screenshot_element.done", return_mode="path", bytes=len(png))
    return {
        "path": str(path),
        "width": int(clip["width"]),
        "height": int(clip["height"]),
        "bytes": len(png),
        "directive": "Read this PNG via the Read tool when you need pixel content.",
    }


async def shoot_page(
    page: Page,
    full_page: bool,
    return_mode: Literal["path", "inline"] = "path",
    session_id: str = "default",
) -> dict[str, Any]:
    _LOG.info("screenshot_page.start", full_page=full_page, return_mode=return_mode)
    await _hide_overlay(page)
    try:
        png = await page.screenshot(type="png", full_page=full_page)
    finally:
        await _restore_overlay(page)
    if len(png) > MAX_SCREENSHOT_BYTES:
        raise ScreenshotTooLargeError(len(png))

    dims: dict[str, Any] = await page.evaluate(
        """(full) => full
            ? ({ w: document.documentElement.scrollWidth,
                 h: document.documentElement.scrollHeight })
            : ({ w: window.innerWidth, h: window.innerHeight })""",
        full_page,
    )

    if return_mode == "inline":
        _LOG.info("screenshot_page.done", return_mode="inline", bytes=len(png))
        return {
            "image_base64": base64.b64encode(png).decode("ascii"),
            "format": "png",
            "width": int(dims["w"]),
            "height": int(dims["h"]),
        }
    # path mode (default)
    ts = datetime.now(UTC).strftime("%Y%m%dT%H%M%S%f")
    pid8 = str(os.getpid())[-8:].zfill(8)
    path = _screenshot_dir(session_id) / f"{ts}-page-{pid8}.png"
    path.write_bytes(png)
    _LOG.info("screenshot_page.done", return_mode="path", bytes=len(png))
    return {
        "path": str(path),
        "width": int(dims["w"]),
        "height": int(dims["h"]),
        "bytes": len(png),
        "directive": "Read this PNG via the Read tool when you need pixel content.",
    }


__all__ = [
    "MAX_SCREENSHOT_BYTES",
    "ScreenshotTooLargeError",
    "cleanup_screenshot_session",
    "shoot_element",
    "shoot_page",
]
