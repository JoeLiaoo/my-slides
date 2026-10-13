"""Summarize source and per-unit progress."""

from __future__ import annotations

import argparse
from typing import Any

from ..command_output import emit
from ..delivery import last_delivery, units_changed_since
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
    approval_status: dict[str, Any] = {}
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
        rejected = [
            row["id"] for row in selected_rows
            if row.get(f"{kind}_latest_decision") == "rejected"
            and not row[f"{kind}_current"]
            and not row[f"{kind}_pending"]
        ]
        needs_review = [
            row["id"] for row in selected_rows
            if not row[f"{kind}_current"] and not row[f"{kind}_pending"]
            and row.get(f"{kind}_latest_decision") != "rejected"
        ]
        approval_status[kind] = {
            "supported": True,
            "current": bool(selected_rows) and len(approved) == len(selected_rows),
            "approved_units": approved,
            "pending_units": pending_approval,
            "unattributed_units": unattributed,
            "rejected_units": rejected,
            "rejections": {
                row["id"]: row.get(f"{kind}_latest_rejection")
                    for row in selected_rows
                    if row.get(f"{kind}_latest_decision") == "rejected"
            },
            "needs_review_units": needs_review,
            "approved_by": {
                row["id"]: {
                    "name": row[f"{kind}_approved_by"],
                    "account": row[f"{kind}_approved_account"],
                    "at": row[f"{kind}_approved_at"],
                    "channel": row.get(f"{kind}_approval_channel"),
                    "user_reply": row.get(f"{kind}_user_reply"),
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
    last = last_delivery(base)
    if last is None:
        delivery_summary: dict[str, Any] = {"has_delivery": False}
    else:
        changed = units_changed_since(base, root)
        delivery_summary = {
            "has_delivery": True,
            "last_delivery": last,
            "changed_since": changed["changed_units"],
            "unchanged_since": changed["unchanged_units"],
            "deck_changed": changed["deck_changed"],
        }
    delivery_line = (
        f"v{last['sequence']}（{last['date']}）"
        if last else "暂无"
    )
    human = (
        f"项目：{root}\n格式：v2\n待整理资料：{len(pending)}\n已移除资料：{len(removed)}\n"
        f"选定单元：{len(unit_status['selected_units'])}\n"
        f"受影响：{len(unit_status['affected_units'])}\n"
        f"可复用：{len(unit_status['reused_units'])}\n"
        f"阻塞：{len(unit_status['blocked_units'])}\n"
        f"待人工确认：报告 {len(approval_status['report']['pending_units'])}，Spec {len(approval_status['spec']['pending_units'])}\n"
        f"已驳回：报告 {len(approval_status['report']['rejected_units'])}，Spec {len(approval_status['spec']['rejected_units'])}\n"
        f"最近交付：{delivery_line}\n"
        "提示：用 --json 查看各单元批准/驳回/构建/检查/交付状态"
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
        "delivery": delivery_summary,
    }
    emit(args, data, human)
    return 0
