"""Summarize source and per-unit progress."""

from __future__ import annotations

import argparse

from ..command_output import emit
from ..project import V1_UNSUPPORTED_MESSAGE, ensure_project, project_root
from ..sources import scan_sources
from ..state import collect_units_status
from ..units import detect_format_version


def run(args: argparse.Namespace) -> int:
    root = project_root(args.project)
    base, cfg = ensure_project(root)
    if detect_format_version(base) != "v2":
        data = {
            "project": str(root),
            "format_version": "v1",
            "deprecated": True,
            "deprecation_warning": V1_UNSUPPORTED_MESSAGE,
            "pending_sources": [],
            "removed_sources": [],
            "approvals": {},
            "slides": {"supported": False, "built": False, "current": False},
        }
        emit(args, data, V1_UNSUPPORTED_MESSAGE, error=True)
        return 1
    _, pending, removed = scan_sources(root, base, cfg)
    unit_status = collect_units_status(
        base, selected=args.units, chapters=cfg.get("chapters", []), project_root=root,
    )
    approval_status = {
        kind: {
            "supported": True,
            "current": False,
            "message": f"使用 approve {kind} --unit / --changed / --all；状态见 --json 的 units 字段",
        }
        for kind in ("report", "spec")
    }
    slide_status = {
        "supported": True,
        "built": (base / "slides" / "index.html").exists(),
        "current": False,
        "message": "使用 slides build|check --unit / --changed / --all",
    }
    human = (
        f"项目：{root}\n格式：v2\n待整理资料：{len(pending)}\n已移除资料：{len(removed)}\n"
        f"选定单元：{len(unit_status['selected_units'])}\n"
        f"受影响：{len(unit_status['affected_units'])}\n"
        f"可复用：{len(unit_status['reused_units'])}\n"
        f"阻塞：{len(unit_status['blocked_units'])}\n"
        "提示：用 --json 查看各单元批准/构建/检查状态"
    )
    data = {
        "project": str(root),
        "format_version": "v2",
        "deprecated": False,
        "pending_sources": pending,
        "removed_sources": removed,
        "approvals": approval_status,
        "slides": slide_status,
        "selected_units": unit_status["selected_units"],
        "affected_units": unit_status["affected_units"],
        "reused_units": unit_status["reused_units"],
        "blocked_units": unit_status["blocked_units"],
        "reasons": unit_status["reasons"],
        "units": unit_status["units"],
        "dependency_graph": unit_status["dependency_graph"],
    }
    emit(args, data, human)
    return 0
