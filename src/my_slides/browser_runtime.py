"""Playwright and Chromium availability and installation."""
from __future__ import annotations

import importlib.util
import subprocess
import sys
from pathlib import Path
from typing import Any


def browser_status() -> dict[str, Any]:
    installed = importlib.util.find_spec("playwright") is not None
    chromium = None
    if installed:
        try:
            from playwright.sync_api import sync_playwright
            with sync_playwright() as playwright:
                chromium = playwright.chromium.executable_path
        except Exception:
            chromium = None
    return {"playwright": installed, "chromium": chromium, "chromium_installed": bool(chromium and Path(chromium).exists())}


def install_browser() -> dict[str, Any]:
    status = browser_status()
    if not status["playwright"]:
        raise ValueError("Playwright 未安装；请使用 uv tool install --editable '.[browser]' 安装 browser extra")
    result = subprocess.run([sys.executable, "-m", "playwright", "install", "chromium"],
                            capture_output=True, text=True, encoding="utf-8", errors="replace")
    if result.returncode:
        raise ValueError("Chromium 安装失败：" + (result.stderr or result.stdout).strip())
    status = browser_status()
    if not status["chromium_installed"]:
        raise ValueError("Playwright 安装完成，但未找到 Chromium 可执行文件")
    return status
