"""Summarize source and per-unit progress."""

from __future__ import annotations

import argparse
from typing import Any

from ..command_output import emit
from ..delivery import last_delivery, units_changed_since
from ..design_deck import deck_dir, placeholder_pages
from ..design_workflow import check_status
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
            "slides": {"supported": False, "deck_exists": False, "checked_current": False},
        }
        emit(args, data, V1_UNSUPPORTED_MESSAGE, error=True)
        return 1
    _, pending, removed = scan_sources(root, base, cfg)
    unit_status = collect_units_status(
        base, selected=args.units, chapters=cfg.get("chapters", []), project_root=root,
    )
    selected_ids = set(unit_status["selected_units"])
    selected_rows = [row for row in unit_status["units"] if row["id"] in selected_ids]
    approved = [row["id"] for row in selected_rows if row["report_current"]]
    pending_approval = [row["id"] for row in selected_rows if row["report_pending"]]
    rejected = [
        row["id"] for row in selected_rows
        if row.get("report_latest_decision") == "rejected" and not row["report_current"] and not row["report_pending"]
    ]
    report_status: dict[str, Any] = {
        "supported": True,
        "current": bool(selected_rows) and len(approved) == len(selected_rows),
        "approved_units": approved,
        "pending_units": pending_approval,
        "unattributed_units": [row["id"] for row in selected_rows if row["report_unattributed"]],
        "rejected_units": rejected,
        "rejections": {
            row["id"]: row.get("report_latest_rejection")
            for row in selected_rows
            if row.get("report_latest_decision") == "rejected"
        },
        "needs_review_units": [
            row["id"] for row in selected_rows
            if not row["report_current"] and not row["report_pending"] and row["id"] not in rejected
        ],
        "approved_by": {
            row["id"]: {
                "name": row["report_approved_by"],
                "account": row["report_approved_account"],
                "at": row["report_approved_at"],
                "channel": row.get("report_approval_channel"),
                "user_reply": row.get("report_user_reply"),
            }
            for row in selected_rows
            if row["report_current"] and row["report_approved_by"]
        },
        "message": "按选定单元汇总；用 status --unit <id> 查看单元，approve report --unit <id> 提交审批申请",
    }
    check = check_status(base)
    slide_status = {
        "supported": True,
        "deck_exists": check["deck_exists"],
        "deck_dir": str(deck_dir(base)),
        "units_without_pages": [row["id"] for row in selected_rows if not row["pages"]],
        "placeholder_units": [row["id"] for row in selected_rows if row["pages"] and placeholder_pages(base, row["id"])],
        "checked": check["checked"],
        "checked_current": check["current"],
        "last_check": check["last"],
        "message": "checked_current 表示最近一次 slides check 通过且之后 deck 未变；版面效果由用户在 5173 审阅",
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
    deck_line = (
        "尚未创建" if not check["deck_exists"]
        else "检查通过（当前版本）" if check["current"]
        else "需要重新检查" if check["checked"] else "尚未检查"
    )
    delivery_line = f"v{last['sequence']}（{last['date']}）" if last else "暂无"
    human = (
        f"项目：{root}\n格式：v2\n待整理资料：{len(pending)}\n已移除资料：{len(removed)}\n"
        f"选定单元：{len(unit_status['selected_units'])}\n"
        f"受影响：{len(unit_status['affected_units'])}\n"
        f"可复用：{len(unit_status['reused_units'])}\n"
        f"阻塞：{len(unit_status['blocked_units'])}\n"
        f"待人工确认报告：{len(pending_approval)}\n"
        f"已驳回报告：{len(rejected)}\n"
        f"Design deck：{deck_line}\n"
        f"最近交付：{delivery_line}\n"
        "提示：用 --json 查看各单元批准/驳回/页面/检查/交付状态"
    )
    data = {
        "project": str(root),
        "format_version": "v2",
        "deprecated": False,
        "pending_sources": pending,
        "removed_sources": removed,
        "approvals": {"report": report_status},
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
