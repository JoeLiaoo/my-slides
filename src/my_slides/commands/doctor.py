"""Inspect project layout and the Design+Slides engine."""

from __future__ import annotations

import argparse

from ..command_output import emit
from ..design_engine import design_status, host_reachable
from ..project import V1_UNSUPPORTED_MESSAGE, ensure_project, find_slug_collisions, project_root
from ..units import UnitsError, detect_format_version, list_units_status, load_units_manifest

# 0.7.0 之前的 Spec / HTML 拼页产物；不再读取，保留原样供用户自行归档。
LEGACY_ARTIFACTS = ("specs", "slides")


def run(args: argparse.Namespace) -> int:
    root = project_root(args.project)
    base, cfg = ensure_project(root)
    format_version = detect_format_version(base)
    required = ["project.yaml", "wiki/README.md", "wiki/index.md", "wiki/log.md", "reports"]
    missing = [name for name in required if not (base / name).exists()]
    unit_errors: list[str] = []
    orphaned: list[dict[str, str]] = []
    slug_errors = find_slug_collisions([str(item) for item in cfg.get("chapters", [])])
    if format_version == "v2":
        try:
            load_units_manifest(base, cfg.get("chapters", []))
            orphaned = list_units_status(base, cfg.get("chapters", [])).get("orphaned", [])
        except UnitsError as exc:
            unit_errors.append(str(exc))
            missing.append("units.json（无效）")
    else:
        missing.append("units.json")
        unit_errors.append(V1_UNSUPPORTED_MESSAGE)
    design = {**design_status(), "host_reachable": host_reachable()}
    legacy = [name for name in LEGACY_ARTIFACTS if (base / name).exists()]
    ok = format_version == "v2" and not missing and not unit_errors and not slug_errors and not orphaned
    data = {
        "ok": ok,
        "workspace": str(base),
        "format_version": format_version,
        "deprecated": format_version == "v1",
        "missing": missing,
        "unit_errors": unit_errors,
        "orphaned": orphaned,
        "slug_errors": slug_errors,
        "design": design,
        "legacy_artifacts": legacy,
    }
    if format_version == "v1":
        data["deprecation_warning"] = V1_UNSUPPORTED_MESSAGE
        human = V1_UNSUPPORTED_MESSAGE
    else:
        details = missing + unit_errors + slug_errors + [f"孤立单元产物：{item['path']}" for item in orphaned]
        human = "工作区结构完整。" if ok else "需要处理：" + ", ".join(details)
        human += "\nDesign 引擎：" + ("就绪" if design["ready"] else f"未就绪（设置 {design['env']} 并在引擎目录 npm install、npm run build）")
        human += "，宿主" + ("已在运行" if design["host_reachable"] else "未运行")
        if legacy:
            human += "\n旧版产物不再使用（Spec / HTML 拼页）：" + "、".join(f"my-slides/{name}/" for name in legacy) + "；可自行归档后删除"
    emit(args, data, human, error=not ok)
    return 0 if ok else 1
