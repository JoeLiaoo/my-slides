"""Locate and drive the Design+Slides presentation engine (BaoCut slim).

The engine is an external Node project (``design-and-slides``) located through
``MY_SLIDES_DESIGN_ROOT``. my-slides never vendors or relicenses it; it only
shells out to its agent CLI with the project's own projects root.
"""
from __future__ import annotations

import json
import os
import shutil
import subprocess
from pathlib import Path
from typing import Any

DESIGN_ROOT_ENV = "MY_SLIDES_DESIGN_ROOT"
AGENT_ENTRY = Path("apps") / "local-host" / "src" / "main.ts"
SLIDES_COMPILER = Path("apps") / "slides-editor" / "dist" / "node" / "compiler.cjs"


def design_root() -> Path | None:
    value = os.environ.get(DESIGN_ROOT_ENV, "").strip()
    return Path(value).expanduser().resolve() if value else None


def design_status() -> dict[str, Any]:
    """Report whether the engine can run, without starting anything."""
    root = design_root()
    node = shutil.which("node")
    data: dict[str, Any] = {
        "env": DESIGN_ROOT_ENV,
        "root": str(root) if root else None,
        "node": node,
        "entry": bool(root and (root / AGENT_ENTRY).is_file()),
        "installed": bool(root and (root / "node_modules").is_dir()),
        "slides_editor_built": bool(root and (root / SLIDES_COMPILER).is_file()),
    }
    data["ready"] = bool(node and data["entry"] and data["installed"] and data["slides_editor_built"])
    return data


def require_engine() -> tuple[Path, str]:
    """Return (engine root, node executable) or explain how to set it up."""
    status = design_status()
    if not status["root"]:
        raise ValueError(f"未设置 {DESIGN_ROOT_ENV}：请指向 design-and-slides 目录（含 apps/local-host）")
    if not status["entry"]:
        raise ValueError(f"{DESIGN_ROOT_ENV} 不是 design-and-slides 目录：缺少 {AGENT_ENTRY.as_posix()}")
    if not status["node"]:
        raise ValueError("Design+Slides 需要 Node.js 22.23+ 或 24.22+；安装后重试")
    if not status["installed"]:
        raise ValueError(f"Design+Slides 依赖未安装：请在 {status['root']} 运行 npm install")
    if not status["slides_editor_built"]:
        raise ValueError(f"Slides 编辑器尚未构建：请在 {status['root']} 运行 npm run build")
    return Path(status["root"]), str(status["node"])


def run_agent(
    command: list[str],
    projects_root: Path,
    *,
    timeout: int = 600,
) -> tuple[int, dict[str, Any]]:
    """Run one Design agent CLI command and return (exit code, JSON payload)."""
    root, node = require_engine()
    argv = [node, "--experimental-strip-types", str(root / AGENT_ENTRY), "agent", *command,
            "--projects", str(projects_root), "--json"]
    result = subprocess.run(argv, cwd=root, capture_output=True, text=True,
                            encoding="utf-8", errors="replace", timeout=timeout)
    try:
        data = json.loads(result.stdout)
    except json.JSONDecodeError as exc:
        detail = (result.stderr or result.stdout).strip()[:500]
        raise ValueError(f"Design CLI 输出无法解析（退出码 {result.returncode}）：{detail}") from exc
    if not isinstance(data, dict):
        raise ValueError("Design CLI 输出不是 JSON 对象")
    return result.returncode, data
