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
    selected_ids = set(unit_status["selected_units"])
    selected_rows = [row for row in unit_status["units"] if row["id"] in selected_ids]
    approval_status = {}
    for kind in ("report", "spec"):
        approved = [row["id"] for row in selected_rows if row[f"{kind}_current"]]
        pending_approval = [
            row["id"] for row in selected_rows
            if row[f"{kind}_pending"]
        ]
        unattributed = [
            row["id"] for row in selected_rows
            if row[f"{kind}_unattributed"]
        ]
        needs_review = [
            row["id"] for row in selected_rows
            if not row[f"{kind}_current"] and not row[f"{kind}_pending"]
        ]
        approval_status[kind] = {
            "supported": True,
            "current": bool(selected_rows) and len(approved) == len(selected_rows),
            "approved_units": approved,
            "pending_units": pending_approval,
            "unattributed_units": unattributed,
            "needs_review_units": needs_review,
            "approved_by": {
                row["id"]: {
                    "name": row[f"{kind}_approved_by"],
                    "account": row[f"{kind}_approved_account"],
                    "at": row[f"{kind}_approved_at"],
                }
                for row in selected_rows
                if row[f"{kind}_current"] and row[f"{kind}_approved_by"]
            },
            "message": f"按选定单元汇总；用 status --unit <id> 查看单元，approve {kind} --unit <id> 提交审批申请",
        }
    slide_status = {
        "supported": True,
        "built": (base / "slides" / "index.html").exists(),
        "current": bool(selected_rows) and all(row["html_current"] for row in selected_rows),
        "checked_current": bool(selected_rows) and all(row["check_current"] for row in selected_rows),
        "unchecked_units": [row["id"] for row in selected_rows if not row["check_current"]],
        "message": "current 表示所选单元的 HTML 构建仍有效；checked_current 表示浏览器检查仍有效",
    }
    human = (
        f"项目：{root}\n格式：v2\n待整理资料：{len(pending)}\n已移除资料：{len(removed)}\n"
        f"选定单元：{len(unit_status['selected_units'])}\n"
        f"受影响：{len(unit_status['affected_units'])}\n"
        f"可复用：{len(unit_status['reused_units'])}\n"
        f"阻塞：{len(unit_status['blocked_units'])}\n"
        f"待人工确认：报告 {len(approval_status['report']['pending_units'])}，Spec {len(approval_status['spec']['pending_units'])}\n"
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
