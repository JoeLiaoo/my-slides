"""Reject a pending report or Spec approval request.

The user mirrors the same gate as ``confirm``. Chat approval mode requires
``--via chat`` together with a matching ``--phrase`` and ``--user-reply``;
terminal approval mode requires an interactive TTY.
"""

from __future__ import annotations

import argparse
import getpass
import sys

from ..approval_review import reject_chat
from ..command_output import emit
from ..project import ensure_project, now, project_root, require_v2_project
from ..state import refresh_unit_currency
from ..unit_workflow import reject_unit_approval, resolve_unit_selection
from ..units import unit_paths


def run(args: argparse.Namespace) -> int:
    root = project_root(args.project)
    base, cfg = ensure_project(root)
    require_v2_project(base)
    reason = (getattr(args, "reason", "") or "").strip()
    if not reason:
        raise ValueError("驳回原因不能为空（请用 --reason 提供）")
    via = getattr(args, "via", None)
    chapter = getattr(args, "chapter", None)
    if via == "chat":
        decisions = reject_chat(
            base, cfg, args.kind,
            unit_id=getattr(args, "unit", None), chapter=chapter,
            phrase=getattr(args, "phrase", "") or "",
            user_reply=getattr(args, "user_reply", "") or "",
            reviewer=getattr(args, "reviewer", None),
            reason=reason,
            when=now(), project_root=root,
        )
        data = {
            "kind": args.kind,
            "decision": "rejected",
            "channel": "chat",
            "reason": reason,
            "units": decisions,
        }
        names = "、".join(item["id"] for item in decisions)
        emit(args, data, f"已通过对话驳回 {args.kind}：{names}；原因：{reason}")
        return 0
    if chapter:
        raise ValueError("整章驳回请使用 --via chat；交互终端一次只驳回一个小章节")
    if not sys.stdin.isatty() or not sys.stdout.isatty():
        raise ValueError("驳回审批必须由用户在交互终端执行；不能通过管道、--json 或非交互脚本驳回")
    if not getattr(args, "unit", None):
        raise ValueError("请指定 --unit")
    unit = resolve_unit_selection(base, cfg, unit_ids=[args.unit], changed=False, all_units=False)[0]
    state = refresh_unit_currency(base, unit, project_root=root)
    request = state[args.kind].get("pending_approval")
    if not state[args.kind]["pending_current"] or not isinstance(request, dict):
        raise ValueError(f"{unit.id}：没有有效的 {args.kind} 待审批申请，或申请后内容/依赖已变化；请重新提交审批")
    artifact = unit_paths(base, unit.id).report if args.kind == "report" else unit_paths(base, unit.id).spec
    digest = request["content_sha256"]
    print(f"待驳回：{args.kind} / {unit.id}\n文件：{artifact}\n内容 SHA-256：{digest}\n申请时间：{request['requested_at']}\n原因：{reason}")
    reviewer = input("审批人姓名：").strip()
    if not reviewer:
        raise ValueError("审批人姓名不能为空；未记录驳回")
    phrase = f"REJECT {args.kind.upper()} {unit.id} {digest[:12]}"
    if input(f"审阅文件后，输入 {phrase} 确认驳回：").strip() != phrase:
        raise ValueError("确认文字不匹配；未记录驳回")
    state = reject_unit_approval(
        base, unit, args.kind,
        when=now(), reason=reason,
        rejected_by=reviewer,
        rejected_account=getpass.getuser(),
        project_root=root, channel="terminal",
    )
    print(f"已驳回 {args.kind} / {unit.id}；原因：{reason}")
    return 0