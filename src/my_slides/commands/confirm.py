"""Interactive approval confirmation for one reviewed unit."""

from __future__ import annotations

import argparse
import getpass
import sys

from ..project import ensure_project, now, project_root, require_v2_project
from ..state import refresh_unit_currency
from ..unit_workflow import confirm_unit_approval, resolve_unit_selection
from ..units import unit_paths


def run(args: argparse.Namespace) -> int:
    if not sys.stdin.isatty() or not sys.stdout.isatty():
        raise ValueError("确认审批必须由用户在交互终端执行；不能通过管道、--json 或非交互脚本确认")
    root = project_root(args.project)
    base, cfg = ensure_project(root)
    require_v2_project(base)
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
        approved_account=getpass.getuser(), project_root=root,
    )
    print(f"已批准 {args.kind} / {unit.id}；审批人：{state[args.kind]['approved_by']}")
    return 0
