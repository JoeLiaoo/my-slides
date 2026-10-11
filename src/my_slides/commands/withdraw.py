"""Agent cancels its own pending approval request."""

from __future__ import annotations

import argparse

from ..command_output import emit
from ..project import ensure_project, now, project_root, require_v2_project
from ..unit_workflow import resolve_unit_selection, withdraw_unit_approval


def run(args: argparse.Namespace) -> int:
    root = project_root(args.project)
    base, cfg = ensure_project(root)
    require_v2_project(base)
    units = resolve_unit_selection(
        base, cfg,
        unit_ids=[args.unit] if getattr(args, "unit", None) else None,
        changed=False, all_units=False, chapter=None,
    )
    cancelled = []
    errors: list[str] = []
    for unit in units:
        try:
            state = withdraw_unit_approval(
                base, unit, args.kind, when=now(), project_root=root,
            )
            cancelled.append({"id": unit.id, "decision": "withdrawn"})
        except ValueError as exc:
            errors.append(f"{unit.id}：{exc}")
    if errors and not cancelled:
        raise ValueError("；".join(errors))
    data = {
        "kind": args.kind,
        "decision": "withdrawn",
        "units": cancelled,
        "errors": errors,
    }
    names = "、".join(item["id"] for item in cancelled) or "（无）"
    human = f"已撤回 {args.kind} 待审申请：{names}"
    if errors:
        human += "\n注意：" + "；".join(errors)
    emit(args, data, human)
    return 0