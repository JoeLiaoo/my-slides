"""Preview or remove expired generated handoffs and Wiki snapshots."""
from __future__ import annotations

import argparse
import shutil
import time
from pathlib import Path

from ..command_output import emit
from ..project import ensure_project, project_root


def run(args: argparse.Namespace) -> int:
    root = project_root(args.project)
    base, _ = ensure_project(root)
    days = int(getattr(args, "older_than_days", 30))
    if days < 1:
        raise ValueError("--older-than-days 必须至少为 1。")
    cutoff = time.time() - days * 86400
    candidates: list[Path] = []
    def expired(path: Path) -> bool:
        try:
            if path.is_symlink() or path.stat(follow_symlinks=False).st_mtime >= cutoff:
                return False
            if path.is_dir():
                return all(expired(child) for child in path.iterdir())
            return path.is_file()
        except OSError:
            return False
    def add_old_handoffs(path: Path) -> None:
        if path.is_symlink():
            return
        if expired(path):
            candidates.append(path)
        elif path.is_dir():
            for child in sorted(path.iterdir()):
                add_old_handoffs(child)

    work = base / "work"
    if work.is_dir() and not work.is_symlink():
        for path in sorted(work.iterdir()):
            add_old_handoffs(path)
    for parent in (base / ".state" / "snapshots" / "wiki",):
        if parent.is_symlink() or not parent.is_dir():
            continue
        for path in sorted(parent.iterdir()):
            if path.is_symlink():
                continue
            try:
                if expired(path):
                    path.resolve(strict=True).relative_to(base.resolve())
                    candidates.append(path)
            except (OSError, ValueError):
                continue
    items = [{"path": path.relative_to(base).as_posix(), "type": "directory" if path.is_dir() else "file"} for path in candidates]
    deleted = []
    if getattr(args, "yes", False):
        for path in candidates:
            # A file may have been refreshed between listing and deletion.
            if not expired(path):
                continue
            try:
                path.resolve(strict=True).relative_to(base.resolve())
            except (OSError, ValueError):
                continue
            if path.is_dir():
                shutil.rmtree(path)
            else:
                path.unlink()
            deleted.append(path.relative_to(base).as_posix())
    data = {"project": str(root), "older_than_days": days, "preview": not getattr(args, "yes", False), "candidates": items, "deleted": deleted}
    if args.yes:
        human = "已清理：" + (", ".join(deleted) if deleted else "没有符合条件的内容")
    else:
        human = "仅预览，未删除：" + (", ".join(item["path"] for item in items) if items else "没有符合条件的内容") + "。确认后添加 --yes 执行。"
    emit(args, data, human)
    return 0
