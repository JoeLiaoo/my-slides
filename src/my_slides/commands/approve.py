"""Approve selected report or Spec units."""

from __future__ import annotations

import argparse

from ..command_output import emit
from ..project import ensure_project, now, project_root, require_v2_project
from ..unit_workflow import (
    approve_unit_report, approve_unit_spec, assemble_after_report_approvals,
    resolve_unit_selection,
)


def run(args: argparse.Namespace) -> int:
    root = project_root(args.project)
    base, cfg = ensure_project(root)
    require_v2_project(base)
    units = resolve_unit_selection(
        base, cfg,
        unit_ids=args.units, changed=args.changed, all_units=args.all_units,
    )
    approved = []
    stamp = now()
    for unit in units:
        if args.kind == "report":
            state = approve_unit_report(base, unit, when=stamp, project_root=root)
        else:
            state = approve_unit_spec(base, unit, when=stamp, project_root=root)
        approved.append({"id": unit.id, "sha256": state[args.kind]["approved_sha256"]})
    assembled = None
    assemble_errors: list[str] = []
    if args.kind == "report":
        assembled, assemble_errors = assemble_after_report_approvals(base)
    emit(
        args,
        {
            "approved": True,
            "kind": args.kind,
            "units": approved,
            "assembled_report": assembled is not None and not assemble_errors,
            "assemble_errors": assemble_errors,
        },
        f"已批准 {len(approved)} 个单元的 {args.kind}"
        + ("" if not assemble_errors else "；组装报告失败：" + "；".join(assemble_errors)),
        error=bool(assemble_errors),
    )
    return 1 if assemble_errors else 0
