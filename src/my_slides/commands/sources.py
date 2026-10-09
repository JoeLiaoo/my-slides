"""Scan and acknowledge project Markdown sources."""

from __future__ import annotations

import argparse

from ..command_output import emit
from ..project import ensure_project, project_root, require_v2_project
from ..sources import mark_ingested, scan_sources
from ..wiki import validate_wiki


def run(args: argparse.Namespace) -> int:
    root = project_root(args.project)
    base, cfg = ensure_project(root)
    require_v2_project(base)
    state, pending, removed = scan_sources(root, base, cfg)
    if args.sources_command == "mark-ingested":
        selected = args.paths or (pending + removed)
        unknown = sorted(set(selected) - set(state["files"]))
        if unknown:
            raise ValueError("资料路径未出现在扫描结果中：" + "、".join(unknown))
        wiki_errors = validate_wiki(base, cfg)
        if wiki_errors:
            raise ValueError("Wiki 链接检查未通过，暂不能确认整理完成：" + "；".join(wiki_errors))
        count = mark_ingested(base, selected)
        data = {"marked_ingested": count, "paths": selected}
        human = f"已确认整理 {count} 个 Markdown 文件。"
    else:
        data = {"scanned_at": state["scanned_at"], "pending": pending, "removed": removed}
        human = f"待整理或已变化：{len(pending)} 个；已删除或移出范围：{len(removed)} 个。\n" + "\n".join(pending + removed)
    emit(args, data, human)
    return 0
