"""Assemble approved report units."""

from __future__ import annotations

import argparse

from ..command_output import emit
from ..project import ensure_project, project_root, require_v2_project
from ..unit_workflow import assemble_after_report_approvals


def run(args: argparse.Namespace) -> int:
    root = project_root(args.project)
    base, cfg = ensure_project(root)
    require_v2_project(base)
    _document, errors = assemble_after_report_approvals(base, chapters=cfg.get("chapters", []))
    emit(
        args,
        {"assembled": not errors, "path": str(base / "reports" / "report.md"), "errors": errors},
        "已组装 reports/report.md" if not errors else "组装失败：\n" + "\n".join(f"- {error}" for error in errors),
        error=bool(errors),
    )
    return 1 if errors else 0
