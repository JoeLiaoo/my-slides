"""Confirm one pending section, or a whole chapter in chat."""

from __future__ import annotations

import argparse
import getpass
import sys

from ..approval_review import confirm_chat
from ..project import ensure_project, now, project_root, require_v2_project
from ..state import refresh_unit_currency
from ..unit_workflow import confirm_unit_approval, resolve_unit_selection
from ..units import unit_paths


def run(args: argparse.Namespace) -> int:
    root = project_root(args.project)
    base, cfg = ensure_project(root)
    require_v2_project(base)
    via = getattr(args, "via", None)
    chapter = getattr(args, "chapter", None)
    if via == "chat":
        confirmed = confirm_chat(
            base, cfg, args.kind,
            unit_id=args.unit, chapter=chapter,
            phrase=getattr(args, "phrase", "") or "",
            user_reply=getattr(args, "user_reply", "") or "",
            reviewer=getattr(args, "reviewer", None),
            when=now(), project_root=root,
        )
        names = "、".join(item["id"] for item in confirmed)
        print(f"已通过对话批准 {args.kind}：{names}；审批人：{confirmed[0]['approved_by']}")
        return 0
    if chapter:
        raise ValueError("整章确认请使用 --via chat；交互终端一次只确认一个小章节")
    if not sys.stdin.isatty() or not sys.stdout.isatty():
        raise ValueError("确认审批必须由用户在交互终端执行；不能通过管道、--json 或非交互脚本确认")
    if not getattr(args, "unit", None):
        raise ValueError("请指定 --unit")
    unit = resolve_unit_selection(base, cfg, unit_ids=[args.unit], changed=False, all_units=False)[0]
    state = refresh_unit_currency(base, unit, project_root=root)
    request = state[args.kind].get("pending_approval")
    if not state[args.kind]["pending_current"] or not isinstance(request, dict):
        raise ValueError(f"{unit.id}：没有有效的 {args.kind} 待审批申请，或申请后内容/依赖已变化；请重新提交审批")
    artifact = unit_paths(base, unit.id).report if args.kind == "report" else unit_paths(base, unit.id).spec
    digest = request["content_sha256"]
    context = request.get("review_context") or state[args.kind].get("reconfirmation_context")
    context_line = f"\n变更说明：{context}" if context else ""
    print(f"待审批：{args.kind} / {unit.id}\n文件：{artifact}\n内容 SHA-256：{digest}\n申请时间：{request['requested_at']}{context_line}")
    reviewer = input("审批人姓名：").strip()
    if not reviewer:
        raise ValueError("审批人姓名不能为空；未记录批准")
    phrase = f"APPROVE {args.kind.upper()} {unit.id} {digest[:12]}"
    if input(f"审阅文件后，输入 {phrase} 确认：").strip() != phrase:
        raise ValueError("确认文字不匹配；未记录批准")
    state = confirm_unit_approval(
        base, unit, args.kind, when=now(), approved_by=reviewer,
        approved_account=getpass.getuser(), project_root=root, channel="terminal",
    )
    print(f"已批准 {args.kind} / {unit.id}；审批人：{state[args.kind]['approved_by']}")
    return 0
