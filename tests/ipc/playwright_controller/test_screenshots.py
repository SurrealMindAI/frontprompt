"""screenshots — shoot_element, shoot_page + 2MB cap + return_mode."""

from __future__ import annotations

import base64

import pytest
from playwright.async_api import async_playwright

from frontprompt.ipc.playwright_controller.screenshots import (
    ScreenshotTooLargeError,
    cleanup_screenshot_session,
    shoot_element,
    shoot_page,
)


@pytest.mark.anyio
async def test_shoot_element_returns_png_base64() -> None:
    async with async_playwright() as pw:
        browser = await pw.chromium.launch(headless=True)
        page = await browser.new_page()
        await page.set_content('<div style="width:100px;height:100px;background:red"></div>')
        handle = await page.query_selector("div")
        result = await shoot_element(handle, padding=0, return_mode="inline")
        assert result["format"] == "png"
        png = base64.b64decode(result["image_base64"])
        assert png[:8] == b"\x89PNG\r\n\x1a\n"  # PNG magic bytes
        assert result["width"] == 100
        assert result["height"] == 100
        await browser.close()


@pytest.mark.anyio
async def test_shoot_element_with_padding() -> None:
    async with async_playwright() as pw:
        browser = await pw.chromium.launch(headless=True)
        page = await browser.new_page()
        await page.set_content('<div style="width:50px;height:50px;background:blue"></div>')
        handle = await page.query_selector("div")
        result = await shoot_element(handle, padding=10, return_mode="inline")
        # padding adds 10 on each side → 70x70
        assert result["width"] == 70
        assert result["height"] == 70
        await browser.close()


@pytest.mark.anyio
async def test_shoot_element_rejects_oversized() -> None:
    """Element producing >2MB PNG raises ScreenshotTooLargeError."""
    async with async_playwright() as pw:
        browser = await pw.chromium.launch(headless=True)
        page = await browser.new_page(viewport={"width": 4000, "height": 4000})
        # Dense pixel-level noise using ImageData — each pixel random → incompressible PNG
        await page.set_content(
            "<canvas id='c' width='4000' height='4000'></canvas>"
            "<script>"
            "const ctx=document.getElementById('c').getContext('2d');"
            "const img=ctx.createImageData(4000,4000);"
            "const data=img.data;"
            "for(let i=0;i<data.length;i++){"
            "  data[i]=(Math.random()*256)|0;"
            "}"
            "ctx.putImageData(img,0,0);"
            "</script>"
        )
        handle = await page.query_selector("canvas")
        with pytest.raises(ScreenshotTooLargeError):
            await shoot_element(handle, padding=0, return_mode="inline")
        await browser.close()


@pytest.mark.anyio
async def test_shoot_page_viewport() -> None:
    async with async_playwright() as pw:
        browser = await pw.chromium.launch(headless=True)
        page = await browser.new_page(viewport={"width": 800, "height": 600})
        await page.set_content("<h1>X</h1>")
        result = await shoot_page(page, full_page=False, return_mode="inline")
        assert result["format"] == "png"
        assert result["width"] == 800
        assert result["height"] == 600
        await browser.close()


@pytest.mark.anyio
async def test_shoot_page_full() -> None:
    async with async_playwright() as pw:
        browser = await pw.chromium.launch(headless=True)
        page = await browser.new_page()
        await page.set_content('<div style="height:3000px;background:#eee"></div>')
        result = await shoot_page(page, full_page=True, return_mode="inline")
        assert result["height"] >= 3000
        await browser.close()


# ── return_mode tests ───────────────────────────────────────────────────────────


@pytest.mark.anyio
async def test_shoot_element_path_mode_writes_file() -> None:
    import pathlib

    async with async_playwright() as pw:
        browser = await pw.chromium.launch(headless=True)
        page = await browser.new_page()
        await page.set_content('<div style="width:50px;height:50px;background:green"></div>')
        handle = await page.query_selector("div")
        result = await shoot_element(handle, padding=0, return_mode="path", session_id="test-session")
        assert "path" in result
        assert "directive" in result
        assert "image_base64" not in result
        p = pathlib.Path(result["path"])
        assert p.exists()
        assert p.suffix == ".png"
        p.unlink()
        await browser.close()


@pytest.mark.anyio
async def test_shoot_element_inline_mode_returns_base64() -> None:
    async with async_playwright() as pw:
        browser = await pw.chromium.launch(headless=True)
        page = await browser.new_page()
        await page.set_content('<div style="width:50px;height:50px;background:blue"></div>')
        handle = await page.query_selector("div")
        result = await shoot_element(handle, padding=0, return_mode="inline", session_id="test-session")
        assert "image_base64" in result
        assert "path" not in result
        assert result["format"] == "png"
        # Verify PNG magic bytes
        png = base64.b64decode(result["image_base64"])
        assert png[:8] == b"\x89PNG\r\n\x1a\n"
        await browser.close()


@pytest.mark.anyio
async def test_shoot_page_path_mode_default() -> None:
    """Default return_mode is 'path'."""
    import pathlib

    async with async_playwright() as pw:
        browser = await pw.chromium.launch(headless=True)
        page = await browser.new_page(viewport={"width": 400, "height": 300})
        await page.set_content("<h1>x</h1>")
        result = await shoot_page(page, full_page=False)
        assert "path" in result
        assert "image_base64" not in result
        assert "directive" in result
        pathlib.Path(result["path"]).unlink(missing_ok=True)
        await browser.close()


def test_cleanup_screenshot_session_removes_dir() -> None:
    from frontprompt.ipc.playwright_controller.screenshots import _screenshot_dir

    session_id = "cleanup-test-xyz"
    d = _screenshot_dir(session_id)
    (d / "test.png").write_bytes(b"fake")
    assert d.exists()
    cleanup_screenshot_session(session_id)
    assert not d.exists()
