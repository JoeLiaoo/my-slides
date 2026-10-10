"""List and manage v2 content units."""

from __future__ import annotations

import argparse

from ..command_output import emit
from ..project import ensure_project, project_root, require_v2_project
from ..unit_management import add_unit, list_trash, move_unit, remove_plan, remove_unit, rename_unit, restore_unit
from ..units import list_units_status


def _context(args: argparse.Namespace):
    root = project_root(args.project)
    base, cfg = ensure_project(root)
    require_v2_project(base)
    return root, base, cfg, [str(item) for item in cfg.get("chapters", [])]


def _remove_human(plan: dict, *, executed: bool) -> str:
    lines = [f"删除影响预览：{plan['unit']['id']}（{plan['unit']['chapter']}）"]
    lines.append("将移入回收区的文件：" + ("、".join(plan["files"]) if plan["files"] else "无文件"))
    missing = [item["path"] for item in plan.get("artifacts", []) if not item["exists"]]
    if missing:
        lines.append("当前不存在、不会移动：" + "、".join(missing))
    for kind in ("report", "spec"):
        approval = plan["approvals"][kind]
        label = "当前有效" if approval["current"] else ("已有历史批准，当前已失效" if approval["has_record"] else "未批准")
        if approval["pending"]:
            label += "，有待确认申请"
        by = f"（审批人：{approval['approved_by']}）" if approval.get("approved_by") else ""
        lines.append(f"{kind}：{label}{by}")
    deps = plan["dependencies"]
    lines.append("本单元声明依赖：" + ("、".join(deps["declared"]) or "无"))
    lines.append("依赖此单元的单元：" + ("、".join(deps["dependent_units"]) or "无"))
    lines.append("链接到此单元的 Markdown：" + ("、".join(deps["markdown_references"]) or "无"))
    if plan["blockers"]:
        lines.append("无法删除：" + "；".join(plan["blockers"]))
    elif executed:
        lines.append(f"已移入回收区：{plan['trash_id']}")
        lines.append(f"恢复命令：{plan['restore_command']}")
        lines.append("请重新组装报告，并重建整套 Slides、重新检查。")
        lines.append("受影响输出：" + "；".join(plan.get("affected_outputs", [])))
    else:
        lines.append("当前仅为预览，没有更改文件。确认后添加 --yes 执行。")
        if plan["requires_user_consent"]:
            lines.append("此单元已有批准记录；Agent 必须先征得用户同意，再执行 --yes。")
    return "\n".join(lines)


def run(args: argparse.Namespace) -> int:
    root, base, cfg, chapters = _context(args)
    operation = args.units_command
    if operation == "list":
        data = list_units_status(base, chapters)
        human = f"格式：v2\n单元数：{len(data['units'])}\n缺失产物：{len(data['missing'])}\n孤立产物：{len(data.get('orphaned', []))}"
        for item in data["missing"]:
            human += f"\n- {item['id']} 缺少 {item['artifact']}（{item['path']}）"
        for item in data.get("orphaned", []):
            human += f"\n- 孤立产物：{item['path']}（清单中没有 {item['id']}）"
        emit(args, data, human, error=bool(data.get("missing") or data.get("orphaned")))
        return 1 if data.get("missing") or data.get("orphaned") else 0

    if operation == "add":
        data = add_unit(base, args.id, args.chapter, chapters, after=args.after, role=args.role)
        emit(args, data, f"已新增单元 {args.id}（{args.chapter}）；请填写报告、Spec 和 HTML 骨架。")
        return 0
    if operation == "remove":
        plan = remove_unit(base, args.id, chapters, project_root=root) if args.yes else remove_plan(base, args.id, chapters, project_root=root)
        data = dict(plan)
        data["executed"] = bool(args.yes)
        emit(args, data, _remove_human(plan, executed=args.yes), error=bool(plan.get("blocked")))
        return 1 if plan.get("blocked") else 0
    if operation == "move":
        data = move_unit(base, args.id, chapters, after=args.after, before=args.before, chapter=args.chapter)
        context = f"；报告需用户确认：{data['report_reconfirmation']}" if data.get("report_reconfirmation") else ""
        emit(args, data, f"已移动 {args.id}；请按需重新确认报告并重新组装报告，再重建整套 Slides 并重新检查{context}。")
        return 0
    if operation == "rename":
        data = rename_unit(base, args.old_id, args.new_id, chapters)
        emit(args, data, f"已将 {args.old_id} 重命名为 {args.new_id}；请重新组装报告，并重建整套 Slides、重新检查。")
        return 0
    if operation == "restore":
        data = restore_unit(base, args.trash_id, chapters)
        human = f"已恢复单元 {data['unit']['id']} 至原章节与位置。报告批准：{'有效' if data['approvals']['report'] else '需重新确认'}；Spec 批准：{'有效' if data['approvals']['spec'] else '需重新确认'}。"
        emit(args, data, human)
        return 0
    if operation == "trash" and args.trash_command == "list":
        entries = list_trash(base)
        data = {"trash": entries}
        human = "回收区为空。" if not entries else "可恢复的删除记录：\n" + "\n".join(
            f"- {item['trash_id']}：{item['unit'].get('id')}（{item['unit'].get('chapter')}）；恢复：{item['restore_command']}"
            for item in entries
        )
        emit(args, data, human)
        return 0
    raise ValueError(f"未知 units 操作：{operation}")
