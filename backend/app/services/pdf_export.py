"""PDF 导出服务。

提供两条路径：
1. 首选：Playwright 无头 Chromium（标准方案，需 `python -m playwright install chromium`）。
2. 降级：系统已安装的 Google Chrome / Edge 的 headless `--print-to-pdf` 命令行生成
   （无需 Playwright driver，用 `@page` 样式保证 A4 排版）。

与 HTML 预览共用同一渲染器，保证版式一致。
"""
from __future__ import annotations

import asyncio
import platform
import subprocess
import sys
import tempfile
from pathlib import Path
from typing import Optional

from .. import config
from ..templates.templates_service import templates_service


class PdfExportError(RuntimeError):
    pass


def _find_system_browser() -> Optional[str]:
    """按常见位置查找系统 Chrome / Edge 可执行文件。"""
    if platform.system() == "Windows":
        candidates = [
            r"C:\Program Files\Google\Chrome\Application\chrome.exe",
            r"C:\Program Files (x86)\Google\Chrome\Application\chrome.exe",
            r"C:\Program Files\Microsoft\Edge\Application\msedge.exe",
            r"C:\Program Files (x86)\Microsoft\Edge\Application\msedge.exe",
            str(Path.home()
                / "AppData" / "Local" / "Google" / "Chrome" / "Application" / "chrome.exe"),
        ]
    else:
        candidates = [
            "/usr/bin/google-chrome",
            "/usr/bin/chromium",
            "/usr/bin/chromium-browser",
            "/usr/bin/microsoft-edge",
        ]
    for path in candidates:
        if Path(path).exists():
            return path
    return None


async def _render_with_playwright(html: str) -> bytes:
    """使用 Playwright 无头 Chromium 渲染。driver 不可用时抛异常，由上层降级。"""
    from playwright.async_api import async_playwright

    p = await async_playwright().start()
    try:
        browser = await p.chromium.launch(args=["--no-sandbox"])
        page = await browser.new_page()
        try:
            await page.set_content(html, wait_until="networkidle")
            return await page.pdf(format="A4", print_background=True)
        finally:
            await page.close()
    finally:
        await browser.close()
        await p.stop()


async def _render_with_system_browser(html: str) -> bytes:
    """使用系统 Chrome/Edge 的 headless --print-to-pdf 导出（同步子进程，包一层线程）。"""
    browser_path = _find_system_browser()
    if not browser_path:
        raise PdfExportError(
            "未找到可用的 Chromium。请运行 `python -m playwright install chromium` 安装，"
            "或安装 Google Chrome/Edge。"
        )

    def _run() -> bytes:
        with tempfile.TemporaryDirectory() as tmp:
            html_path = Path(tmp) / "resume.html"
            pdf_path = Path(tmp) / "resume.pdf"
            html_path.write_text(html, encoding="utf-8")
            cmd = [
                browser_path,
                "--headless",
                "--disable-gpu",
                "--no-sandbox",
                "--run-all-compositor-stages-before-draw",
                "--print-to-pdf-no-header",
                f"--print-to-pdf={pdf_path}",
                html_path.resolve().as_uri(),
            ]
            proc = subprocess.run(cmd, capture_output=True, timeout=120)
            if not pdf_path.exists() or pdf_path.stat().st_size == 0:
                msg = (proc.stderr or b"").decode("utf-8", "ignore")[:300]
                raise PdfExportError(f"Chrome 打印 PDF 失败：{msg}")
            return pdf_path.read_bytes()

    return await asyncio.to_thread(_run)


async def _render_html_to_pdf(html: str) -> bytes:
    """产出 A4 PDF：优先 Playwright，失败时降级到系统浏览器。"""
    try:
        try:
            return await _render_with_playwright(html)
        except ImportError:
            # Playwright 未安装，直接走系统浏览器
            return await _render_with_system_browser(html)
        except Exception as exc:
            # Playwright driver/浏览器启动失败（如未装 chromium），降级到系统浏览器
            try:
                return await _render_with_system_browser(html)
            except Exception:
                # 系统浏览器也不可用时，抛出 Playwright 原始错误以便用户定位
                raise PdfExportError(f"PDF 渲染失败：{exc}") from exc
    except PdfExportError:
        raise
    except Exception as exc:  # noqa: BLE001
        raise PdfExportError(f"PDF 渲染失败：{exc}") from exc


async def render_pdf(
    resume: dict, template_id: str = "modern-cn-001", layout: Optional[dict] = None
) -> bytes:
    """模板渲染 HTML 并产出 A4 PDF。"""
    html = templates_service.render_html(resume, template_id, layout)
    return await _render_html_to_pdf(html)


async def render_pdf_from_html(html: str) -> bytes:
    """直接把外部提供的完整 HTML 文档（如 AI 自定义排版）导出为 A4 PDF。"""
    if not html or "<" not in html:
        raise PdfExportError("HTML 内容为空或非法")
    return await _render_html_to_pdf(html)
