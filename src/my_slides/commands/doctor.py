"""Inspect project layout and optional rendering dependencies."""

from __future__ import annotations

import argparse

from ..browser_runtime import browser_status
from ..command_output import emit
from ..project import V1_UNSUPPORTED_MESSAGE, ensure_project, find_slug_collisions, project_root
from ..rendering import renderer_status
from ..units import UnitsError, detect_format_version, load_units_manifest


def run(args: argparse.Namespace) -> int:
    root = project_root(args.project)
    base, cfg = ensure_project(root)
    format_version = detect_format_version(base)
    required = ["project.yaml", "wiki/README.md", "wiki/index.md", "wiki/log.md", "reports", "specs", "slides"]
    missing = [name for name in required if not (base / name).exists()]
    unit_errors: list[str] = []
    slug_errors = find_slug_collisions([str(item) for item in cfg.get("chapters", [])])
    if format_version == "v2":
        try:
            load_units_manifest(base, cfg.get("chapters", []))
        except UnitsError as exc:
            unit_errors.append(str(exc))
            missing.append("units.json（无效）")
    else:
        missing.append("units.json")
        unit_errors.append(V1_UNSUPPORTED_MESSAGE)
    renderer = renderer_status()
    browser = browser_status()
    ok = format_version == "v2" and not missing and not unit_errors and not slug_errors
    data = {
        "ok": ok,
        "workspace": str(base),
        "format_version": format_version,
        "deprecated": format_version == "v1",
        "missing": missing,
        "unit_errors": unit_errors,
        "slug_errors": slug_errors,
        "renderer": renderer,
        "browser": browser,
    }
    if format_version == "v1":
        data["deprecation_warning"] = V1_UNSUPPORTED_MESSAGE
        human = V1_UNSUPPORTED_MESSAGE
    else:
        human = "工作区结构完整。" if ok else "缺少：" + ", ".join(missing + unit_errors + slug_errors)
    emit(args, data, human, error=not ok)
    return 0 if ok else 1
