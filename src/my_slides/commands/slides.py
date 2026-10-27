"""Sync, check, and open the Design deck for selected units."""

from __future__ import annotations

import argparse

from ..command_output import emit
from ..design_deck import sync_deck
from ..design_workflow import check_deck, open_info
from ..project import ensure_project, project_root, require_v2_project
from ..unit_workflow import resolve_unit_selection


def run(args: argparse.Namespace) -> int:
    """build 同步 Design deck，check 走 Design 检查，open 给审阅链接。"""
    root = project_root(args.project)
    base, cfg = ensure_project(root)
    require_v2_project(base)
    if args.slides_command == "open":
        info = open_info(base)
        state = "宿主已在运行" if info["host_reachable"] else f"宿主未运行：在 {info['engine_root']} 执行 {info['host_command']}"
        emit(args, info, f"审阅链接：{info['url']}\n{state}")
        return 0
    if args.slides_command == "build":
        selected = resolve_unit_selection(base, cfg, unit_ids=args.units, changed=args.changed, all_units=args.all_units)
        data = sync_deck(base, cfg, selected)
        lines = [f"Design deck 已同步：{data['deck_dir']}", f"新建占位页：{', '.join(data['created_pages']) or '无'}"]
        if data["written_via"] == "host":
            lines.append("已通过运行中的 Design 宿主发布，打开的编辑器会自动刷新。")
        if data["units_without_pages"]:
            lines.append("仍无页面的单元：" + "、".join(data["units_without_pages"]))
        emit(args, {"valid": True, **data}, "\n".join(lines))
        return 0
    data = check_deck(base, cfg, strict=bool(args.strict), render=bool(args.browser))
    human = "检查通过" if data["valid"] else "检查未通过：\n" + "\n".join(f"- {error}" for error in data["errors"])
    emit(args, data, human, error=not data["valid"])
    return 0 if data["valid"] else 1
