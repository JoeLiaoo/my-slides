"""Submit report or Spec units for an explicit human review."""

from __future__ import annotations

import argparse
import shlex

from ..command_output import emit
from ..project import ensure_project, now, project_root, require_v2_project
from ..unit_workflow import request_unit_approval, resolve_unit_selection


def run(args: argparse.Namespace) -> int:
    root = project_root(args.project)
    base, cfg = ensure_project(root)
    require_v2_project(base)
    units = resolve_unit_selection(
        base, cfg,
        unit_ids=args.units, changed=args.changed, all_units=args.all_units,
    )
    requested = []
    stamp = now()
    for unit in units:
        request = request_unit_approval(base, unit, args.kind, when=stamp, project_root=root)
        requested.append({
            "id": unit.id,
            "sha256": request["content_sha256"],
            "requested_at": request["requested_at"],
            "confirm_command": f"my-slides confirm {args.kind} --unit {unit.id} --project {shlex.quote(str(root))}",
        })
    data = {
        "requested": bool(requested),
        "approved": False,
        "kind": args.kind,
        "units": requested,
        "requires_human_confirmation": bool(requested),
    }
    human = f"已提交 {len(requested)} 个 {args.kind} 单元供用户审阅；尚未批准。"
    if requested:
        human += "\n请用户本人在终端逐项运行：\n" + "\n".join(item["confirm_command"] for item in requested)
    emit(args, data, human)
    return 0
