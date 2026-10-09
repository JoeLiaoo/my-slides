"""Build and check selected slide units."""

from __future__ import annotations

import argparse
from pathlib import Path
from typing import Any

from ..command_output import emit
from ..project import ensure_project, project_root, require_v2_project
from ..unit_workflow import resolve_unit_selection


def run(args: argparse.Namespace) -> int:
    root = project_root(args.project)
    base, cfg = ensure_project(root)
    require_v2_project(base)
    selected = resolve_unit_selection(
        base, cfg,
        unit_ids=args.units, changed=args.changed, all_units=args.all_units,
    )
    selected_ids = [unit.id for unit in selected]
    plan: dict[str, Any] | None = None
    browser_result = None
    output: Path | None = None
    errors: list[str] = []
    if args.slides_command == "build":
        from ..assembly import build_units_deck

        output, errors, plan = build_units_deck(
            base, cfg,
            unit_ids=args.units, changed=args.changed, all_units=args.all_units,
            write=True,
        )
    else:
        from ..browser import check_units_on_deck

        output = base / "slides" / "index.html"
        check_result = check_units_on_deck(base, output, selected_ids, browser=bool(args.browser))
        errors = list(check_result["errors"])
        browser_result = check_result.get("browser")
        plan = {"selected_units": selected_ids, "measured": bool(args.browser)}
    data = {
        "valid": not errors,
        "output": str(output) if output else None,
        "browser": browser_result,
        "errors": errors,
        "plan": plan,
    }
    if errors:
        human = "检查未通过：\n" + "\n".join(f"- {error}" for error in errors)
    else:
        label = "合并完成" if args.slides_command == "build" else "检查通过"
        human = f"{label}：{output}"
    emit(args, data, human, error=bool(errors))
    return 1 if errors else 0
