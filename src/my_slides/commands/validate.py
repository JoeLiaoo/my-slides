"""Validate Wiki pages or selected report and Spec units."""

from __future__ import annotations

import argparse

from ..command_output import emit
from ..project import ensure_project, project_root, require_v2_project
from ..unit_workflow import resolve_unit_selection, validate_unit_report, validate_unit_spec
from ..wiki import validate_wiki


def run(args: argparse.Namespace) -> int:
    root = project_root(args.project)
    base, cfg = ensure_project(root)
    require_v2_project(base)
    if args.kind == "wiki":
        errors = validate_wiki(base, cfg)
        data = {"valid": not errors, "errors": errors}
    else:
        units = resolve_unit_selection(
            base, cfg,
            unit_ids=args.units, changed=args.changed, all_units=args.all_units,
        )
        errors = []
        for unit in units:
            errors.extend(validate_unit_report(base, unit) if args.kind == "report" else validate_unit_spec(base, unit))
        data = {"valid": not errors, "errors": errors, "units": [unit.id for unit in units]}
    emit(
        args, data,
        "检查通过。" if not errors else "检查未通过：\n" + "\n".join(f"- {error}" for error in errors),
        error=bool(errors),
    )
    return 1 if errors else 0
