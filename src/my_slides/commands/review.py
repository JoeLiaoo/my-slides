"""Show a pending report or Spec in a form an agent can paste into chat."""

from __future__ import annotations

import argparse

from ..approval_review import review_packet
from ..command_output import emit
from ..project import ensure_project, project_root, require_v2_project


def _human(packet: dict) -> str:
    lines = [f"待审批：{packet['kind']} / {packet['target']}"]
    for unit in packet["units"]:
        title = f"{unit['chapter']} / {unit['title']}" if unit.get("title") else unit["chapter"]
        pages = f"\n页数：{unit['pages']}" if unit.get("pages") else ""
        lines.append(f"\n{title}（{unit['id']}）\n文件：{unit['path']}{pages}\n变更：{unit['changes']['summary']}")
        if unit["changes"].get("diff"):
            lines.append("具体差异：\n" + unit["changes"]["diff"])
        lines.append("待审正文：\n" + str(unit.get("content") or "").rstrip())
    lines.append(f"\n确认短语：{packet['phrase']}")
    lines.append("请在对话中明确回复是否批准。只有用户明确批准后，才能执行 confirm --via chat，并把原话传入 --user-reply。")
    return "\n".join(lines)


def run(args: argparse.Namespace) -> int:
    root = project_root(args.project)
    base, cfg = ensure_project(root)
    require_v2_project(base)
    packet = review_packet(
        base, cfg, args.kind,
        unit_id=getattr(args, "unit", None),
        chapter=getattr(args, "chapter", None),
        project_root=root,
    )
    emit(args, packet, _human(packet))
    return 0
