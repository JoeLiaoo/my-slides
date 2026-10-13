"""CLI entry point for ``my-slides chapters …`` (issue #28 phase 4)."""

from __future__ import annotations

import argparse

from ..chapter_management import (
    add_chapter,
    list_chapters,
    move_chapter,
    remove_chapter,
    rename_chapter,
)
from ..command_output import emit
from ..project import ensure_project, project_root, require_v2_project
from ..units import load_units_manifest


def _context(args: argparse.Namespace) -> tuple:
    root = project_root(args.project)
    base, cfg = ensure_project(root)
    require_v2_project(base)
    chapters = [str(item) for item in cfg.get("chapters", [])]
    return root, base, cfg, chapters


def _human_chapter_list(data: dict) -> str:
    lines = [f"报告章节：{data['count']}"]
    for chapter in data["chapters"]:
        ids = "、".join(chapter["unit_ids"]) or "（暂无小章节）"
        lines.append(f"- {chapter['order']:>2}. {chapter['name']}（{chapter['unit_count']} 个小章节：{ids}）")
    if data.get("orphan_chapters"):
        lines.append("异常：units.json 引用了 project.yaml 之外的章节："
                     + "、".join(data["orphan_chapters"]))
    return "\n".join(lines)


def run(args: argparse.Namespace) -> int:
    root, base, cfg, chapters = _context(args)
    operation = args.chapters_command

    if operation == "list":
        units, manifest_errors = load_units_manifest(base, chapters=None)
        if manifest_errors:
            raise ValueError("；".join(manifest_errors))
        data = list_chapters(base, chapters, units)
        emit(args, data, _human_chapter_list(data), error=bool(data.get("orphan_chapters")))
        return 1 if data.get("orphan_chapters") else 0

    if operation == "add":
        data = add_chapter(root, args.name, after=args.after)
        label = f"；位置：{data['position']}" if data.get("position") is not None else ""
        wiki_note = "；Wiki 索引已同步" if data.get("wiki_updated") else "；Wiki 索引未变动（不存在 index.md）"
        emit(args, data, f"已新增章节「{data['chapter']}」{label}{wiki_note}。")
        return 0

    if operation == "rename":
        data = rename_chapter(root, args.old, args.new)
        emit(args, data, f"已将章节「{data['from']}」改名为「{data['to']}」；共 {len(data['affected_units'])} 个小章节同步更新；{data['reason']}")
        return 0

    if operation == "remove":
        data = remove_chapter(root, args.name)
        emit(args, data, f"已删除章节「{data['chapter']}」；剩余 {len(data['chapters'])} 个章节。")
        return 0

    if operation == "move":
        data = move_chapter(root, args.name, after=args.after, before=args.before)
        emit(args, data, f"已将章节「{data['chapter']}」移动到第 {data['position']} 位；Wiki 索引已同步。")
        return 0

    raise ValueError(f"未知 chapters 操作：{operation}")
