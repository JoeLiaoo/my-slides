"""CLI entry point for ``my-slides export`` (issue #28 phase 4)."""

from __future__ import annotations

import argparse
from pathlib import Path

from ..command_output import emit
from ..delivery import export_delivery
from ..project import ensure_project, project_root, require_v2_project


def run(args: argparse.Namespace) -> int:
    root = project_root(args.project)
    base, cfg = ensure_project(root)
    require_v2_project(base)
    output_dir = Path(args.output).expanduser().resolve() if getattr(args, "output", None) else None
    record = export_delivery(base, cfg, project_root=root, output_dir=output_dir)
    lines = [
        f"已交付：{record['path']}",
        f"序号：v{record['sequence']}（{record['date']}）",
        f"包含单元：{len(record['units'])} 个",
    ]
    emit(args, record, "\n".join(lines))
    return 0
