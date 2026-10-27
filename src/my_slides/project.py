"""Locate the thin project workspace."""

from __future__ import annotations

from pathlib import Path

APP_DIR = "my-slides"


def project_root(value: str | None, *, discover: bool = True) -> Path:
    if value:
        root = Path(value).expanduser().resolve()
    else:
        start = Path.cwd().resolve()
        root = start
        if discover:
            for candidate in (start, *start.parents):
                if (candidate / APP_DIR / "project.json").is_file():
                    root = candidate
                    break
    if not root.is_dir():
        raise ValueError(f"项目目录不存在：{root}")
    return root
