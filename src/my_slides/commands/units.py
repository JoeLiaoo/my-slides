"""List unit identities and required artifacts."""

from __future__ import annotations

import argparse

from ..command_output import emit
from ..project import ensure_project, project_root, require_v2_project
from ..units import list_units_status


def run(args: argparse.Namespace) -> int:
    root = project_root(args.project)
    base, cfg = ensure_project(root)
    require_v2_project(base)
    data = list_units_status(base, cfg.get("chapters", []))
    human = f"格式：v2\n单元数：{len(data['units'])}\n缺失产物：{len(data['missing'])}"
    if data["missing"]:
        human += "\n" + "\n".join(
            f"- {item['id']} 缺少 {item['artifact']}（{item['path']}）"
            for item in data["missing"]
        )
    emit(args, data, human, error=bool(data.get("missing")))
    return 1 if data.get("missing") else 0
